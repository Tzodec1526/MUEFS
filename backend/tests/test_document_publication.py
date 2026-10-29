"""A public copy must never expose or replace its retained original."""

import hashlib
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.audit import AuditLog
from app.models.case import Case
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import audit_service, document_service
from tests.filing_requests import submission_review
from tests.test_filing_history import filing_fixture


def publication_pdf(content: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({content}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
async def public_record(db_session, api_client, monkeypatch, tmp_path):
    fid, filer, clerk, other = await filing_fixture(db_session)
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    original = publication_pdf("Original private identifier 123-45-6789")
    api_client.headers["X-Demo-User-Id"] = str(filer)
    upload = await api_client.post(
        f"/api/v1/filings/{fid}/documents",
        headers={"Idempotency-Key": str(uuid4())},
        data={"title": "Private original title", "document_type_code": "COMPLAINT"},
        files={"file": ("original.pdf", original, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    did = upload.json()["id"]
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )).status_code == 200
    receipt = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"][0]
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    accepted = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/review",
        json={"expected_submission_count": 1, "action": "accept"},
    )
    assert accepted.status_code == 200, accepted.text
    return dict(
        filing_id=fid,
        document_id=did,
        filer=filer,
        clerk=clerk,
        other=other,
        case_id=accepted.json()["case_id"],
        original=original,
        receipt=receipt,
        storage=tmp_path,
    )


async def prepare_copy(client, document_id, content="Public copy without private identifier"):
    payload = publication_pdf(content)
    response = await client.post(
        f"/api/v1/clerk/documents/{document_id}/public-copies",
        data={"title": "Court-reviewed public title"},
        files={"file": ("public.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json(), payload


async def test_prepare_publish_withdraw_preserves_original_and_receipt(
    public_record, api_client, db_session
):
    record = public_record
    did, fid, cid = record["document_id"], record["filing_id"], record["case_id"]
    path = f"/api/v1/clerk/documents/{did}"
    copy, payload = await prepare_copy(api_client, did)
    copy_url = f"/api/v1/document-public-copies/{copy['id']}/download"
    original_url = f"/api/v1/documents/{did}/download"
    other = {"X-Demo-User-Id": str(record["other"])}
    owner = {"X-Demo-User-Id": str(record["filer"])}
    assert (await api_client.get(copy_url)).content == payload
    assert (await api_client.get(copy_url, headers=owner)).status_code == 403
    assert (await api_client.get(copy_url, headers=other)).status_code == 403
    assert (await api_client.get(original_url, headers=other)).content == record["original"]
    data = {
        "copy_id": copy["id"],
        "expected_version": 0,
        "reviewed": False,
        "reason": "Reviewed copy and authority REF-101",
    }
    assert (await api_client.post(path + "/publication", json=data)).status_code == 422
    data["reviewed"] = True
    assert (await api_client.post(path + "/publication", json=data)).status_code == 200
    assert (await api_client.get(original_url, headers=other)).status_code == 403
    assert (
        await api_client.get(f"/api/v1/documents/{did}/verify", headers=other)
    ).status_code == 403
    assert (await api_client.get(original_url, headers=owner)).content == record["original"]
    published = await api_client.get(copy_url, headers=other)
    assert (
        published.content == payload and published.headers["cache-control"] == "private, no-store"
    )
    docket = (await api_client.get(f"/api/v1/cases/{cid}/filings", headers=other)).json()
    public_doc = docket[0]["documents"][0]
    assert public_doc["title"] == copy["title"] and public_doc["sha256_hash"] == copy["sha256_hash"]
    assert public_doc["copy_id"] == copy["id"] and public_doc["file_size_bytes"] == len(payload)
    assert public_doc["document_type_code"] == "PUBLIC_COPY"
    assert "Private original title" not in str(docket)
    assert hashlib.sha256(record["original"]).hexdigest() not in str(docket)
    history = (await api_client.get(f"/api/v1/filings/{fid}/history", headers=owner)).json()
    assert (
        next(row for row in history["transactions"] if row["id"] == record["receipt"]["id"])
        == record["receipt"]
    )
    assert any(row["event_type"] == "public_copy_published" for row in history["transactions"])
    assert not history["can_manage_documents"]
    assert (await api_client.post(path + "/publication", json=data)).status_code == 409
    withheld = await api_client.post(
        path + "/withhold",
        json={"expected_version": 1, "reason": "Withdraw publication for further review REF-102"},
    )
    assert withheld.status_code == 200
    assert (await api_client.get(copy_url, headers=other)).status_code == 403
    assert (await api_client.get(original_url, headers=other)).status_code == 403
    assert (await api_client.get(copy_url, headers=owner)).content == payload
    assert (await api_client.get(f"/api/v1/cases/{cid}/filings", headers=other)).json()[0][
        "documents"
    ] == []
    # A later explicit publication may restore a reviewed copy, never the original.
    data["expected_version"] = 2
    assert (await api_client.post(path + "/publication", json=data)).status_code == 200
    assert (await api_client.get(copy_url, headers=other)).content == payload
    original = await db_session.get(FilingDocument, did)
    assert original.sha256_hash == hashlib.sha256(record["original"]).hexdigest()
    assert original.title == "Private original title" and original.is_confidential


async def test_preparation_warnings_are_visible_before_publication(public_record, api_client):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did, "Potential identifier 123-45-6789")
    assert copy["pii_warnings"]
    assert "file_key" not in copy
    state = (await api_client.get(f"/api/v1/clerk/documents/{did}/publication")).json()
    assert state["version"] == 0 and state["current_copy"] is None
    assert not state["document"]["is_confidential"]


async def test_only_this_courts_staff_can_change_document_publication(
    public_record, api_client, db_session
):
    did = public_record["document_id"]
    admin = User(
        email="unassigned-admin@example.com",
        first_name="System",
        last_name="Admin",
        user_type=UserType.ADMIN,
    )
    db_session.add(admin)
    await db_session.flush()
    for actor in [public_record["filer"], public_record["other"], admin.id]:
        headers = {"X-Demo-User-Id": str(actor)}
        for suffix in ["publication", "publication/history"]:
            assert (
                await api_client.get(f"/api/v1/clerk/documents/{did}/{suffix}", headers=headers)
            ).status_code == 403
        assert (
            await api_client.post(
                f"/api/v1/clerk/documents/{did}/withhold",
                headers=headers,
                json={"expected_version": 0, "reason": "Unauthorized attempt"},
            )
        ).status_code == 403
        response = await api_client.post(
            f"/api/v1/clerk/documents/{did}/public-copies",
            headers=headers,
            data={"title": "Unauthorized copy"},
            files={"file": ("copy.pdf", publication_pdf("Public"), "application/pdf")},
        )
        assert response.status_code == 403


@pytest.mark.parametrize("restriction", ["fee_waiver", "superseded", "not_accepted", "no_case"])
async def test_publication_cannot_bypass_document_restrictions(
    public_record, api_client, db_session, restriction
):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did)
    doc = await db_session.get(FilingDocument, did)
    if restriction == "fee_waiver":
        doc.document_type_code = "FEE_WAIVER"
    elif restriction == "superseded":
        from datetime import UTC, datetime

        doc.removed_at = datetime.now(UTC)
    elif restriction == "no_case":
        (await db_session.get(FilingEnvelope, public_record["filing_id"])).case_id = None
    else:
        (
            await db_session.get(FilingEnvelope, public_record["filing_id"])
        ).status = FilingStatus.RETURNED
    await db_session.flush()
    response = await api_client.post(
        f"/api/v1/clerk/documents/{did}/publication",
        json={
            "copy_id": copy["id"],
            "expected_version": 0,
            "reviewed": True,
            "reason": "Must fail",
        },
    )
    assert response.status_code == 409
    assert doc.public_copy_id is None and doc.access_version == 0


async def test_sealed_case_blocks_public_copy_download(public_record, api_client, db_session):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did)
    assert (
        await api_client.post(
            f"/api/v1/clerk/documents/{did}/publication",
            json={
                "copy_id": copy["id"],
                "expected_version": 0,
                "reviewed": True,
                "reason": "Reviewed",
            },
        )
    ).status_code == 200
    case = await db_session.get(Case, public_record["case_id"])
    case.is_sealed = True
    await db_session.flush()
    assert (
        await api_client.get(
            f"/api/v1/document-public-copies/{copy['id']}/download",
            headers={"X-Demo-User-Id": str(public_record["other"])},
        )
    ).status_code == 403


@pytest.mark.parametrize("operation", ["prepare", "publish", "withhold"])
async def test_audit_failure_rolls_back_publication_and_cleans_uncommitted_copy(
    public_record,
    api_client,
    db_session,
    monkeypatch,
    operation,
):
    did = public_record["document_id"]
    copy = None
    if operation == "publish":
        copy, _ = await prepare_copy(api_client, did)
    before_transactions = await db_session.scalar(
        select(func.count()).select_from(FilingTransaction)
    )

    async def failure(*args, **kwargs):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(audit_service, "log_action", failure)
    with pytest.raises(RuntimeError, match="Audit unavailable"):
        if operation == "prepare":
            await prepare_copy(api_client, did)
        else:
            await api_client.post(
                f"/api/v1/clerk/documents/{did}/" + ("publication" if copy else "withhold"),
                json={
                    "expected_version": 0,
                    "reason": "Must roll back",
                    **({"copy_id": copy["id"], "reviewed": True} if copy else {}),
                },
            )
    doc = await db_session.get(FilingDocument, did)
    assert doc.access_version == 0 and doc.public_copy_id is None and not doc.is_confidential
    assert (
        await db_session.scalar(select(func.count()).select_from(FilingTransaction))
        == before_transactions
    )
    assert len(list((public_record["storage"] / "public-copies").rglob("*.pdf"))) == (
        1 if copy else 0
    )


async def test_prepared_copy_integrity_and_metadata_are_retained(
    public_record, api_client, db_session
):
    did = public_record["document_id"]
    data, _ = await prepare_copy(api_client, did)
    copy = await db_session.get(DocumentPublicCopy, data["id"])
    for sql in [
        "UPDATE document_public_copies SET title='rewritten'",
        "DELETE FROM document_public_copies",
    ]:
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(sql))
    (public_record["storage"] / copy.file_key).write_bytes(publication_pdf("Different bytes"))
    response = await api_client.post(
        f"/api/v1/clerk/documents/{did}/publication",
        json={
            "copy_id": copy.id,
            "expected_version": 0,
            "reviewed": True,
            "reason": "Reviewed prior bytes",
        },
    )
    assert response.status_code == 409 and "integrity" in response.json()["detail"]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "public_copy.published")
        )
        == 0
    )


