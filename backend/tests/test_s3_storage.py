"""Opt-in tests against disposable local S3-compatible storage; never a live bucket."""

import asyncio
import hashlib
import os
from contextlib import contextmanager
from io import BytesIO
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from app.config import settings
from app.services import document_service

S3_ENDPOINT = os.getenv("MUEFS_TEST_S3_ENDPOINT")
pytestmark = pytest.mark.skipif(not S3_ENDPOINT, reason="MUEFS_TEST_S3_ENDPOINT not configured")


def remove_test_bucket(client, bucket):
    """Empty and delete a test bucket; one that setup never created is already gone."""
    from botocore.exceptions import ClientError

    # Only a bucket named by these tests can be cleaned up.
    assert bucket.startswith("muefs-test-") and len(bucket) == 43
    try:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            if page.get("Contents"):
                client.delete_objects(
                    Bucket=bucket,
                    Delete={
                        "Objects": [{"Key": item["Key"]} for item in page["Contents"]],
                    },
                )
        client.delete_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchBucket":
            raise


@contextmanager
def disposable_bucket(monkeypatch):
    """Point storage at a new bucket name; always remove it and release the client."""
    assert urlsplit(S3_ENDPOINT).hostname in {"127.0.0.1", "localhost"}, (
        "Use disposable local storage"
    )
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://unused/unused")
    monkeypatch.setattr(settings, "s3_endpoint_url", S3_ENDPOINT)
    monkeypatch.setattr(settings, "s3_access_key", os.environ["MUEFS_TEST_S3_ACCESS_KEY"])
    monkeypatch.setattr(settings, "s3_secret_key", os.environ["MUEFS_TEST_S3_SECRET_KEY"])
    bucket = f"muefs-test-{uuid4().hex}"
    monkeypatch.setattr(settings, "s3_bucket_name", bucket)
    document_service.get_s3_client.cache_clear()
    client = document_service.get_s3_client()
    try:
        yield client, bucket
    finally:
        try:
            remove_test_bucket(client, bucket)
        finally:
            client.close()
            document_service.get_s3_client.cache_clear()


@pytest.fixture
def s3_storage(monkeypatch):
    with disposable_bucket(monkeypatch) as (client, bucket):
        client.create_bucket(Bucket=bucket)
        yield client, bucket


async def test_s3_parallel_uploads_and_integrity_reuse_the_client(s3_storage, monkeypatch):
    import boto3.session

    def unexpected_client(*args, **kwargs):
        pytest.fail("A storage operation discarded the reusable S3 connection pool")

    monkeypatch.setattr(boto3.session.Session, "client", unexpected_client)
    contents = {
        f"filings/1/{i}.txt": (f"Synthetic attachment {i}\n" * 12000).encode() for i in range(8)
    }
    await asyncio.gather(
        *(
            asyncio.to_thread(document_service.upload_document, data, key, "text/plain")
            for key, data in contents.items()
        )
    )
    results = await asyncio.gather(
        *(asyncio.to_thread(document_service.stored_integrity, key) for key in contents)
    )
    assert results == [(hashlib.sha256(data).hexdigest(), len(data)) for data in contents.values()]
    for key, data in contents.items():
        with document_service.download_document(key) as stream:
            assert stream.read() == data
    document_service.delete_document(next(iter(contents)))
    with pytest.raises(FileNotFoundError):
        document_service.stored_integrity(next(iter(contents)))


def test_s3_multipart_etag_does_not_replace_content_fingerprints(s3_storage):
    client, bucket = s3_storage
    key = "retained/multipart.pdf"
    # Boto3's default multipart threshold is 8 MiB; this exercises multipart storage.
    payload = b"Synthetic retained bytes\n" * 400000
    client.upload_fileobj(BytesIO(payload), bucket, key)
    metadata = client.head_object(Bucket=bucket, Key=key)
    assert "-" in metadata["ETag"]
    assert document_service.stored_integrity(key) == (
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )


def test_demo_seeding_creates_the_configured_bucket_once(monkeypatch):
    # Seeding creates the bucket here, so a seeding failure must still surface as itself.
    with disposable_bucket(monkeypatch):
        document_service.ensure_bucket()
        document_service.upload_document(b"kept", "demo/kept.txt", "text/plain")
        document_service.ensure_bucket()
        assert document_service.stored_integrity("demo/kept.txt")[1] == len(b"kept")
