from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingEnvelope, FilingStatus
from tests.test_case_participants import participants_case as participants_case


@pytest.fixture
def instruction():
    return {
        "expected_version": 0, "is_sealed": False, "confirm_public_release": True,
        "reason": "Synthetic reviewed instruction", "authority_reference": "Synthetic ADM-ACCESS-1",
    }


async def test_public_access_changes_search_docket_downloads_and_favorites(
    participants_case, instruction, db_session, api_client, stored_document,
):
    users, cases = participants_case
    staff, _foreign, filer, visitor, _admin = users
    case = cases[0]
    filing = FilingEnvelope(court_id=case.court_id, case_type_id=case.case_type_id,
        case_id=case.id, filer_id=filer.id, status=FilingStatus.ACCEPTED)
    db_session.add(filing)
    await db_session.flush()
    original = stored_document(filing.id)
    private = stored_document(filing.id, title="Private record")
    private.is_confidential = True
    db_session.add_all([original, private])
    await db_session.flush()
    digest = original.sha256_hash
    path = f"/api/v1/cases/{case.id}"
    opened = await api_client.put(path + "/public-access", json=instruction)
    assert opened.status_code == 200, opened.text
    assert opened.json() == {"is_sealed": False, "participant_version": 1}
    api_client.headers.pop("X-Demo-User-Id")
    assert (await api_client.get(path)).status_code == 200
    found = await api_client.get("/api/v1/cases/search", params={"case_number": case.case_number})
    assert found.json()["total"] == 1
    download = await api_client.get(f"/api/v1/documents/{original.id}/download")
    assert download.status_code == 200 and download.content == b"Synthetic Complaint"
    assert (await api_client.get(f"/api/v1/documents/{private.id}/download")).status_code == 403
    assert (await api_client.get(path + "/participants/history")).status_code == 401
    api_client.headers["X-Demo-User-Id"] = str(visitor.id)
    favorite = await api_client.post("/api/v1/favorites", json={"case_id": case.id})
    assert favorite.status_code == 201, favorite.text
    api_client.headers["X-Demo-User-Id"] = str(staff.id)
    restricted = {**instruction, "expected_version": 1, "is_sealed": True,
                  "confirm_public_release": False, "authority_reference": "Synthetic ADM-ACCESS-2"}
    response = await api_client.put(path + "/public-access", json=restricted)
    assert response.status_code == 200, response.text
    history = (await api_client.get(path + "/participants/history")).json()
    assert history["total"] == 2
    change = history["events"][0]
    assert change["action"] == "case.public_access_changed"
    assert change["details"]["before"]["is_sealed"] is False
    assert change["details"]["after"]["is_sealed"] is True
    assert change["details"]["actor_name"] == staff.full_name
    assert change["details"]["authority_reference"] == restricted["authority_reference"]
    assert change["details"]["reason"] == instruction["reason"]
    api_client.headers.pop("X-Demo-User-Id")
    sealed_paths = [
        path, path + "/filings",
        f"/api/v1/documents/{original.id}/download", f"/api/v1/documents/{original.id}/verify",
    ]
    for sealed_path in sealed_paths:
        expected = 401 if sealed_path.endswith("/verify") else 403
        assert (await api_client.get(sealed_path)).status_code == expected, sealed_path
    api_client.headers["X-Demo-User-Id"] = str(visitor.id)
    for sealed_path in sealed_paths:
        assert (await api_client.get(sealed_path)).status_code == 403, sealed_path
    api_client.headers.pop("X-Demo-User-Id")
    found = await api_client.get("/api/v1/cases/search", params={"case_number": case.case_number})
    assert found.json()["total"] == 0 and instruction["reason"] not in found.text
    api_client.headers["X-Demo-User-Id"] = str(visitor.id)
    assert (await api_client.get("/api/v1/favorites")).json()["total"] == 0
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    assert (await api_client.get(f"/api/v1/filings/{filing.id}")).status_code == 200
    assert (await api_client.get(f"/api/v1/documents/{original.id}/download")).status_code == 200
    assert original.sha256_hash == digest and not original.is_confidential
    assert private.is_confidential and filing.status == FilingStatus.ACCEPTED


