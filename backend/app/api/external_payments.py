"""Credit verified external receipts without moving funds or rewriting their evidence."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id, lock_current_user
from app.api.params import Page, RecordId
from app.config import settings
from app.database import get_db
from app.models.filing import FilingEnvelope
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.payment import (
    ExternalPaymentRequest,
    ExternalPaymentReversal,
    PaymentRecord,
    PaymentRecords,
)
from app.services import access_service, audit_service
from app.services.fee_assessment_service import fee_state
from app.services.filing_record_service import record_transaction
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/filings", tags=["External payment records"])


async def lock_payment_filing(
    db: AsyncSession, filing_id: int, user_id: int
) -> tuple[FilingEnvelope, User]:
    actor = await lock_current_user(db, user_id)
    filing = await db.scalar(select(FilingEnvelope).where(FilingEnvelope.id == filing_id)
                             .with_for_update().execution_options(populate_existing=True))
    if filing is None:
        raise HTTPException(404, "Filing not found")
    if (
        actor.id == filing.filer_id
        or not await access_service.user_has_court_administrator_assignment(
            db,
            actor.id,
            filing.court_id,
        )
    ):
        raise HTTPException(403, "A separate administrator assigned to this court is required")
    if not settings.external_payments_enabled:
        raise HTTPException(503, "External payment recording is not enabled for this deployment")
    return filing, actor


@router.get("/{filing_id}/payments", response_model=PaymentRecords)
async def list_payment_records(
    filing_id: RecordId,
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    filing = (await db.execute(select(
        FilingEnvelope.filer_id, FilingEnvelope.court_id, FilingEnvelope.payment_version,
    ).where(FilingEnvelope.id == filing_id).with_for_update(read=True))).one_or_none()
    if filing is None:
        raise HTTPException(404, "Filing not found")
    if filing.filer_id != user_id and not await access_service.user_is_court_staff_for_court(
        db,
        user_id,
        filing.court_id,
    ):
        raise HTTPException(403, "Not authorized to view this filing's payments")
    scope = Payment.envelope_id == filing_id
    return PaymentRecords(
        payments=[
            PaymentRecord.model_validate(payment)
            for payment in await db.scalars(
                select(Payment)
                .where(scope)
                .order_by(Payment.id.desc())
                .offset((page - 1) * 25)
                .limit(25)
            )
        ],
        total=await db.scalar(select(func.count()).select_from(Payment).where(scope)) or 0,
        page=page,
        payment_version=filing.payment_version,
    )


@router.post("/{filing_id}/external-payments", response_model=PaymentRecord, status_code=201)
async def record_external_payment(
    filing_id: RecordId,
    data: ExternalPaymentRequest,
    request: Request,
    response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    filing, actor = await lock_payment_filing(db, filing_id, user_id)
    payload = data.model_dump(mode="json")
    payload["received_at"] = data.received_at.astimezone(UTC).isoformat()
    fingerprint = hashlib.sha256(
        json.dumps([filing_id, actor.id, payload], sort_keys=True).encode()
    ).hexdigest()
    previous = await db.scalar(
        select(Payment).where(Payment.external_request_key == str(idempotency_key))
    )
    if previous is not None:
        if (
            previous.envelope_id != filing_id
            or (previous.external_receipt or {}).get("request_sha256") != fingerprint
        ):
            raise HTTPException(
                409, "This request key was already used for a different payment record"
            )
        response.status_code = 200
        return PaymentRecord.model_validate(previous)

    if data.received_at > datetime.now(UTC):
        raise HTTPException(422, "The external receipt time cannot be in the future")
    fees = await fee_state(db, filing, actor.id)
    if (
        data.expected_fee_version != fees.version
        or data.expected_payment_version != fees.payment_version
    ):
        raise HTTPException(
            409,
            "The fee or payment record changed. Refresh and review it before recording a credit",
        )
    if not fees.can_record_external_payment or fees.balance_due_cents is None:
        raise HTTPException(
            409,
            "No unpaid court-assessed or denied-waiver amount is available for this credit",
        )
    if data.amount_cents > fees.balance_due_cents:
        raise HTTPException(409, "The credit exceeds this filing's current amount due")
    receipt_key = hashlib.sha256(
        json.dumps(
            [
                filing.court_id,
                " ".join(data.receipt_system.casefold().split()),
                " ".join(data.receipt_reference.casefold().split()),
            ]
        ).encode()
    ).hexdigest()
    basis = {
        "source": fees.source,
        "assessment_id": fees.assessment_id,
        "version": fees.version,
        "authority_reference": fees.authority_reference,
        "items": [item.model_dump() for item in fees.items],
        "total_cents": fees.total_cents,
        "previous_paid_cents": fees.paid_cents,
    }
    receipt = {
        "system": data.receipt_system,
        "reference": data.receipt_reference,
        "received_at": payload["received_at"],
        "recorded_by": actor.id,
        "recorded_by_name": f"{actor.first_name} {actor.last_name}",
        "reason": data.reason,
        "request_sha256": fingerprint,
    }
    try:
        async with db.begin_nested():
            version = await db.scalar(
                update(FilingEnvelope)
                .where(
                    FilingEnvelope.id == filing_id,
                    FilingEnvelope.payment_version == data.expected_payment_version,
                )
                .values(payment_version=FilingEnvelope.payment_version + 1)
                .returning(FilingEnvelope.payment_version)
            )
            if version is None:
                raise HTTPException(
                    409, "The payment record changed. Refresh before recording a credit"
                )
            payment = Payment(
                envelope_id=filing_id,
                payer_id=filing.filer_id,
                amount_cents=data.amount_cents,
                status=PaymentStatus.COMPLETED,
                is_simulated=settings.allow_demo_mode,
                transaction_ref=f"MUEFS-EXT-{idempotency_key}",
                processed_at=data.received_at,
                external_request_key=str(idempotency_key),
                external_receipt_key=receipt_key,
                external_receipt=receipt,
                fee_basis=basis,
                description="Credit from an external receipt; no funds moved by this portal",
            )
            db.add(payment)
            await db.flush()
            filing.payment_id = payment.id
            await record_transaction(
                db,
                filing,
                "fee_payment_recorded",
                actor.id,
                reason=data.reason,
                details={
                    "payment": {
                        "id": payment.id,
                        "amount_cents": payment.amount_cents,
                        "transaction_ref": payment.transaction_ref,
                        "is_simulated": payment.is_simulated,
                        "fee_basis": basis,
                        "external_receipt": receipt,
                    }
                },
            )
            await audit_service.log_action(
                db,
                user_id=actor.id,
                action="record_external_payment",
                entity_type="payment",
                entity_id=payment.id,
                details={
                    "filing_id": filing_id,
                    "amount_cents": payment.amount_cents,
                    "external_receipt": receipt,
                },
                ip_address=client_ip(request),
                user_agent=client_user_agent(request),
            )
    except IntegrityError as exc:
        # The unique receipt key arbitrates competing credits on different filings.
        duplicate = await db.scalar(
            select(Payment).where(
                Payment.external_receipt_key == receipt_key,
                Payment.status == PaymentStatus.COMPLETED,
            )
        )
        if duplicate is None:
            if await db.scalar(select(Payment.id).where(
                Payment.external_request_key == str(idempotency_key),
            )) is not None:
                raise HTTPException(
                    409, "This request key was already used for another payment",
                ) from exc
            raise
        raise HTTPException(
            409,
            f"This receipt is already credited to filing #{duplicate.envelope_id}. "
            "Review its payment records before entering another credit",
        ) from exc
    return PaymentRecord.model_validate(payment)


@router.post("/{filing_id}/external-payments/{payment_id}/reverse", response_model=PaymentRecord)
async def reverse_external_payment(
    filing_id: RecordId,
    payment_id: RecordId,
    data: ExternalPaymentReversal,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    filing, actor = await lock_payment_filing(db, filing_id, user_id)
    payment = await db.scalar(
        select(Payment)
        .where(
            Payment.id == payment_id,
            Payment.envelope_id == filing_id,
            Payment.external_request_key.is_not(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payment is None:
        raise HTTPException(404, "External payment credit not found")
    # A lost reversal response can be retried without another balance change or event.
    if payment.status == PaymentStatus.REVERSED:
        return PaymentRecord.model_validate(payment)
    if payment.status != PaymentStatus.COMPLETED:
        raise HTTPException(409, "This payment is not an active external credit")
    async with db.begin_nested():
        version = await db.scalar(
            update(FilingEnvelope)
            .where(
                FilingEnvelope.id == filing_id,
                FilingEnvelope.payment_version == data.expected_payment_version,
            )
            .values(payment_version=FilingEnvelope.payment_version + 1)
            .returning(FilingEnvelope.payment_version)
        )
        if version is None:
            raise HTTPException(
                409, "The payment record changed. Refresh before reversing the credit"
            )
        payment.status = PaymentStatus.REVERSED
        await db.flush()
        await record_transaction(
            db,
            filing,
            "fee_payment_reversed",
            actor.id,
            reason=data.reason,
            details={
                "payment": {
                    "id": payment.id,
                    "amount_cents": payment.amount_cents,
                    "transaction_ref": payment.transaction_ref,
                    "is_simulated": payment.is_simulated,
                    "external_receipt": payment.external_receipt,
                }
            },
        )
        await audit_service.log_action(
            db,
            user_id=actor.id,
            action="reverse_external_payment",
            entity_type="payment",
            entity_id=payment.id,
            details={
                "filing_id": filing_id,
                "amount_cents": payment.amount_cents,
                "reason": data.reason,
            },
            ip_address=client_ip(request),
            user_agent=client_user_agent(request),
        )
    return PaymentRecord.model_validate(payment)
