"""Court search applies literal filters before stable pagination."""

import pytest

from app.models.court import Court, CourtType


async def test_anonymous_directory_includes_every_court_with_only_search_fields(
    db_session, api_client,
):
    courts = [
        Court(name=f"Court {i:03}", county="Wayne" if i % 2 else "Alcona",
              court_type=CourtType.CIRCUIT, is_efiling_enabled=i != 101,
              cms_type="Synthetic CMS", address="123 Court Street")
        for i in range(102)
    ]
    db_session.add_all(courts)
    await db_session.flush()

    response = await api_client.get("/api/v1/courts/directory")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {"id": court.id, "name": court.name, "county": court.county}
        for court in sorted(courts, key=lambda court: (court.county, court.name, court.id))
    ]


@pytest.mark.parametrize("field", ["q", "county"])
async def test_court_search_treats_wildcards_as_text(db_session, api_client, field):
    literal = Court(name=r"100%_\Court", county=r"100%_\County", court_type=CourtType.CIRCUIT)
    ordinary = Court(name="Ordinary Court", county="Ordinary", court_type=CourtType.CIRCUIT)
    db_session.add_all([literal, ordinary])
    await db_session.flush()
    response = await api_client.get("/api/v1/courts", params={field: "%_\\"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [c["id"] for c in response.json()["courts"]] == [literal.id]


async def test_court_filters_and_count_share_stable_pages(db_session, api_client):
    matching = [
        Court(name="Same Court", county="Wayne", court_type=CourtType.CIRCUIT) for _ in range(5)
    ]
    db_session.add_all([
        *matching,
        Court(name="Same Court", county="Wayne", court_type=CourtType.CIRCUIT,
              is_efiling_enabled=False),
        Court(name="Same Court", county="Wayne", court_type=CourtType.COURT_OF_APPEALS),
        Court(name="Other Court", county="Wayne", court_type=CourtType.CIRCUIT),
    ])
    await db_session.flush()
    response = await api_client.get("/api/v1/courts", params={
        "q": "Same", "county": "Wayne", "tier": "trial", "page": 2, "page_size": 2,
    })
    assert response.json()["total"] == 5
    assert [c["id"] for c in response.json()["courts"]] == [c.id for c in matching[2:4]]
