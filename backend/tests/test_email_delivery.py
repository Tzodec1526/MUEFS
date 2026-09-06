"""Exercise durable delivery over a local SMTP socket; no external mail is sent."""

import asyncio
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import Parser

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.filing import FilingEnvelope
from app.models.notification import DeliveryStatus, Notification, NotificationDeliveryEvent
from app.models.user import User, UserType
from app.services import email_delivery_service as delivery
from app.services.notification_service import notify_filing_status_change
from tests.test_filing_history import filing_fixture


@pytest_asyncio.fixture
async def smtp_sink(monkeypatch):
    state = {"rcpt_code": 250, "lose_reply": False, "messages": [], "commands": []}

    async def smtp(reader, writer):
        writer.write(b"220 localhost test mail sink\r\n")
        await writer.drain()
        try:
            while line := await reader.readline():
                verb = line.strip().split(b" ", 1)[0].upper()
                state["commands"].append(verb)
                if verb == b"EHLO":
                    writer.write(b"250-localhost\r\n250 SIZE 100000\r\n")
                elif verb in (b"HELO", b"MAIL", b"RSET"):
                    writer.write(b"250 OK\r\n")
                elif verb == b"RCPT":
                    writer.write(f"{state['rcpt_code']} Recipient response\r\n".encode())
                elif verb == b"DATA":
                    writer.write(b"354 End with dot\r\n")
                    await writer.drain()
                    lines = []
                    while (part := await reader.readline()) not in (b".\r\n", b""):
                        lines.append(part[1:] if part.startswith(b"..") else part)
                    state["messages"].append(b"".join(lines).decode("ascii"))
                    if state["lose_reply"]:
                        break
                    writer.write(b"250 Message accepted\r\n")
                elif verb == b"QUIT":
                    writer.write(b"221 Goodbye\r\n")
                    break
                else:
                    writer.write(b"502 Unsupported\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(smtp, "127.0.0.1", 0)
    for name, value in {
        "email_delivery_enabled": True,
        "debug": True,
        "allow_demo_mode": True,
        "smtp_host": "127.0.0.1",
        "smtp_port": server.sockets[0].getsockname()[1],
        "smtp_tls": "plain",
        "smtp_from": "notices@example.com",
        "smtp_username": "",
        "portal_base_url": "http://localhost:8013",
    }.items():
        monkeypatch.setattr(settings, name, value)
    try:
        yield state
    finally:
        server.close()
        await server.wait_closed()


@pytest_asyncio.fixture
async def mail_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def prepare_notice(db):
    fid, filer, clerk, other = await filing_fixture(db)
    user = await db.get(User, filer)
    user.verified_email = user.email
    filing = await db.get(FilingEnvelope, fid)
    filing.case_title = "Protected caption and financial information"
    notice = await notify_filing_status_change(
        db, filer_id=filer, filing_id=fid, status="submitted",
        court_name="Records Court", case_title=filing.case_title,
    )
    return notice.id, fid, filer, clerk, other


async def test_smtp_acceptance_retains_generic_message_and_attempts(mail_sessions, smtp_sink):
    async with mail_sessions.begin() as db:
        nid, _fid, _filer, _clerk, _other = await prepare_notice(db)
    assert smtp_sink["messages"] == []  # Queuing a notice never opens SMTP.
    assert await delivery.deliver_next(mail_sessions)
    assert not await delivery.deliver_next(mail_sessions)
    async with mail_sessions() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status == DeliveryStatus.SENT
        assert notice.sent_at is not None and notice.attempt_count == 1
        events = list(
            await db.scalars(
                select(NotificationDeliveryEvent).order_by(NotificationDeliveryEvent.id)
            )
        )
        assert [e.outcome for e in events] == ["queued", "started", "accepted"]
        assert events[2].smtp_code == 250
        assert smtp_sink["messages"] == [events[0].message]
        message = Parser(policy=policy.default).parsestr(smtp_sink["messages"][0])
        assert message["Message-ID"] == notice.email_message_id
        assert message["To"] == "receipt@test.com"
        assert "Protected caption" not in message.get_content()
        assert (
            "Case:" not in message.get_content()
            and "http://localhost:8013/filings/" in message.get_content()
        )


async def test_temporary_failure_retries_same_message_after_due_time(mail_sessions, smtp_sink):
    smtp_sink["rcpt_code"] = 451
    async with mail_sessions.begin() as db:
        nid, *_ = await prepare_notice(db)
    assert await delivery.deliver_next(mail_sessions)
    assert not await delivery.deliver_next(mail_sessions)
    async with mail_sessions.begin() as db:
        notice = await db.get(Notification, nid)
        message_id = notice.email_message_id
        assert notice.delivery_status == DeliveryStatus.PENDING and notice.last_error
        assert notice.next_attempt_at.replace(tzinfo=UTC) > datetime.now(UTC)
        notice.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    smtp_sink["rcpt_code"] = 250
    assert await delivery.deliver_next(mail_sessions)
    async with mail_sessions() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status == DeliveryStatus.SENT and notice.attempt_count == 2
        assert notice.email_message_id == message_id
    assert len(smtp_sink["messages"]) == 1


async def test_lost_final_smtp_response_requires_review_not_automatic_retry(
    mail_sessions, smtp_sink
):
    smtp_sink["lose_reply"] = True
    async with mail_sessions.begin() as db:
        nid, *_ = await prepare_notice(db)
    assert await delivery.deliver_next(mail_sessions)
    assert not await delivery.deliver_next(mail_sessions)
    async with mail_sessions() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status == DeliveryStatus.UNKNOWN
        assert notice.sent_at is None and notice.next_attempt_at is None
    assert len(smtp_sink["messages"]) == 1  # The relay actually received the bytes.


@pytest.mark.parametrize("smtp_code, attempts", [(550, 1), (451, 5)])
async def test_rejected_mail_stops_at_permanent_failure_or_retry_limit(
    mail_sessions, smtp_sink, smtp_code, attempts
):
    smtp_sink["rcpt_code"] = smtp_code
    async with mail_sessions.begin() as db:
        nid, *_ = await prepare_notice(db)
    for attempt in range(1, attempts + 1):
        assert await delivery.deliver_next(mail_sessions)
        async with mail_sessions.begin() as db:
            notice = await db.get(Notification, nid)
            assert notice.attempt_count == attempt
            if attempt < attempts:
                assert notice.delivery_status == DeliveryStatus.PENDING
                notice.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                assert notice.delivery_status == DeliveryStatus.FAILED
                assert notice.next_attempt_at is None
    assert not await delivery.deliver_next(mail_sessions)
    assert smtp_sink["commands"].count(b"RCPT") == attempts
    assert smtp_sink["messages"] == []


async def test_interrupted_attempt_is_retained_and_stale_worker_cannot_overwrite_retry(
    mail_sessions,
    smtp_sink,
):
    async with mail_sessions.begin() as db:
        nid, *_ = await prepare_notice(db)
    claimed = await delivery.claim_email(mail_sessions)
    async with mail_sessions.begin() as db:
        notice = await db.get(Notification, nid)
        notice.last_attempt_at = datetime.now(UTC) - timedelta(minutes=11)
    assert await delivery.recover_interrupted(mail_sessions) == 1
    assert not await delivery.deliver_next(mail_sessions)
    async with mail_sessions.begin() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status == DeliveryStatus.UNKNOWN
        await delivery.queue_email(db, notice, reason="Relay records reviewed")
    await delivery.finish_attempt(mail_sessions, claimed, "accepted", 250, None)
    async with mail_sessions() as db:
        notice = await db.get(Notification, nid)
        assert notice.delivery_status == DeliveryStatus.PENDING and notice.sent_at is None
        outcomes = list(
            await db.scalars(
                select(NotificationDeliveryEvent.outcome).order_by(NotificationDeliveryEvent.id)
            )
        )
        assert outcomes == ["queued", "started", "unknown", "queued", "accepted"]


async def test_verification_is_rechecked_before_smtp(mail_sessions, smtp_sink):
    async with mail_sessions.begin() as db:
        nid, _fid, filer, *_ = await prepare_notice(db)
        (await db.get(User, filer)).verified_email = None
    assert await delivery.deliver_next(mail_sessions)
    async with mail_sessions() as db:
        assert (await db.get(Notification, nid)).delivery_status == DeliveryStatus.BLOCKED
    assert smtp_sink["commands"] == []


async def test_rollback_does_not_leave_an_email_to_send(mail_sessions, smtp_sink):
    with pytest.raises(RuntimeError):
        async with mail_sessions.begin() as db:
            await prepare_notice(db)
            raise RuntimeError("Database work failed")
    assert not await delivery.deliver_next(mail_sessions)
    async with mail_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(NotificationDeliveryEvent)) == 0
    assert smtp_sink["commands"] == []


