"""Tests for Apex Ledger API

Run with: pytest test_main.py -v
"""

import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.login import hash_password, create_token

client = TestClient(app)


def auth_client(username: str):
    """Returns a client with a valid JWT cookie for the given username."""
    token = create_token({"sub": username})
    client.cookies.set("access_token", token)
    return client


def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Apex Ledger" in response.text


def test_login_page_renders():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Login" in response.text


def test_signup_page_renders():
    response = client.get("/signup")
    assert response.status_code == 200


def test_wallet_requires_auth():
    client.cookies.clear()
    response = client.get("/wallet", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_wrong_password():
    response = client.post(
        "/auth/login",
        data={"username": "korner", "password": "wrongpassword"},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "Invalid" in response.text


def test_signup_creates_user():
    username = f"test_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/auth/signup",
        data={"username": username, "password": "testpass123"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "/wallet" in response.headers.get("location", "")


def test_signup_duplicate_username():
    username = f"test_{uuid.uuid4().hex[:8]}"
    client.post("/auth/signup", data={"username": username, "password": "pass123"})
    response = client.post(
        "/auth/signup",
        data={"username": username, "password": "pass123"},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "already exists" in response.text


def test_transfer_below_minimum():
    auth_client("korner")
    response = client.post(
        "/transfer",
        data={"receiver_username": "mantis_", "amount": "5", "idempotency_key": str(uuid.uuid4())},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert "10" in response.text
