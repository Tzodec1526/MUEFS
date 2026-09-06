"""Capture a real API review before exercising submission in workflow tests."""


async def submission_review(client, filing_id):
    response = await client.get(f"/api/v1/filings/{filing_id}")
    assert response.status_code == 200, response.text
    return {"expected_submission_token": response.json()["submission_token"]}