async def test_copy_cannot_be_published_against_a_different_original(
    public_record, api_client, db_session
):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did)
    other_doc = FilingDocument(
        envelope_id=public_record["filing_id"],
        title="Different original",
        document_type_code="EXHIBIT",
        file_key="different.pdf",
        file_size_bytes=1,
        mime_type="application/pdf",
        sha256_hash="a" * 64,
    )
    db_session.add(other_doc)
    await db_session.flush()
    response = await api_client.post(
        f"/api/v1/clerk/documents/{other_doc.id}/publication",
        json={
            "copy_id": copy["id"],
            "reviewed": True,
            "expected_version": 0,
            "reason": "Copy belongs to another document",
        },
    )
    assert response.status_code == 404
    assert not other_doc.is_confidential and other_doc.public_copy_id is None


@pytest.mark.parametrize(
    "payload,mime", [(b"%PDF-broken", "application/pdf"), (b"text", "text/plain")]
)
async def test_invalid_public_copy_is_not_retained(
    public_record, api_client, db_session, payload, mime
):
    response = await api_client.post(
        f"/api/v1/clerk/documents/{public_record['document_id']}/public-copies",
        data={"title": "Invalid copy"},
        files={"file": ("invalid.pdf", payload, mime)},
    )
    assert response.status_code in {415, 422}
    assert await db_session.scalar(select(func.count()).select_from(DocumentPublicCopy)) == 0
    assert not list((public_record["storage"] / "public-copies").rglob("*.pdf"))


