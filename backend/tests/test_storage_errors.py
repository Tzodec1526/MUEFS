"""A storage outage is a retryable 503; a missing object stays a missing object."""

from io import BytesIO
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.services import document_service
from tests.test_document_http import filing_client as filing_client


class _Unreachable:
    def upload_fileobj(self, *args, **kwargs):
        raise EndpointConnectionError(endpoint_url="http://storage.invalid")

    get_object = delete_object = upload_fileobj


class _Missing:
    def get_object(self, **kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")


class _Interrupted:
    def get_object(self, **kwargs):
        class Body(BytesIO):
            def read(self, size=-1):
                raise ReadTimeoutError(endpoint_url="http://storage.invalid")

        return {"Body": Body()}


@pytest.fixture
def object_storage(monkeypatch):
    def use(client):
        monkeypatch.setattr(document_service, "uses_local_storage", lambda: False)
        monkeypatch.setattr(document_service, "get_s3_client", lambda: client)

    return use


def test_outages_and_missing_objects_are_distinguished(object_storage):
    object_storage(_Unreachable())
    for operation in (
        lambda: document_service.upload_document(b"bytes", "filings/1/a.txt", "text/plain"),
        lambda: document_service.download_document("filings/1/a.txt"),
        lambda: document_service.stored_integrity("filings/1/a.txt"),
        lambda: document_service.delete_document("filings/1/a.txt"),
    ):
        with pytest.raises(document_service.StorageUnavailableError):
            operation()
    object_storage(_Missing())
    with pytest.raises(FileNotFoundError):
        document_service.stored_integrity("filings/1/a.txt")
    # A read that fails partway through is an outage, not a mismatched file.
    object_storage(_Interrupted())
    with pytest.raises(document_service.StorageUnavailableError):
        document_service.stored_integrity("filings/1/a.txt")


async def test_unavailable_storage_is_a_retryable_response(filing_client, object_storage):
    client, envelope, _ = filing_client
    fields = {"title": "Record", "document_type_code": "COMPLAINT"}
    uploaded = await client.post(
        f"/api/v1/filings/{envelope.id}/documents", headers={"Idempotency-Key": str(uuid4())},
        data=fields, files={"file": ("record.txt", b"stored bytes", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    document = uploaded.json()["id"]

    object_storage(_Unreachable())
    responses = [
        await client.get(f"/api/v1/documents/{document}/download"),
        await client.get(f"/api/v1/documents/{document}/verify"),
        await client.post(
            f"/api/v1/filings/{envelope.id}/documents",
            headers={"Idempotency-Key": str(uuid4())},
            data=fields, files={"file": ("other.txt", b"other bytes", "text/plain")},
        ),
    ]
    for response in responses:
        assert response.status_code == 503, response.text
        assert response.headers["retry-after"] == "30"
        assert "temporarily unavailable" in response.json()["detail"]

    object_storage(_Missing())
    missing = await client.get(f"/api/v1/documents/{document}/download")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Document file is unavailable"
    verified = await client.get(f"/api/v1/documents/{document}/verify")
    assert verified.status_code == 200
    assert verified.json()["is_valid"] is False
