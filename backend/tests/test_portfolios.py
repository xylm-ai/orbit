import pytest

async def _setup(client, email: str):
    res = await client.post("/auth/register", json={"family_name": "PF Family", "email": email, "password": "pass"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entity = await client.post("/entities", json={"name": "Raj", "type": "individual"}, headers=headers)
    return token, entity.json()["id"], headers

@pytest.mark.asyncio
async def test_create_pms_portfolio(client):
    _, entity_id, headers = await _setup(client, "pfowner@test.com")
    res = await client.post(
        f"/entities/{entity_id}/portfolios",
        json={"type": "pms", "provider_name": "Motilal Oswal", "account_number": "MO12345"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["provider_name"] == "Motilal Oswal"

@pytest.mark.asyncio
async def test_list_portfolios(client):
    _, entity_id, headers = await _setup(client, "pflist@test.com")
    await client.post(f"/entities/{entity_id}/portfolios", json={"type": "equity", "provider_name": "Zerodha"}, headers=headers)
    await client.post(f"/entities/{entity_id}/portfolios", json={"type": "mf", "provider_name": "CAMS"}, headers=headers)
    res = await client.get(f"/entities/{entity_id}/portfolios", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
