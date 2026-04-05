import pytest

async def _owner_setup(client, suffix: str):
    email = f"owner-{suffix}@test.com"
    res = await client.post("/auth/register", json={"family_name": f"Family {suffix}", "email": email, "password": "pass"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entity = await client.post("/entities", json={"name": "Entity", "type": "individual"}, headers=headers)
    return token, entity.json()["id"], headers

async def _second_user(client, suffix: str):
    email = f"advisor-{suffix}@test.com"
    res = await client.post("/auth/register", json={"family_name": f"Advisor Family {suffix}", "email": email, "password": "pass"})
    return res.json()["access_token"], email

@pytest.mark.asyncio
async def test_owner_can_invite_advisor(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv1")
    advisor_token, advisor_email = await _second_user(client, "inv1")

    res = await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": advisor_email, "role": "advisor"},
        headers=owner_headers,
    )
    assert res.status_code == 201
    assert res.json()["role"] == "advisor"

@pytest.mark.asyncio
async def test_invited_advisor_sees_entity(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv2")
    advisor_token, advisor_email = await _second_user(client, "inv2")

    await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": advisor_email, "role": "advisor"},
        headers=owner_headers,
    )

    res = await client.get("/entities", headers={"Authorization": f"Bearer {advisor_token}"})
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert entity_id in ids

@pytest.mark.asyncio
async def test_non_owner_cannot_invite(client):
    _, entity_id, owner_headers = await _owner_setup(client, "inv3")
    advisor_token, advisor_email = await _second_user(client, "inv3")

    await client.post(f"/entities/{entity_id}/invite", json={"email": advisor_email, "role": "advisor"}, headers=owner_headers)

    third_token, third_email = await _second_user(client, "inv3b")
    res = await client.post(
        f"/entities/{entity_id}/invite",
        json={"email": third_email, "role": "viewer"},
        headers={"Authorization": f"Bearer {advisor_token}"},
    )
    assert res.status_code == 403
