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
    payload = {"family_name": "Test Family", "email": "dup@example.com", "password": "pass1234"}
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
        "password": "correct12",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpass@example.com",
        "password": "wrong123",
    })
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_2fa_setup_and_verify(client):
    reg = await client.post("/auth/register", json={
        "family_name": "2FA Family",
        "email": "totp@example.com",
        "password": "pass1234",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    setup = await client.post("/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    import pyotp
    code = pyotp.TOTP(secret).now()
    verify = await client.post("/auth/2fa/verify", json={"totp_code": code}, headers=headers)
    assert verify.status_code == 204

@pytest.mark.asyncio
async def test_login_requires_2fa_after_setup(client):
    reg = await client.post("/auth/register", json={
        "family_name": "2FA Required",
        "email": "needstotp@example.com",
        "password": "pass1234",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    setup = await client.post("/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    import pyotp
    code = pyotp.TOTP(secret).now()
    await client.post("/auth/2fa/verify", json={"totp_code": code}, headers=headers)

    no_code = await client.post("/auth/login", json={"email": "needstotp@example.com", "password": "pass1234"})
    assert no_code.status_code == 401

    with_code = await client.post("/auth/login", json={
        "email": "needstotp@example.com",
        "password": "pass1234",
        "totp_code": pyotp.TOTP(secret).now(),
    })
    assert with_code.status_code == 200