@pytest.mark.parametrize("identity", ["other_court", "filer", "attorney", "system_admin",
                                     "inactive", "anonymous"])
async def test_public_access_requires_current_court_assignment(
    participants_case, instruction, db_session, api_client, identity,
):
    users, cases = participants_case
    identities = dict(zip(["staff", "other_court", "filer", "attorney", "system_admin"], users))
    if identity == "anonymous":
        api_client.headers.pop("X-Demo-User-Id")
    elif identity == "inactive":
        users[0].is_active = False
        await db_session.flush()
    else:
        api_client.headers["X-Demo-User-Id"] = str(identities[identity].id)
    response = await api_client.put(f"/api/v1/cases/{cases[0].id}/public-access", json=instruction)
    expected = 401 if identity in {"anonymous", "inactive"} else 403
    assert response.status_code == expected, response.text
    assert cases[0].is_sealed and cases[0].participant_version == 0


@pytest.mark.parametrize("invalid", ["reason", "authority", "confirmation", "string_flag", "extra"])
async def test_invalid_access_instructions_do_not_change_visibility(
    participants_case, instruction, db_session, api_client, invalid,
):
    case = participants_case[1][0]
    if invalid == "reason":
        instruction["reason"] = " "
    elif invalid == "authority":
        instruction["authority_reference"] = " "
    elif invalid == "confirmation":
        instruction["confirm_public_release"] = False
    elif invalid == "string_flag":
        instruction["is_sealed"] = "false"
    else:
        instruction["document_access"] = "public"
    response = await api_client.put(f"/api/v1/cases/{case.id}/public-access", json=instruction)
    assert response.status_code == 422, response.text
    assert case.is_sealed and case.participant_version == 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


async def test_participant_edits_and_public_access_invalidate_each_others_old_review(
    participants_case, instruction, api_client, db_session,
):
    users, cases = participants_case
    case = cases[0]
    path = f"/api/v1/cases/{case.id}"
    proposal = {"party_name": "Reviewed party", "role": "defendant",
                "account_email": users[2].email,
                "access_enabled": True, "expected_version": 0, "reason": "Synthetic participation"}
    participant = await api_client.post(path + "/participants", json=proposal)
    assert participant.status_code == 201, participant.text
    assert (await api_client.put(path + "/public-access", json=instruction)).status_code == 409
    instruction["expected_version"] = 1
    assert (await api_client.put(path + "/public-access", json=instruction)).status_code == 200
    proposal.update(expected_version=1, access_enabled=False)
    assert (await api_client.put(path + f"/participants/{participant.json()['id']}",
                                 json=proposal)).status_code == 409
    same = deepcopy(instruction)
    same["expected_version"] = 2
    assert (await api_client.put(path + "/public-access", json=same)).status_code == 200
    assert (await db_session.get(Case, case.id)).participant_version == 2
    instruction.update(expected_version=2, is_sealed=True, confirm_public_release=False)
    assert (await api_client.put(path + "/public-access", json=instruction)).status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    assert (await api_client.get(path)).status_code == 200, "Explicit participant grant was lost"


async def test_staff_cannot_change_access_to_a_case_they_are_party_to(
    participants_case, instruction, db_session, api_client,
):
    users, cases = participants_case
    staff = users[0]
    db_session.add(CaseParticipant(
        case_id=cases[0].id, user_id=staff.id, role=ParticipantRole.PLAINTIFF,
        party_name="Staff member as a party", access_enabled=True,
    ))
    await db_session.flush()
    response = await api_client.put(f"/api/v1/cases/{cases[0].id}/public-access", json=instruction)
    assert response.status_code == 403, response.text
    assert "Another court reviewer" in response.json()["detail"]
    assert (await db_session.get(Case, cases[0].id)).is_sealed
