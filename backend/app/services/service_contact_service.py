"""Shared checks for reviewed service instructions and document delivery."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.case import COUNSEL_ROLES, Case, CaseParticipant
from app.models.notification import ServiceContact, ServiceMethod
from app.models.service_delivery import ServicePacket, ServiceRecipient
from app.models.user import User, UserType
from app.services.case_participant_service import participant_snapshot


def contact_snapshot(contact: ServiceContact) -> dict:
    return {
        field: getattr(contact, field)
        for field in (
            "id",
            "participant_id",
            "participant_snapshot",
            "user_id",
            "name",
            "method",
            "email",
            "address",
            "is_active",
            "authority",
            "version",
        )
    }


def routing_issues(
    case: Case,
    participant: CaseParticipant,
    account: User | None,
    contact: ServiceContact,
) -> list[str]:
    issues = []
    if not contact.is_active:
        issues.append("These service instructions are inactive.")
    if not participant.is_active or not participant.reviewed_at:
        issues.append("The participant needs an active, court-reviewed record.")
    if contact.participant_snapshot != participant_snapshot(participant):
        issues.append(
            "The participant record changed. Court review of these instructions is required.",
        )
    if contact.method == ServiceMethod.ELECTRONIC:
        if (
            not account
            or not account.is_active
            or (not account.keycloak_id and not settings.allow_demo_mode)
        ):
            issues.append(
                "Electronic routing requires an active account linked to the identity provider.",
            )
        elif (
            contact.user_id != account.id
            or not account.verified_email
            or account.verified_email != account.email.strip().lower()
            or account.verified_email != contact.email
        ):
            issues.append(
                "The service email must match the linked account's current verified email.",
            )
        if case.is_sealed and not participant.access_enabled:
            issues.append(
                "Electronic routing requires this participant's restricted-case access grant.",
            )
        if participant.role in COUNSEL_ROLES and (
            not account
            or account.user_type != UserType.ATTORNEY
            or not account.bar_number_verified
            or not account.bar_number
            or account.bar_number != participant.attorney_bar_number
        ):
            issues.append(
                "Counsel routing requires the linked attorney's matching verified bar number."
            )
    return issues


async def email_context(
    db: AsyncSession,
    notification_id: int,
) -> tuple[ServiceRecipient | None, str | None]:
    """Recheck a frozen address and authority before queuing or claiming its alert."""
    if not settings.service_delivery_enabled or not settings.email_delivery_enabled:
        return None, "Document delivery is not enabled"
    row = (
        await db.execute(
            select(ServiceRecipient, Case, ServiceContact, CaseParticipant, User)
            .join(ServicePacket, ServicePacket.id == ServiceRecipient.packet_id)
            .join(Case, Case.id == ServicePacket.case_id)
            .outerjoin(ServiceContact, ServiceContact.id == ServiceRecipient.contact_id)
            .outerjoin(CaseParticipant, CaseParticipant.id == ServiceContact.participant_id)
            .outerjoin(User, User.id == CaseParticipant.user_id)
            .where(ServiceRecipient.notification_id == notification_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        return None, "The retained document delivery is unavailable"
    recipient, case, contact, participant, account = row
    if (
        contact is None
        or participant is None
        or contact.case_id != case.id
        or participant.case_id != case.id
        or recipient.recipient_id != contact.user_id
        or recipient.contact_version != contact.version
        or recipient.contact_snapshot != contact_snapshot(contact)
    ):
        return recipient, "Service instructions changed. Review them and create a new delivery"
    issues = routing_issues(case, participant, account, contact)
    return recipient, " ".join(issues) if issues else None
