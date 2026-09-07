"""Court-wide external receipt activity, derived from retained filing transactions."""

import csv
import io
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id, lock_current_user
from app.database import get_db
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.schemas.payment import PaymentActivity, PaymentRegister, PaymentRegisterTotals
from app.services.access_service import user_has_court_administrator_assignment

router = APIRouter(tags=["External payment records"])


@router.get("/clerk/payment-register", response_model=PaymentRegister)
async def payment_register(
    court_id: int = Query(ge=1),
    date_from: date = Query(),
    date_to: date = Query(),
    timezone: str = Query(max_length=100),
    include_simulated: bool = False,
    page: int = Query(1, ge=1),
    output_format: Literal["json", "csv"] = Query("json", alias="format"),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    await lock_current_user(db, user_id)
    if not await user_has_court_administrator_assignment(db, user_id, court_id):
        raise HTTPException(403, "An administrator assignment to this court is required")
    if not 0 <= (date_to - date_from).days < 31 or date_to == date.max:
        raise HTTPException(422, "Choose an inclusive date range of at most 31 days")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, "Choose a valid IANA time zone") from exc
    try:
        start = datetime.combine(date_from, time.min, zone).astimezone(UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(UTC)
    except OverflowError as exc:
        raise HTTPException(
            422, "The selected dates fall outside this time zone's supported range",
        ) from exc
    payment = FilingTransaction.details["payment"]
    receipt = payment["external_receipt"]
    amount = payment["amount_cents"].as_integer()
    events = select(
        FilingTransaction.id.label("event_id"), FilingTransaction.filing_id,
        FilingTransaction.occurred_at,
        case((FilingTransaction.event_type == "fee_payment_reversed", -amount),
             else_=amount).label("amount_cents"),
        payment["is_simulated"].as_boolean().label("is_simulated"),
    ).join(FilingEnvelope, FilingEnvelope.id == FilingTransaction.filing_id).where(
        FilingEnvelope.court_id == court_id,
        FilingTransaction.event_type.in_(("fee_payment_recorded", "fee_payment_reversed")),
        FilingTransaction.occurred_at >= start, FilingTransaction.occurred_at < end,
    )
    if not include_simulated:
        events = events.where(payment["is_simulated"].as_boolean().is_(False))
    activity = events.cte("activity")
    aggregates = [func.count().label("total")]
    for simulated, prefix in ((False, ""), (True, "simulated_")):
        for kind, sign in (("credits", 1), ("reversals", -1)):
            aggregates.append(func.coalesce(func.sum(case((
                activity.c.is_simulated.is_(simulated) & (activity.c.amount_cents * sign > 0),
                activity.c.amount_cents * sign,
            ), else_=0)), 0).label(f"{prefix}{kind}_cents"))
    totals = select(*aggregates).select_from(activity).cte("totals")
    page_query = select(activity)
    if output_format == "csv":
        # Refuse oversized exports without fetching receipt text that will be discarded.
        page_query = page_query.join(totals, true()).where(totals.c.total <= 5000)
    page_ids = page_query.order_by(
        activity.c.occurred_at.desc(), activity.c.event_id.desc(),
    ).offset(0 if output_format == "csv" else (page - 1) * 50).limit(
        5000 if output_format == "csv" else 50,
    ).cte("page_ids")
    # Receipt text and reasons are needed only for the selected page/export rows.
    page_rows = select(
        page_ids, FilingTransaction.event_type, FilingTransaction.actor_id,
        FilingTransaction.actor_name, payment["id"].as_integer().label("payment_id"),
        receipt["system"].as_string().label("receipt_system"),
        receipt["reference"].as_string().label("receipt_reference"),
        receipt["received_at"].as_string().label("received_at"),
        FilingTransaction.details["reason"].as_string().label("reason"),
    ).select_from(page_ids.join(
        FilingTransaction, FilingTransaction.id == page_ids.c.event_id,
    )).cte("rows")
    # One statement gives totals and page rows the same snapshot, including an empty page.
    records = (await db.execute(select(totals, page_rows).select_from(
        totals.outerjoin(page_rows, true()),
    ).order_by(page_rows.c.occurred_at.desc(), page_rows.c.event_id.desc()))).mappings().all()
    first = records[0]
    if output_format == "csv" and first["total"] > 5000:
        raise HTTPException(422, "This period exceeds 5,000 entries. Choose a shorter date range")
    report = PaymentRegister(
        court_id=court_id, date_from=date_from, date_to=date_to, timezone=timezone,
        range_start=start, range_end=end, generated_at=datetime.now(UTC),
        include_simulated=include_simulated, total=first["total"], page=page,
        totals=PaymentRegisterTotals(
            credits_cents=first["credits_cents"], reversals_cents=first["reversals_cents"],
        ),
        simulated_totals=PaymentRegisterTotals(
            credits_cents=first["simulated_credits_cents"],
            reversals_cents=first["simulated_reversals_cents"],
        ),
        entries=[PaymentActivity.model_validate(row) for row in records if row["event_id"]],
    )
    if output_format == "json":
        return report

    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    fields = tuple(PaymentActivity.model_fields)
    writer.writerow(("court_id", "period_start_utc", "period_end_utc", "period_timezone",
                     "generated_at_utc", "currency", *fields))
    for entry in report.entries:
        values = (court_id, start.isoformat(), end.isoformat(), timezone,
                  report.generated_at.isoformat(), "USD", *entry.model_dump(mode="json").values())
        # Retained text can resemble a spreadsheet formula. Keep its original value in JSON;
        # CSV quotes delimiters/newlines and prefixes dangerous text with an apostrophe.
        writer.writerow(
            "'" + value if isinstance(value, str) and value.lstrip().startswith(
                ("=", "+", "-", "@", "＝", "＋", "－", "＠"),
            ) else value
            for value in values
        )
    return Response(
        content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="court-{court_id}-receipts-{date_from}-{date_to}.csv"'
            ),
        },
    )
