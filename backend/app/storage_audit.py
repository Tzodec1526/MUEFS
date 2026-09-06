"""Verify restored filing storage without changing the database or stored files.

Run against a quiescent restored database and its matching storage configuration.
Output is JSON Lines. A final summary with complete=true is required; an interrupted
report is incomplete. Exit codes: 0 verified, 1 discrepancies, 2 incomplete audit.
"""

import argparse
import asyncio
import hashlib
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
from sqlalchemy import func, or_, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.case import Case, CaseParticipant
from app.models.court import Court
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification, NotificationType, ServiceContact
from app.models.service_delivery import ServicePacket, ServiceRecipient
from app.models.user import User
from app.readonly_database import ReadOnlyDatabaseError, read_only_connection
from app.schemas.filing import FilingDocumentResponse
from app.services import document_service
from app.services.service_contact_service import CONTACT_SNAPSHOT_FIELDS

_BATCH_SIZE = 250


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
    *,
    case_id: int | None = None,
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
                "filing_date_ordered",
                "fee_review_requested",
                "fee_assessed",
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
    if case_id is not None:
        query = query.where(
            FilingTransaction.filing_id.in_(
                select(FilingEnvelope.id).where(FilingEnvelope.case_id == case_id),
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


def _service_manifest(value: object) -> dict[int, dict]:
    if not isinstance(value, list) or not value:
        raise ValueError("Missing document manifest")
    documents = {}
    for item in value:
        if (
            not isinstance(item, dict)
            or type(item.get("id")) is not int
            or item["id"] <= 0
            or item["id"] in documents
            or not _valid_fingerprint(item.get("sha256_hash"), item.get("file_size_bytes"))
        ):
            raise ValueError("Invalid document manifest")
        documents[item["id"]] = FilingDocumentResponse.model_validate(item).model_dump(mode="json")
    return documents


async def inspect_service_packets(
    connection: AsyncConnection,
    court_id: int | None = None,
    *,
    case_id: int | None = None,
) -> AsyncIterator[dict]:
    """Compare frozen selections with their source; later routing changes are allowed."""
    scoped = court_id is not None or case_id is not None
    filings = select(FilingEnvelope.id)
    cases = select(Case.id)
    if court_id is not None:
        filings = filings.where(FilingEnvelope.court_id == court_id)
        cases = cases.where(Case.court_id == court_id)
    if case_id is not None:
        filings = filings.where(FilingEnvelope.case_id == case_id)
        cases = cases.where(Case.id == case_id)
    sender = User.__table__.alias("delivery_sender")
    query = (
        select(
            ServicePacket.__table__,
            FilingEnvelope.id.label("filing_exists"),
            FilingEnvelope.case_id.label("filing_case_id"),
            FilingEnvelope.court_id.label("filing_court_id"),
            Case.court_id.label("case_court_id"),
            FilingTransaction.filing_id.label("source_filing_id"),
            FilingTransaction.event_type.label("source_type"),
            FilingTransaction.details.label("source_details"),
            sender.c.id.label("sender_exists"),
        )
        .select_from(ServicePacket)
        .outerjoin(FilingEnvelope, FilingEnvelope.id == ServicePacket.filing_id)
        .outerjoin(Case, Case.id == ServicePacket.case_id)
        .outerjoin(FilingTransaction, FilingTransaction.id == ServicePacket.source_transaction_id)
        .outerjoin(sender, sender.c.id == ServicePacket.actor_id)
    )
    if scoped:
        linked_packets = (
            select(ServiceRecipient.packet_id)
            .outerjoin(Notification, Notification.id == ServiceRecipient.notification_id)
            .outerjoin(ServiceContact, ServiceContact.id == ServiceRecipient.contact_id)
            .outerjoin(CaseParticipant, CaseParticipant.id == ServiceContact.participant_id)
            .where(or_(
                Notification.filing_envelope_id.in_(filings),
                ServiceContact.case_id.in_(cases),
                CaseParticipant.case_id.in_(cases),
            ))
        )
        # Include either side of a damaged cross-case link, so neither export can hide it.
        query = query.where(or_(
            ServicePacket.case_id.in_(cases),
            ServicePacket.filing_id.in_(filings),
            FilingTransaction.filing_id.in_(filings),
            ServicePacket.id.in_(linked_packets),
        ))
    last_id = None
    while packets := (await connection.execute(
        query.where(ServicePacket.id > last_id if last_id is not None else true())
        .order_by(ServicePacket.id).limit(25)
    )).mappings().all():
        ids = [packet["id"] for packet in packets]
        counts = dict((await connection.execute(
            select(ServiceRecipient.packet_id, func.count())
            .where(ServiceRecipient.packet_id.in_(ids)).group_by(ServiceRecipient.packet_id)
        )).tuples().all())
        # The sending contract permits 1..100 recipients. Count first so damaged imports
        # cannot make one packet or one page materialize an unlimited recipient collection.
        eligible = [packet_id for packet_id in ids if 1 <= counts.get(packet_id, 0) <= 100]
        recipients: dict[str, list] = {packet_id: [] for packet_id in ids}
        if eligible:
            rows = (await connection.execute(
                select(
                    ServiceRecipient.__table__,
                    Notification.id.label("notice_exists"),
                    Notification.recipient_id.label("notice_recipient"),
                    Notification.filing_envelope_id.label("notice_filing"),
                    Notification.notification_type.label("notice_type"),
                    ServiceContact.case_id.label("contact_case"),
                    *(getattr(ServiceContact, field).label(f"current_contact_{field}")
                      for field in CONTACT_SNAPSHOT_FIELDS),
                    CaseParticipant.case_id.label("participant_case"),
                    User.id.label("account_exists"),
                )
                .select_from(ServiceRecipient)
                .outerjoin(Notification, Notification.id == ServiceRecipient.notification_id)
                .outerjoin(ServiceContact, ServiceContact.id == ServiceRecipient.contact_id)
                .outerjoin(CaseParticipant, CaseParticipant.id == ServiceContact.participant_id)
                .outerjoin(User, User.id == ServiceRecipient.recipient_id)
                .where(ServiceRecipient.packet_id.in_(eligible))
                .order_by(ServiceRecipient.id)
            )).mappings().all()
            for row in rows:
                recipients[row["packet_id"]].append(row)
        for packet in packets:
            ref = {
                "kind": "service_packet", "id": packet["id"],
                "filing_id": packet["filing_id"],
                "source_transaction_id": packet["source_transaction_id"],
            }
            if _valid_fingerprint(packet["request_sha256"], 0):
                ref["selection_sha256"] = packet["request_sha256"]
            if any(packet[field] is None for field in (
                "filing_exists", "case_court_id", "source_filing_id", "sender_exists",
            )):
                yield {**ref, "status": "missing_metadata"}
                continue
            source = packet["source_details"]
            if (
                packet["filing_case_id"] != packet["case_id"]
                or packet["filing_court_id"] != packet["case_court_id"]
                or packet["source_filing_id"] != packet["filing_id"]
                or packet["source_type"] not in ("submitted", "service_recorded")
                or not isinstance(source, dict)
                or source.get("case_id") != packet["case_id"]
                or source.get("court_id") != packet["case_court_id"]
                or source.get("filing_type") not in ("subsequent", "motion", "service_only")
            ):
                yield {**ref, "status": "delivery_mismatch", "reason": "source_destination"}
                continue
            try:
                details = packet["details"]
                if not isinstance(details, dict):
                    raise ValueError("Missing packet details")
                selected = details.get("documents")
                if not isinstance(selected, list) or len(selected) > 100:
                    raise ValueError("Invalid selected documents")
                documents = _service_manifest(selected)
                original = _service_manifest(source.get("documents"))
            except ValueError:
                yield {**ref, "status": "invalid_manifest"}
                continue
            if any(
                doc["document_type_code"] in PRIVATE_DOCUMENT_TYPES or doc != original.get(doc_id)
                for doc_id, doc in documents.items()
            ):
                yield {**ref, "status": "delivery_mismatch", "reason": "document_selection"}
                continue
            targets = recipients[packet["id"]]
            if not 1 <= counts.get(packet["id"], 0) <= 100:
                yield {**ref, "status": "invalid_manifest", "reason": "recipient_count"}
                continue
            if any(
                type(target[field]) is not int or target[field] < 1
                for target in targets for field in ("contact_id", "contact_version", "recipient_id")
            ):
                yield {**ref, "status": "invalid_manifest", "reason": "recipient_selection"}
                continue
            request = {
                "filing_id": packet["filing_id"],
                "source_transaction_id": packet["source_transaction_id"],
                "documents": sorted(documents),
                "recipients": sorted(
                    (target["contact_id"], target["contact_version"]) for target in targets
                ),
            }
            fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            if (
                fingerprint != packet["request_sha256"]
                or len({row["contact_id"] for row in targets}) != len(targets)
                or len({row["recipient_id"] for row in targets}) != len(targets)
            ):
                yield {**ref, "status": "delivery_mismatch", "reason": "selection_fingerprint"}
            else:
                yield {**ref, "status": "metadata_consistent"}
            for target in targets:
                result = {
                    "kind": "service_recipient", "id": target["id"],
                    "packet_id": packet["id"], "notification_id": target["notification_id"],
                }
                snapshot = target["contact_snapshot"]
                if isinstance(snapshot, dict):
                    result["contact_sha256"] = hashlib.sha256(
                        json.dumps(snapshot, sort_keys=True).encode()
                    ).hexdigest()
                participant = (
                    snapshot.get("participant_snapshot") if isinstance(snapshot, dict) else None
                )
                if any(target[field] is None for field in (
                    "notice_exists", "contact_case", "participant_case", "account_exists",
                )):
                    result["status"] = "missing_metadata"
                elif (
                    not isinstance(snapshot, dict) or not isinstance(participant, dict)
                    or any(type(snapshot.get(field)) is not int
                           for field in ("id", "version", "user_id", "participant_id"))
                    or any(type(participant.get(field)) is not int for field in ("id", "user_id"))
                    or type(target["current_contact_version"]) is not int
                    or snapshot.get("id") != target["contact_id"]
                    or snapshot.get("version") != target["contact_version"]
                    or target["contact_version"] < 1
                    or target["current_contact_version"] < target["contact_version"]
                    or snapshot.get("user_id") != target["recipient_id"]
                    or snapshot.get("participant_id") != target["current_contact_participant_id"]
                    or participant.get("id") != snapshot.get("participant_id")
                    or participant.get("user_id") != target["recipient_id"]
                    or participant.get("is_active") is not True
                    or snapshot.get("is_active") is not True
                    or snapshot.get("method") != "electronic"
                    or not isinstance(snapshot.get("email"), str) or not snapshot["email"].strip()
                ):
                    result["status"] = "invalid_manifest"
                elif (
                    target["current_contact_version"] == target["contact_version"]
                    and snapshot != {
                        field: target[f"current_contact_{field}"]
                        for field in CONTACT_SNAPSHOT_FIELDS
                    }
                ):
                    result["status"] = "delivery_mismatch"
                elif (
                    target["contact_case"] != packet["case_id"]
                    or target["participant_case"] != packet["case_id"]
                    or target["notice_recipient"] != target["recipient_id"]
                    or target["notice_filing"] != packet["filing_id"]
                    or target["notice_type"] != NotificationType.SERVICE_OF_PROCESS
                ):
                    result["status"] = "delivery_mismatch"
                else:
                    result["status"] = "metadata_consistent"
                yield result
        last_id = packets[-1]["id"]

    # A remaining recipient row also proves a packet is missing, even when that packet
    # can no longer be found by the page scan above.
    orphans = (
        select(ServiceRecipient.id, ServiceRecipient.packet_id)
        .outerjoin(ServicePacket, ServicePacket.id == ServiceRecipient.packet_id)
        .where(ServicePacket.id.is_(None))
    )
    if scoped:
        orphans = orphans.outerjoin(
            Notification, Notification.id == ServiceRecipient.notification_id,
        ).outerjoin(ServiceContact, ServiceContact.id == ServiceRecipient.contact_id).where(or_(
            Notification.filing_envelope_id.in_(filings), ServiceContact.case_id.in_(cases),
        ))
    last_id = None
    while orphan_rows := (await connection.execute(
        orphans.where(ServiceRecipient.id > last_id if last_id is not None else true())
        .order_by(ServiceRecipient.id).limit(_BATCH_SIZE)
    )).all():
        for orphan in orphan_rows:
            yield {
                "kind": "service_recipient", "id": orphan.id,
                "packet_id": orphan.packet_id, "status": "missing_metadata",
            }
        last_id = orphan_rows[-1].id


async def run_audit(output: TextIO, court_id: int | None = None) -> int:
    started = datetime.now(UTC)
    print(
        json.dumps(
            {
                "kind": "start",
                "schema_version": 2,
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
    try:
        async with read_only_connection(settings.database_url) as connection:
            if court_id is not None and not await connection.scalar(
                select(Court.id).where(Court.id == court_id),
            ):
                raise ReadOnlyDatabaseError("The selected court does not exist")
            for inspection in (inspect_files, inspect_receipts, inspect_service_packets):
                async for result in inspection(connection, court_id):
                    counts[result["status"]] += 1
                    checked[result["kind"]] += 1
                    print(json.dumps(result), file=output, flush=True)
        complete = True
    except BrokenPipeError:
        raise
    except (SQLAlchemyError, OSError, ValueError, LookupError) as exc:
        # Database/storage exception messages can contain credentials, keys or filenames.
        print(
            json.dumps(
                {
                    "kind": "error",
                    "status": "incomplete",
                    "error_type": type(exc).__name__,
                    "message": str(exc)
                    if isinstance(exc, ReadOnlyDatabaseError)
                    else "Could not read the collection. Check database access and schema.",
                }
            ),
            file=output,
            flush=True,
        )
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
