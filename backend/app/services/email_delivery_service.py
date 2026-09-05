"""Durable filing notices. SMTP acceptance is neither delivery nor legal service."""

import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.notification import DeliveryStatus, Notification, NotificationDeliveryEvent
from app.models.user import User

MAX_AUTOMATIC_ATTEMPTS = 5
INTERRUPTED_AFTER = timedelta(minutes=10)


def validate_email_config() -> None:
    if not settings.email_delivery_enabled:
        return
    origin = urlsplit(settings.portal_base_url)
    loopback = {"localhost", "127.0.0.1", "::1"}
    if (
        origin.scheme not in {"https", "http"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
    ):
        raise ValueError("PORTAL_BASE_URL must be the portal origin without credentials or a path")
    if origin.scheme != "https" and not (settings.debug and origin.hostname in loopback):
        raise ValueError("PORTAL_BASE_URL requires HTTPS outside a local development server")
    if not settings.smtp_host or not 1 <= settings.smtp_port <= 65535:
        raise ValueError("Configure SMTP_HOST and a valid SMTP_PORT")
    if settings.smtp_tls == "plain" and not (settings.debug and settings.smtp_host in loopback):
        raise ValueError("Unencrypted SMTP is permitted only for a local development mail sink")
    if settings.allow_demo_mode and settings.smtp_host not in loopback:
        raise ValueError("Demo mode cannot send email through an external SMTP relay")
    try:
        validate_email(settings.smtp_from, check_deliverability=False, allow_smtputf8=False)
    except EmailNotValidError as exc:
        raise ValueError("SMTP_FROM must be a single valid email address") from exc


async def queue_email(
    db: AsyncSession,
    notice: Notification,
    *,
    actor_id: int | None = None,
    reason: str | None = None,
) -> None:
    """Materialize a generic notice inside the filing transaction, without network I/O."""
    if not settings.email_delivery_enabled:
        notice.delivery_status = DeliveryStatus.DISABLED
        return
    validate_email_config()
    user = await db.get(User, notice.recipient_id)
    if (
        not user
        or not user.is_active
        or not user.verified_email
        or (user.verified_email != user.email.strip().lower())
    ):
        notice.delivery_status = DeliveryStatus.BLOCKED
        notice.last_error = "Recipient needs an active account and a verified matching email"
        return
    now = datetime.now(UTC)
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = validate_email(settings.smtp_from, check_deliverability=False).ascii_email
    message["To"] = validate_email(user.verified_email, check_deliverability=False).ascii_email
    message["Subject"] = "MUEFS: a filing update is available"
    message["Date"] = format_datetime(now)
    message["Message-ID"] = make_msgid(domain=str(message["From"]).rsplit("@", 1)[1])
    path = (
        f"/filings/{notice.filing_envelope_id}/history"
        if notice.filing_envelope_id
        else "/notifications"
    )
    message.set_content(
        "A filing update is available in your MUEFS account.\n\n"
        f"Sign in to read the update: {settings.portal_base_url.rstrip('/')}{path}\n\n"
        f"Notice reference: {notice.id}\n"
        "Case details and documents are available only after signing in.\n",
        cte="quoted-printable",
    )
    notice.email_recipient = user.verified_email
    notice.email_sender = settings.smtp_from
    notice.email_message_id = str(message["Message-ID"])
    notice.email_message = message.as_string()
    notice.delivery_status = DeliveryStatus.PENDING
    notice.sent_at = None
    notice.next_attempt_at = now
    notice.last_error = None
    db.add(
        NotificationDeliveryEvent(
            notification_id=notice.id,
            attempt_number=notice.attempt_count + 1,
            outcome="queued",
            occurred_at=now,
            actor_id=actor_id,
            detail=reason,
            message=notice.email_message,
        )
    )


async def claim_email(sessions: async_sessionmaker[AsyncSession]) -> Notification | None:
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        candidate = (
            select(Notification.id)
            .where(
                Notification.delivery_status == DeliveryStatus.PENDING,
                Notification.next_attempt_at <= now,
                Notification.email_message_id.is_not(None),
            )
            .order_by(Notification.next_attempt_at, Notification.id)
            .with_for_update(skip_locked=True)
            .limit(1)
            .scalar_subquery()
        )
        notice = await db.scalar(
            update(Notification)
            .where(
                Notification.id == candidate,
                Notification.delivery_status == DeliveryStatus.PENDING,
            )
            .values(
                delivery_status=DeliveryStatus.SENDING,
                last_attempt_at=now,
                next_attempt_at=None,
                attempt_count=Notification.attempt_count + 1,
            )
            .returning(Notification)
        )
        if notice is None:
            return None
        user = await db.get(User, notice.recipient_id)
        if (
            not user
            or not user.is_active
            or user.verified_email != notice.email_recipient
            or (user.email.strip().lower() != notice.email_recipient)
        ):
            notice.delivery_status = DeliveryStatus.BLOCKED
            notice.last_error = "Recipient verification or account changed before sending"
            outcome = "blocked"
        else:
            outcome = "started"
        db.add(
            NotificationDeliveryEvent(
                notification_id=notice.id,
                attempt_number=notice.attempt_count,
                outcome=outcome,
                occurred_at=now,
                detail=notice.last_error if outcome == "blocked" else None,
            )
        )
    return notice


def send_email(notice: Notification) -> tuple[str, int | None, str | None]:
    """Use a bounded socket timeout; an interrupted DATA exchange has an unknown outcome."""
    if not notice.email_sender or not notice.email_recipient or not notice.email_message:
        return "permanent_failure", None, "Queued email is incomplete"
    smtp: smtplib.SMTP | None = None
    sending_data = False
    try:
        if settings.smtp_tls == "ssl":
            smtp = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=10,
                context=ssl.create_default_context(),
            )
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            if settings.smtp_tls == "starttls":
                smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        # Explicit envelope stages distinguish a refused message from a lost final response.
        smtp.ehlo_or_helo_if_needed()
        sender = validate_email(notice.email_sender, check_deliverability=False).ascii_email
        recipient = validate_email(notice.email_recipient, check_deliverability=False).ascii_email
        if sender is None or recipient is None:
            return "permanent_failure", None, "SMTPUTF8 addresses require a supported relay"
        code, _ = smtp.mail(sender)
        if code != 250:
            return (
                "temporary_failure" if code < 500 else "permanent_failure",
                code,
                "SMTP relay refused the sender",
            )
        code, _ = smtp.rcpt(recipient)
        if code not in (250, 251):
            return (
                "temporary_failure" if code < 500 else "permanent_failure",
                code,
                "SMTP relay refused the recipient",
            )
        sending_data = True
        code, _ = smtp.data(notice.email_message.encode("ascii"))
        return (
            ("accepted", code, None)
            if code == 250
            else (
                "temporary_failure" if code < 500 else "permanent_failure",
                code,
                "SMTP relay refused the message",
            )
        )
    except smtplib.SMTPResponseException as exc:
        return (
            "temporary_failure" if exc.smtp_code < 500 else "permanent_failure",
            exc.smtp_code,
            "SMTP relay rejected the exchange",
        )
    except EmailNotValidError:
        return "permanent_failure", None, "Queued address is invalid"
    except (OSError, smtplib.SMTPException):
        return (
            ("unknown", None, "The connection ended before the relay confirmed acceptance")
            if sending_data
            else ("temporary_failure", None, "Could not complete a connection to the email relay")
        )
    finally:
        if smtp is not None:
            # QUIT failure after a successful DATA must not turn acceptance into failure.
            smtp.close()


