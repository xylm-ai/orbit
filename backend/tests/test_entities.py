import pytest

async def _register_and_token(client, email: str, family: str = "Test Family") -> str:
    res = await client.post("/auth/register", json={"family_name": family, "email": email, "password": "pass1234"})
    return res.json()["access_token"]

@pytest.mark.asyncio
async def test_owner_can_create_entity(client):
    token = await _register_and_token(client, "owner1@test.com", "Family 1")
    res = await client.post(
        "/entities",
        json={"name": "Rajesh Sharma", "type": "individual", "pan": "ABCDE1234F"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Rajesh Sharma"
    assert data["type"] == "individual"

@pytest.mark.asyncio
async def test_owner_sees_own_entities(client):
    token = await _register_and_token(client, "owner2@test.com", "Family 2")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/entities", json={"name": "Entity A", "type": "huf"}, headers=headers)
    await client.post("/entities", json={"name": "Entity B", "type": "company"}, headers=headers)
    res = await client.get("/entities", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2