@pytest.mark.parametrize("storage", ["local", "s3"])
async def test_missing_file_is_unavailable_without_fake_document(
    public_record, api_client, monkeypatch, tmp_path, storage,
):
    from botocore.exceptions import ClientError

    class MissingObject:
        def get_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    copy, _ = await prepare_copy(api_client, public_record["document_id"])
    if storage == "s3":
        monkeypatch.setattr(document_service, "uses_local_storage", lambda: False)
        monkeypatch.setattr(document_service, "get_s3_client", MissingObject)
    else:
        monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path / "missing")
    for url in [
        f"/api/v1/documents/{public_record['document_id']}/download",
        f"/api/v1/document-public-copies/{copy['id']}/download",
    ]:
        response = await api_client.get(url)
        assert response.status_code == 404
        assert response.json()["detail"] == "Document file is unavailable"
    response = await api_client.post(
        f"/api/v1/clerk/documents/{public_record['document_id']}/publication",
        json={
            "copy_id": copy["id"],
            "reviewed": True,
            "expected_version": 0,
            "reason": "Missing stored candidate",
        },
    )
    assert response.status_code == 409


async def test_access_history_keeps_actor_name_and_pages(public_record, api_client, db_session):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did)
    for version in range(26):
        publish = version % 2 == 0
        response = await api_client.post(
            f"/api/v1/clerk/documents/{did}/" + ("publication" if publish else "withhold"),
            json={
                "expected_version": version,
                "reason": f"Authority {version}",
                **({"copy_id": copy["id"], "reviewed": True} if publish else {}),
            },
        )
        assert response.status_code == 200
    actor = await db_session.get(User, public_record["clerk"])
    actor.first_name = "Renamed"
    await db_session.flush()
    first = (await api_client.get(f"/api/v1/clerk/documents/{did}/publication/history")).json()
    second = (
        await api_client.get(f"/api/v1/clerk/documents/{did}/publication/history?page=2")
    ).json()
    assert first["total"] == second["total"] == 27
    assert len(first["events"]) == 25 and len(second["events"]) == 2
    assert len({row["id"] for row in first["events"] + second["events"]}) == 27
    assert all(row["actor_name"] == "Records Clerk" for row in first["events"] + second["events"])
    assert first["events"][0]["details"]["reason"] == "Authority 25"


