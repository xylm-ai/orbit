import pytest

@pytest.mark.asyncio
async def test_register_creates_owner(client):
    response = await client.post("/auth/register", json={
        "family_name": "Sharma Family",
        "email": "rajesh@example.com",
        "password": "securepass123",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"family_name": "Test Family", "email": "dup@example.com", "password": "pass"}
    await client.post("/auth/register", json=payload)
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/auth/register", json={
        "family_name": "Login Family",
        "email": "login@example.com",
        "password": "mypassword",
    })
    response = await client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "family_name": "Family X",
        "email": "wrongpass@example.com",
        "password": "correct",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpass@example.com",
        "password": "wrong",
    })
    assert response.status_code == 401