async def test_notice_scope_retry_permissions_and_retained_events(
    db_session, api_client, smtp_sink
):
    nid, fid, filer, clerk, other = await prepare_notice(db_session)
    notice = await db_session.get(Notification, nid)
    notice.delivery_status = DeliveryStatus.UNKNOWN
    notice.next_attempt_at = None
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(other)
    assert (await api_client.get(f"/api/v1/notifications/{nid}/delivery")).status_code == 403
    court_id = (await db_session.get(FilingEnvelope, fid)).court_id
    assert (await api_client.get(f"/api/v1/notifications?court_id={court_id}")).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(filer)
    assert (await api_client.get("/api/v1/notifications")).json()["total"] == 1
    assert (
        await api_client.post(f"/api/v1/notifications/{nid}/retry", json={"reason": "Please retry"})
    ).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    listing = (
        await api_client.get(f"/api/v1/notifications?court_id={court_id}&delivery_status=unknown")
    ).json()
    assert listing["total"] == 1 and listing["notifications"][0]["created_at"].endswith("+00:00")
    assert (
        await api_client.post(f"/api/v1/notifications/{nid}/retry", json={"reason": " "})
    ).status_code == 400
    retry = await api_client.post(
        f"/api/v1/notifications/{nid}/retry", json={"reason": "Relay investigation completed"}
    )
    assert retry.status_code == 200 and retry.json()["delivery_status"] == "pending"
    assert (
        await api_client.post(f"/api/v1/notifications/{nid}/retry", json={"reason": "Duplicate"})
    ).status_code == 409
    events = (await api_client.get(f"/api/v1/notifications/{nid}/delivery")).json()["events"]
    assert events[0]["detail"] == "Relay investigation completed"
    assert "message" not in events[0]
    for statement in (
        "DELETE FROM notification_delivery_events",
        "UPDATE notification_delivery_events SET outcome='changed'",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement))


