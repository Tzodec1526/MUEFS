"""Export or verify a private case archive. Requires operator database and storage access."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import and_, or_, select, text, union
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.court import CaseType, Court
from app.models.court_calendar import CourtCalendar
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification, NotificationDeliveryEvent, ServiceContact
from app.models.payment import Payment
from app.models.user import User
from app.readonly_database import ReadOnlyDatabaseError, read_only_connection
from app.services import document_service
from app.storage_audit import inspect_receipts

_CHUNK = 64 * 1024
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_README = b"""PRIVATE MUEFS CASE ARCHIVE - FORMAT 1

This archive contains nonpublic case records and personal information.
Keep it in storage approved for those records.

manifest.json lists every archive entry, its SHA-256 fingerprint and uncompressed
size, along with record counts, source schema revision and export times.
records/<table>.jsonl contains UTF-8 JSON, one source record per line. Source IDs
are preserved, timestamps use UTC, and monetary amounts are recorded in cents.
User records contain limited profile information, not identity-provider state.

objects/<sha256> contains exact stored document bytes. Each document/copy record
identifies its object_path and MIME type. Original, superseded, confidential and
prepared public copies are included when linked to the selected case. Objects
with identical fingerprints share one archive entry; source records remain separate.

The archive is a records-transfer package, not an automatic restore or certified
court copy. Checksums establish consistency, not authenticity. Retain the reported
manifest SHA-256 separately, and compare it when verifying the received archive.
Verification does not extract or execute any document.
"""
_ACTOR_FIELDS = {
    "actor_id",
    "filer_id",
    "reviewer_id",
    "user_id",
    "recipient_id",
    "created_by",
    "published_by",
    "payer_id",
    "judge_id",
}


class CaseExportError(ValueError):
    """A safe diagnostic that identifies incomplete or inconsistent evidence."""


def _json(value: object) -> bytes:
    def encode(item: object) -> str:
        if isinstance(item, datetime):
            return item.replace(tzinfo=item.tzinfo or UTC).astimezone(UTC).isoformat()
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError(f"Unsupported record value: {type(item).__name__}")

    return (json.dumps(value, default=encode, ensure_ascii=False, sort_keys=True) + "\n").encode()


async def export_case(case_id: int, output: Path) -> dict:
    if case_id <= 0:
        raise CaseExportError("The case ID must be positive")
    if output.exists():
        raise CaseExportError("The output already exists; choose a new archive path")
    entries: dict[str, dict] = {}
    counts: dict[str, int] = {}
    objects: dict[str, tuple[str, int]] = {}
    started = datetime.now(UTC)
    async with read_only_connection(settings.database_url) as connection:
        case = (
            (await connection.execute(select(Case.__table__).where(Case.id == case_id)))
            .mappings()
            .one_or_none()
        )
        if case is None:
            raise CaseExportError("The selected case does not exist")
        revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        if not revision:
            raise CaseExportError("The database has no recorded schema revision")
        async for result in inspect_receipts(connection, case_id=case_id):
            if result["status"] != "metadata_consistent":
                raise CaseExportError(
                    "The case has missing or inconsistent retained document evidence"
                )
        filing_ids = select(FilingEnvelope.id).where(FilingEnvelope.case_id == case_id)
        outside_payment = await connection.scalar(
            select(Payment.id)
            .join(FilingEnvelope, FilingEnvelope.payment_id == Payment.id)
            .where(
                FilingEnvelope.case_id == case_id,
                Payment.envelope_id.is_not(None),
                Payment.envelope_id.not_in(filing_ids),
            )
            .limit(1)
        )
        if outside_payment is not None:
            raise CaseExportError("A legacy payment reference points outside the selected case")
        document_ids = select(FilingDocument.id).where(FilingDocument.envelope_id.in_(filing_ids))
        copy_ids = select(DocumentPublicCopy.id).where(
            DocumentPublicCopy.document_id.in_(document_ids)
        )
        payment_filter = or_(
            Payment.envelope_id.in_(filing_ids),
            Payment.id.in_(
                select(FilingEnvelope.payment_id).where(FilingEnvelope.case_id == case_id)
            ),
        )
        notice_ids = select(Notification.id).where(Notification.filing_envelope_id.in_(filing_ids))
        queries = [
            (Court, Court.id == case["court_id"]),
            (Case, Case.id == case_id),
            (
                CaseType,
                CaseType.id.in_(
                    union(
                        select(Case.case_type_id).where(Case.id == case_id),
                        select(FilingEnvelope.case_type_id).where(
                            FilingEnvelope.case_id == case_id
                        ),
                    )
                ),
            ),
            (FilingEnvelope, FilingEnvelope.id.in_(filing_ids)),
            (FilingDocument, FilingDocument.id.in_(document_ids)),
            (DocumentPublicCopy, DocumentPublicCopy.id.in_(copy_ids)),
            (FilingTransaction, FilingTransaction.filing_id.in_(filing_ids)),
            (CaseParticipant, CaseParticipant.case_id == case_id),
            (Payment, payment_filter),
            (ServiceContact, ServiceContact.case_id == case_id),
            (Notification, Notification.id.in_(notice_ids)),
            (NotificationDeliveryEvent, NotificationDeliveryEvent.notification_id.in_(notice_ids)),
            (CourtCalendar, CourtCalendar.court_id == case["court_id"]),
            (
                AuditLog,
                or_(
                    and_(AuditLog.entity_type == "case", AuditLog.entity_id == case_id),
                    and_(
                        AuditLog.entity_type == "filing_envelope",
                        AuditLog.entity_id.in_(filing_ids),
                    ),
                    and_(
                        AuditLog.entity_type == "filing_document",
                        AuditLog.entity_id.in_(document_ids),
                    ),
                    and_(
                        AuditLog.entity_type == "document_public_copy",
                        AuditLog.entity_id.in_(copy_ids),
                    ),
                    and_(
                        AuditLog.entity_type == "payment",
                        AuditLog.entity_id.in_(select(Payment.id).where(payment_filter)),
                    ),
                    and_(
                        AuditLog.entity_type == "notification", AuditLog.entity_id.in_(notice_ids)
                    ),
                ),
            ),
        ]
        user_sources = [
            select(model.__table__.c[field]).where(predicate)
            for model, predicate in queries
            for field in _ACTOR_FIELDS
            if field in model.__table__.c
        ]
        queries.append((User, User.id.in_(union(*user_sources))))
        descriptor, temporary_name = tempfile.mkstemp(prefix=".case-export-", dir=output.parent)
        temporary = Path(temporary_name)
        try:
            with (
                os.fdopen(descriptor, "w+b") as archive_file,
                ZipFile(
                    archive_file,
                    "w",
                    compression=ZIP_DEFLATED,
                    compresslevel=6,
                    allowZip64=True,
                ) as archive,
            ):
                for model, predicate in queries:
                    table = model.__table__
                    query = select(table)
                    if model is User:
                        # Accounts provide attribution, not credentials or identity-provider state.
                        columns = [
                            User.id,
                            User.first_name,
                            User.last_name,
                            User.email,
                            User.user_type,
                            User.bar_number,
                            User.bar_number_verified,
                            User.is_active,
                        ]
                        query = select(*columns)
                    path = f"records/{table.name}.jsonl"
                    digest, size, count = hashlib.sha256(), 0, 0
                    async with connection.stream(
                        query.where(predicate)
                        .order_by(
                            *table.primary_key.columns,
                        )
                        .execution_options(yield_per=250)
                    ) as rows:
                        with archive.open(path, "w", force_zip64=True) as target:
                            async for row in rows.mappings():
                                record = dict(row)
                                if (
                                    model is FilingEnvelope
                                    and record["court_id"] != case["court_id"]
                                ):
                                    raise CaseExportError(
                                        "A filing's court does not match the selected case"
                                    )
                                if model in (FilingDocument, DocumentPublicCopy):
                                    fingerprint, length = (
                                        record["sha256_hash"],
                                        record["file_size_bytes"],
                                    )
                                    if (
                                        not re.fullmatch(r"[0-9a-f]{64}", fingerprint or "")
                                        or type(length) is not int
                                        or length < 0
                                    ):
                                        raise CaseExportError(
                                            "A document has an invalid fingerprint or size"
                                        )
                                    key = record["file_key"]
                                    if key in objects and objects[key] != (fingerprint, length):
                                        raise CaseExportError(
                                            "Conflicting metadata refers to one stored object"
                                        )
                                    objects[key] = (fingerprint, length)
                                    record["object_path"] = f"objects/{fingerprint}"
                                payload = _json(record)
                                target.write(payload)
                                digest.update(payload)
                                size += len(payload)
                                count += 1
                    entries[path] = {"sha256": digest.hexdigest(), "size_bytes": size}
                    counts[table.name] = count
                for key, (fingerprint, length) in objects.items():
                    path = f"objects/{fingerprint}"
                    digest, size = hashlib.sha256(), 0
                    # PDFs and office archives are already compressed. Preserve their bytes
                    # without spending CPU recompressing them; JSON records remain deflated.
                    object_target = (
                        archive.open(ZipInfo(path), "w", force_zip64=True)
                        if path not in entries
                        else None
                    )
                    try:
                        with closing(document_service.download_document(key)) as source:
                            while chunk := source.read(_CHUNK):
                                if object_target is not None:
                                    object_target.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                    finally:
                        if object_target is not None:
                            object_target.close()
                    if digest.hexdigest() != fingerprint or size != length:
                        raise CaseExportError(
                            "Stored bytes do not match a document's retained fingerprint or size"
                        )
                    entries[path] = {"sha256": fingerprint, "size_bytes": size}
                archive.writestr("README.txt", _README)
                entries["README.txt"] = {
                    "sha256": hashlib.sha256(_README).hexdigest(),
                    "size_bytes": len(_README),
                }
                manifest = _json(
                    {
                        "format": "muefs-case-archive",
                        "format_version": 1,
                        "case_id": case_id,
                        "court_id": case["court_id"],
                        "schema_revision": revision,
                        "export_started_at": started,
                        "finished_at": datetime.now(UTC),
                        "counts": counts,
                        "entries": entries,
                        "classification": "private; includes nonpublic records",
                    }
                )
                if len(manifest) > _MAX_MANIFEST_BYTES:
                    raise CaseExportError(
                        "The case exceeds the archive format's manifest size limit"
                    )
                archive.writestr("manifest.json", manifest)
            # Publish only a complete archive. A competing exporter cannot overwrite it.
            os.link(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "status": "exported",
        "case_id": case_id,
        "counts": counts,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }


def verify_archive(path: Path, manifest_sha256: str | None = None) -> dict:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise CaseExportError("The archive has duplicate entries or no manifest")
        with archive.open("manifest.json") as source:
            manifest_bytes = source.read(_MAX_MANIFEST_BYTES + 1)
        if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
            raise CaseExportError("The manifest exceeds the archive format's size limit")
        fingerprint = hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_sha256 is not None and fingerprint != manifest_sha256:
            raise CaseExportError("The manifest does not match the separately retained fingerprint")
        manifest = json.loads(manifest_bytes)
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "muefs-case-archive"
            or manifest.get("format_version") != 1
        ):
            raise CaseExportError("Unsupported archive format")
        entries = manifest["entries"]
        if not isinstance(entries, dict) or set(names) != {*entries, "manifest.json"}:
            raise CaseExportError("The archive contents do not match the manifest")
        for name, expected in entries.items():
            if not re.fullmatch(
                r"README\.txt|records/[a-z_]+\.jsonl|objects/[0-9a-f]{64}", name
            ) or not isinstance(expected, dict):
                raise CaseExportError("The archive contains an invalid entry")
            if (
                type(expected.get("size_bytes")) is not int
                or expected["size_bytes"] < 0
                or archive.getinfo(name).file_size != expected["size_bytes"]
                or not isinstance(expected.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])
            ):
                raise CaseExportError("An archive entry has an invalid size or fingerprint")
            digest, size = hashlib.sha256(), 0
            with archive.open(name) as source:
                while chunk := source.read(_CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
            if digest.hexdigest() != expected["sha256"] or size != expected["size_bytes"]:
                raise CaseExportError(
                    "An archive entry does not match its recorded fingerprint or size"
                )
    return {
        "status": "verified",
        "case_id": manifest["case_id"],
        "entries": len(entries),
        "manifest_sha256": fingerprint,
        "expected_fingerprint_checked": manifest_sha256 is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser(
        "export", help="Create a new archive; never overwrite an existing file"
    )
    export.add_argument("--case-id", required=True, type=int)
    export.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser(
        "verify", help="Verify checksums without extracting or accessing the database"
    )
    verify.add_argument("archive", type=Path)
    verify.add_argument(
        "--manifest-sha256", help="Fingerprint retained separately from the archive"
    )
    args = parser.parse_args()
    try:
        result = (
            asyncio.run(export_case(args.case_id, args.output))
            if args.command == "export"
            else verify_archive(args.archive, args.manifest_sha256)
        )
        print(json.dumps(result))
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        BadZipFile,
        SQLAlchemyError,
        BotoCoreError,
        ClientError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc)
                    if isinstance(exc, (CaseExportError, ReadOnlyDatabaseError))
                    else "Export or verification failed. Check the database, storage and archive.",
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
