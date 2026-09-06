"""Verify restored filing storage without changing the database or stored files.

Run against a quiescent restored database and its matching storage configuration.
Output is JSON Lines. A final summary with complete=true is required; an interrupted
report is incomplete. Exit codes: 0 verified, 1 discrepancies, 2 incomplete audit.
"""

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select, true
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.court import Court
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.services import document_service

_BATCH_SIZE = 250


class AuditConfigurationError(ValueError):
    """Operator guidance that is safe to retain without connection details."""


def _valid_fingerprint(digest: object, size: object) -> bool:
    return (
        isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        and type(size) is int
        and size >= 0
    )


async def inspect_files(
    connection: AsyncConnection,
    court_id: int | None = None,
) -> AsyncIterator[dict]:
    filings = select(FilingEnvelope.id).where(FilingEnvelope.court_id == court_id)
    documents = select(FilingDocument.id).where(FilingDocument.envelope_id.in_(filings))
    for model, kind in ((FilingDocument, "document"), (DocumentPublicCopy, "public_copy")):
        query = select(model.id, model.file_key, model.sha256_hash, model.file_size_bytes)
        if court_id is not None:
            query = query.where(
                FilingDocument.envelope_id.in_(filings)
                if model is FilingDocument
                else DocumentPublicCopy.document_id.in_(documents)
            )
        last_id: int | None = None
        while rows := (
            await connection.execute(
                query.where(model.id > last_id if last_id is not None else true())
                .order_by(model.id)
                .limit(_BATCH_SIZE),
            )
        ).all():
            for row in rows:
                result = {"kind": kind, "id": row.id}
                if not _valid_fingerprint(row.sha256_hash, row.file_size_bytes):
                    result["status"] = "invalid_metadata"
                else:
                    result.update(
                        expected_sha256=row.sha256_hash, expected_size_bytes=row.file_size_bytes
                    )
                    try:
                        digest, size = await run_in_threadpool(
                            document_service.stored_integrity,
                            row.file_key,
                        )
                    except FileNotFoundError:
                        result["status"] = "missing"
                    except ValueError:
                        result["status"] = "invalid_reference"
                    except (OSError, BotoCoreError, ClientError) as exc:
                        result.update(status="unavailable", error_type=type(exc).__name__)
                    else:
                        result.update(sha256=digest, size_bytes=size)
                        result["status"] = (
                            "verified"
                            if digest == row.sha256_hash and size == row.file_size_bytes
                            else "mismatch"
                        )
                yield result
            last_id = rows[-1].id


async def _compare_receipt_batch(connection: AsyncConnection, references: list[dict]) -> list[dict]:
    rows = (
        await connection.execute(
            select(
                FilingDocument.id,
                FilingDocument.envelope_id,
                FilingDocument.sha256_hash,
                FilingDocument.file_size_bytes,
            ).where(FilingDocument.id.in_({ref["document_id"] for ref in references}))
        )
    ).all()
    documents = {row.id: row for row in rows}
    copy_ids = {ref["copy_id"] for ref in references if ref["kind"] == "receipt_public_copy"}
    copies = {}
    if copy_ids:
        copy_rows = (
            await connection.execute(
                select(
                    DocumentPublicCopy.id,
                    DocumentPublicCopy.document_id,
                    DocumentPublicCopy.sha256_hash,
                    DocumentPublicCopy.file_size_bytes,
                ).where(DocumentPublicCopy.id.in_(copy_ids))
            )
        ).all()
        copies = {row.id: row for row in copy_rows}
    for ref in references:
        document = documents.get(ref["document_id"])
        stored = copies.get(ref["copy_id"]) if ref["kind"] == "receipt_public_copy" else document
        if document is None or stored is None:
            ref["status"] = "missing_metadata"
        elif (
            document.envelope_id != ref["filing_id"]
            or (ref["kind"] == "receipt_public_copy" and stored.document_id != ref["document_id"])
            or stored.sha256_hash != ref["expected_sha256"]
            or stored.file_size_bytes != ref["expected_size_bytes"]
        ):
            ref["status"] = "receipt_mismatch"
        else:
            ref["status"] = "metadata_consistent"
    return references