async def test_staff_cannot_decide_publication_of_their_own_filing(
    public_record, api_client, db_session,
):
    record = public_record
    did, fid = record["document_id"], record["filing_id"]
    filing = await db_session.get(FilingEnvelope, fid)
    # The filer also holds a clerk assignment at this court.
    db_session.add(UserCourtRole(
        user_id=record["filer"], court_id=filing.court_id, role=CourtRole.CLERK,
    ))
    await db_session.flush()
    copy, _ = await prepare_copy(api_client, did)  # prepared by an independent clerk
    stored_before = sorted(p.name for p in record["storage"].rglob("*") if p.is_file())
    api_client.headers["X-Demo-User-Id"] = str(record["filer"])
    path = f"/api/v1/clerk/documents/{did}"
    assert (await api_client.get(path + "/publication")).status_code == 200
    refused = [
        await api_client.post(
            path + "/public-copies", data={"title": "Own copy"},
            files={"file": ("own.pdf", publication_pdf("Own copy"), "application/pdf")},
        ),
        await api_client.post(path + "/publication", json={
            "copy_id": copy["id"], "expected_version": 0, "reviewed": True,
            "reason": "Own filing REF-1",
        }),
        await api_client.post(path + "/withhold", json={
            "expected_version": 0, "reason": "Own filing REF-2",
        }),
    ]
    for response in refused:
        assert response.status_code == 403, response.text
        assert "Another court reviewer" in response.json()["detail"]
    # The refused copy was never screened or stored.
    assert sorted(p.name for p in record["storage"].rglob("*") if p.is_file()) == stored_before
    history = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()
    assert history["can_manage_documents"] is False
    api_client.headers["X-Demo-User-Id"] = str(record["clerk"])
    assert (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["can_manage_documents"]


async def test_public_copy_downloads_fail_when_the_stored_bytes_changed(
    public_record, api_client, db_session,
):
    record = public_record
    did = record["document_id"]
    copy, payload = await prepare_copy(api_client, did)
    published = await api_client.post(f"/api/v1/clerk/documents/{did}/publication", json={
        "copy_id": copy["id"], "expected_version": 0, "reviewed": True,
        "reason": "Reviewed copy REF-9",
    })
    assert published.status_code == 200, published.text
    stored = await db_session.get(DocumentPublicCopy, copy["id"])
    (record["storage"] / stored.file_key).write_bytes(payload + b"tampered after review")
    response = await api_client.get(
        f"/api/v1/document-public-copies/{copy['id']}/download",
        headers={"X-Demo-User-Id": str(record["other"])},
    )
    assert response.status_code == 409, response.text
    assert b"tampered" not in response.content


async def test_storage_outage_while_publishing_is_retryable(public_record, api_client, monkeypatch):
    did = public_record["document_id"]
    copy, _ = await prepare_copy(api_client, did)

    def unavailable(file_key):
        raise document_service.StorageUnavailableError("Document storage is unavailable")

    monkeypatch.setattr(document_service, "stored_integrity", unavailable)
    response = await api_client.post(f"/api/v1/clerk/documents/{did}/publication", json={
        "copy_id": copy["id"], "expected_version": 0, "reviewed": True,
        "reason": "Reviewed copy REF-10",
    })
    # The copy is intact; the clerk should retry, not prepare it again.
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == "30"
