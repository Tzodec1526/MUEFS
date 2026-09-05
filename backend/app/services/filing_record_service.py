"""Record receipts and decisions atomically with their filing transition."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.court import Court
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.payment import Payment
from app.models.user import User
from app.schemas.filing import FilingDocumentResponse
from app.services.notification_service import notify_filing_status_change


async def record_transaction(
    db: AsyncSession, filing: FilingEnvelope, event_type: str, actor_id: int,
    *, reason: str | None = None, idempotency_key: str | None = None,
    details: dict | None = None,
) -> FilingTransaction:
    actor = await db.get(User, actor_id)
    court = await db.get(Court, filing.court_id)
    now = datetime.now(UTC)
    details = dict(details or {})
    if reason:
        details["reason"] = reason
    if event_type in ("submitted", "service_recorded"):
        case = await db.get(Case, filing.case_id) if filing.case_id else None
        payment = await db.get(Payment, filing.payment_id) if filing.payment_id else None
        now = filing.submitted_at or now
        details = {
            "court_id": filing.court_id,
            "court_name": court.name if court else f"Court #{filing.court_id}",
            "case_id": filing.case_id,
            "case_number": case.case_number if case else None,
            "case_title": filing.case_title,
            "filing_type": filing.filing_type,
            "filing_description": filing.filing_description,
            "fee_waiver_requested": filing.fee_waiver_requested,
            "filing_date_basis": filing.filing_date_basis,
            # Financial hardship text is deliberately not copied into notices/receipts.
            "payment": {
                "id": payment.id, "amount_cents": payment.amount_cents,
                "transaction_ref": payment.transaction_ref,
                "is_simulated": bool(payment.description and
                                     payment.description.startswith("[SIMULATED")),
            } if payment else None,
            "documents": [FilingDocumentResponse.model_validate(doc).model_dump(mode="json")
                          for doc in filing.documents],
        }
        for doc in filing.documents:
            if doc.retained_at is None:
                doc.retained_at = now
    elif event_type == "accepted":
        details.update(case_id=filing.case_id, cms_case_number=filing.cms_case_number,
                       cms_filing_id=filing.cms_filing_id,
                       filing_date_basis=filing.filing_date_basis)

    transaction = FilingTransaction(
        filing_id=filing.id, submission_number=filing.submission_count,
        event_type=event_type, actor_id=actor_id,
        actor_name=f"{actor.first_name} {actor.last_name}" if actor else f"User #{actor_id}",
        occurred_at=now, details=details, idempotency_key=idempotency_key,
    )
    db.add(transaction)
    await db.flush()
    if event_type != "cms_failed":
        notice = await notify_filing_status_change(
            db, filer_id=filing.filer_id, filing_id=filing.id, status=event_type,
            court_name=court.name if court else f"Court #{filing.court_id}",
            case_title=filing.case_title,
            reason=("Open the private filing history to read the decision."
                    if event_type.startswith("waiver_") else reason),
        )
        notice.body += (
            f"\nTransaction: {transaction.id}\nRecorded (UTC): {now.isoformat()}"
        )
    return transaction