async def test_oidc_verifies_email_and_revokes_mismatched_or_unverified_claims(
    db_session,
    api_client,
    monkeypatch,
):
    from app.api import auth

    user = User(
        email="identity@example.com",
        first_name="ID",
        last_name="User",
        user_type=UserType.SELF_REPRESENTED,
        keycloak_id="verified-sub",
    )
    db_session.add(user)
    await db_session.flush()
    api_client.headers["Authorization"] = "Bearer token"
    claims = {"sub": "verified-sub", "email": user.email, "email_verified": True}

    async def decode(_token):
        return claims

    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    assert (await api_client.get("/api/v1/auth/me")).status_code == 200
    assert user.verified_email == user.email
    claims["email"] = "different@example.com"
    await api_client.get("/api/v1/auth/me")
    assert user.verified_email is None
    claims.update(email=user.email, email_verified=False)
    await api_client.get("/api/v1/auth/me")
    assert user.verified_email is None


async def test_starttls_failure_does_not_send_credentials_or_message(
    mail_sessions, smtp_sink, monkeypatch
):
    async with mail_sessions.begin() as db:
        await prepare_notice(db)
    monkeypatch.setattr(settings, "smtp_tls", "starttls")
    monkeypatch.setattr(settings, "smtp_username", "test-user")
    await delivery.deliver_next(mail_sessions)
    assert b"MAIL" not in smtp_sink["commands"] and b"AUTH" not in smtp_sink["commands"]
    assert smtp_sink["messages"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"smtp_host": "relay.example.com"},
        {"debug": False},
        {"portal_base_url": "https://user:password@example.com"},
        {"smtp_from": "notices@example.com\nBcc: other@example.com"},
    ],
)
def test_unsafe_mail_configuration_is_rejected(smtp_sink, monkeypatch, changes):
    for name, value in changes.items():
        monkeypatch.setattr(settings, name, value)
    with pytest.raises(ValueError):
        delivery.validate_email_config()