async def inspect_receipts(
    connection: AsyncConnection,
    court_id: int | None = None,
) -> AsyncIterator[dict]:
    query = select(
        FilingTransaction.id,
        FilingTransaction.filing_id,
        FilingTransaction.details,
        FilingTransaction.event_type,
    ).where(
        FilingTransaction.event_type.in_(
            [
                "submitted",
                "service_recorded",
                "waiver_granted",
                "waiver_denied",
                "public_copy_published",
            ]
        ),
    )
    if court_id is not None:
        query = query.where(
            FilingTransaction.filing_id.in_(
                select(FilingEnvelope.id).where(FilingEnvelope.court_id == court_id),
            )
        )
    last_id: str | None = None
    references: list[dict] = []
    # Receipts carry JSON manifests. Keep only a small page plus one document batch.
    while rows := (
        await connection.execute(
            query.where(FilingTransaction.id > last_id if last_id is not None else true())
            .order_by(FilingTransaction.id)
            .limit(25),
        )
    ).all():
        for row in rows:
            is_copy = row.event_type == "public_copy_published"
            manifest = None
            if isinstance(row.details, dict):
                manifest = (
                    [row.details.get("public_copy")] if is_copy else row.details.get("documents")
                )
            if not isinstance(manifest, list) or not manifest:
                yield {"kind": "receipt", "id": row.id, "status": "invalid_manifest"}
                continue
            for index, entry in enumerate(manifest):
                ref = {
                    "kind": "receipt_public_copy" if is_copy else "receipt_document",
                    "id": row.id,
                    "index": index,
                    "filing_id": row.filing_id,
                }
                if (
                    not isinstance(entry, dict)
                    or type(entry.get("id")) is not int
                    or entry["id"] <= 0
                    or (
                        is_copy
                        and (type(entry.get("document_id")) is not int or entry["document_id"] <= 0)
                    )
                    or not _valid_fingerprint(
                        entry.get("sha256_hash"), entry.get("file_size_bytes")
                    )
                ):
                    yield {**ref, "status": "invalid_manifest"}
                    continue
                references.append(
                    {
                        **ref,
                        "document_id": entry["document_id"] if is_copy else entry["id"],
                        "expected_sha256": entry["sha256_hash"],
                        "expected_size_bytes": entry["file_size_bytes"],
                    }
                )
                if is_copy:
                    references[-1]["copy_id"] = entry["id"]
                if len(references) == _BATCH_SIZE:
                    for result in await _compare_receipt_batch(connection, references):
                        yield result
                    references = []
        last_id = rows[-1].id
    if references:
        for result in await _compare_receipt_batch(connection, references):
            yield result


async def run_audit(output: TextIO, court_id: int | None = None) -> int:
    started = datetime.now(UTC)
    print(
        json.dumps(
            {
                "kind": "start",
                "schema_version": 1,
                "run_id": str(uuid4()),
                "started_at": started.isoformat(),
                "court_id": court_id,
            }
        ),
        file=output,
        flush=True,
    )
    counts: Counter[str] = Counter()
    checked: Counter[str] = Counter()
    complete = False
    engine = None
    try:
        url = make_url(settings.database_url)
        if url.get_backend_name() == "sqlite":
            if not url.database or url.database == ":memory:" or url.query.get("uri"):
                raise AuditConfigurationError(
                    "Use a file-backed SQLite database URL without URI options"
                )
            # Open read-only: a typo must not create an empty database to 'verify'.
            try:
                database = Path(url.database).resolve(strict=True)
            except FileNotFoundError as exc:
                raise AuditConfigurationError(
                    "The configured SQLite database does not exist"
                ) from exc
            url = url.set(
                database=database.as_uri(),
                query={**url.query, "mode": "ro", "uri": "true"},
            )
        elif url.get_backend_name() != "postgresql":
            raise AuditConfigurationError("Storage auditing supports PostgreSQL and SQLite")
        engine = create_async_engine(url, echo=False)
        async with engine.connect() as connection:
            if url.get_backend_name() == "postgresql":
                await connection.execution_options(isolation_level="REPEATABLE READ")
                await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            else:
                await connection.exec_driver_sql("PRAGMA query_only=ON")
                # Explicit BEGIN also covers sqlite3's legacy SELECT transaction mode.
                await connection.exec_driver_sql("BEGIN")
            if court_id is not None and not await connection.scalar(
                select(Court.id).where(Court.id == court_id),
            ):
                raise AuditConfigurationError("The selected court does not exist")
            for inspection in (inspect_files, inspect_receipts):
                async for result in inspection(connection, court_id):
                    counts[result["status"]] += 1
                    checked[result["kind"]] += 1
                    print(json.dumps(result), file=output, flush=True)
        complete = True
    except BrokenPipeError:
        raise
    except (SQLAlchemyError, OSError, ValueError) as exc:
        # Database/storage exception messages can contain credentials, keys or filenames.
        print(
            json.dumps(
                {
                    "kind": "error",
                    "status": "incomplete",
                    "error_type": type(exc).__name__,
                    "message": str(exc)
                    if isinstance(exc, AuditConfigurationError)
                    else "Could not read the collection. Check database access and schema.",
                }
            ),
            file=output,
            flush=True,
        )
    finally:
        if engine:
            await engine.dispose()
    failures = sum(
        count
        for status, count in counts.items()
        if status not in {"verified", "metadata_consistent"}
    )
    exit_code = 2 if not complete else int(failures > 0)
    print(
        json.dumps(
            {
                "kind": "summary",
                "complete": complete,
                "exit_code": exit_code,
                "checked": dict(checked),
                "results": dict(counts),
                "finished_at": datetime.now(UTC).isoformat(),
            }
        ),
        file=output,
        flush=True,
    )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Create a new UTF-8 JSONL report (default: stdout)"
    )
    parser.add_argument("--court-id", type=int, help="Limit the report to one court")
    args = parser.parse_args()
    if args.court_id is not None and args.court_id <= 0:
        parser.error("--court-id must be positive")
    try:
        if args.output:
            # Never overwrite an earlier recovery report.
            with args.output.open("x", encoding="utf-8") as output:
                return asyncio.run(run_audit(output, args.court_id))
        return asyncio.run(run_audit(sys.stdout, args.court_id))
    except OSError as exc:
        print(f"Could not write audit report ({type(exc).__name__})", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