async def finish_attempt(
    sessions: async_sessionmaker[AsyncSession],
    notice: Notification,
    outcome: str,
    code: int | None,
    detail: str | None,
) -> None:
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        current = await db.scalar(
            select(Notification).where(Notification.id == notice.id).with_for_update()
        )
        db.add(
            NotificationDeliveryEvent(
                notification_id=notice.id,
                attempt_number=notice.attempt_count,
                outcome=outcome,
                occurred_at=now,
                smtp_code=code,
                detail=detail,
            )
        )
        if (
            current is None
            or current.attempt_count != notice.attempt_count
            or (current.delivery_status not in (DeliveryStatus.SENDING, DeliveryStatus.UNKNOWN))
        ):
            return  # A late worker cannot overwrite a newer attempt or an operator's retry.
        current.last_error = detail
        if outcome == "accepted":
            current.delivery_status = DeliveryStatus.SENT
            current.sent_at = now
        elif outcome == "unknown":
            current.delivery_status = DeliveryStatus.UNKNOWN
        elif outcome == "temporary_failure" and current.attempt_count < MAX_AUTOMATIC_ATTEMPTS:
            current.delivery_status = DeliveryStatus.PENDING
            current.next_attempt_at = now + timedelta(minutes=2**current.attempt_count)
        else:
            current.delivery_status = DeliveryStatus.FAILED


async def recover_interrupted(sessions: async_sessionmaker[AsyncSession]) -> int:
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        rows = list(
            await db.scalars(
                update(Notification)
                .where(
                    Notification.delivery_status == DeliveryStatus.SENDING,
                    Notification.last_attempt_at <= now - INTERRUPTED_AFTER,
                )
                .values(
                    delivery_status=DeliveryStatus.UNKNOWN,
                    last_error="Worker stopped before recording an outcome; inspect relay records",
                )
                .returning(Notification)
            )
        )
        for notice in rows:
            db.add(
                NotificationDeliveryEvent(
                    notification_id=notice.id,
                    attempt_number=notice.attempt_count,
                    outcome="unknown",
                    occurred_at=now,
                    detail=notice.last_error,
                )
            )
    return len(rows)


async def deliver_next(sessions: async_sessionmaker[AsyncSession]) -> bool:
    notice = await claim_email(sessions)
    if notice is None:
        return False
    if notice.delivery_status == DeliveryStatus.SENDING:
        result = await run_in_threadpool(send_email, notice)
        await finish_attempt(sessions, notice, *result)
    return True
