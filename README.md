<div align="center">

# ⬡ Apex Ledger

**A secure peer-to-peer payment system built with FastAPI**

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-NeonDB-336791?style=flat-square&logo=postgresql)
![Redis](https://img.shields.io/badge/Redis-Cache-DC382D?style=flat-square&logo=redis)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat-square&logo=docker)
![CI](https://github.com/N0teveryth1ng/Apex_Ledger/actions/workflows/ci.yml/badge.svg)

</div>

---

## Overview

Apex Ledger is a full-stack payment wallet application that allows users to register, log in, and transfer money to other users in real time. It is built with a focus on security, performance, and clean backend architecture.

**Key capabilities:**
- JWT-based authentication (stateless, cookie-stored)
- Real-time balance transfers with platform fee calculation
- Redis caching with circuit breaker fallback
- Idempotency keys to prevent duplicate transfers
- Containerized with Docker, tested with pytest, CI via GitHub Actions

---

## Screenshots

| Login | Wallet | Leaderboard |
|-------|--------|-------------|
| ![Login](https://github.com/user-attachments/assets/9c0c1a64-2e8c-4498-8278-a3deee58774d) | ![Wallet](https://github.com/user-attachments/assets/ef4ecc68-ac08-4bb1-88e0-0c5f9422221b) | ![Rank](https://github.com/user-attachments/assets/f366f73e-91ef-4f11-9eaa-a60f4270ae3f) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Client                           │
│                  (Browser / HTTP)                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI App                          │
│                                                         │
│   ┌─────────────┐        ┌──────────────────────────┐  │
│   │  JWT Auth   │        │     Route Handlers        │  │
│   │  Middleware │───────▶│  /login  /signup          │  │
│   └─────────────┘        │  /wallet /transfer /rank  │  │
│                          └──────────┬───────────────┬┘  │
└─────────────────────────────────────┼───────────────┼───┘
                                      │               │
                    ┌─────────────────▼──┐    ┌───────▼──────────┐
                    │   Redis Cache      │    │   PostgreSQL      │
                    │   (Balance Cache)  │    │   (NeonDB)        │
                    │   Circuit Breaker  │    │                   │
                    │   TTL: 60s         │    │  users_cred       │
                    └────────────────────┘    │  user_details     │
                                              │  transactions     │
                                              │  platform_fee     │
                                              └───────────────────┘
```

---

## Request Flow — Transfer

```
User submits transfer form
        │
        ▼
JWT cookie verified → get sender username
        │
        ▼
Idempotency key checked (Redis) → prevent double-clicks
        │
        ▼
Sender balance validated (PostgreSQL)
        │
        ▼
1.5% platform fee calculated and recorded
        │
        ▼
Receiver existence verified
        │
        ▼
Atomic balance update (sender - amount, receiver + amount)
        │
        ▼
Transaction recorded → Redis cache invalidated
        │
        ▼
Redirect to /wallet with updated balance
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | FastAPI | API routing, request handling |
| Database | PostgreSQL (NeonDB) | Persistent user & transaction data |
| Cache | Redis Cloud | Balance caching, idempotency keys |
| Auth | JWT (python-jose) | Stateless session management |
| Password | passlib + bcrypt | Secure password hashing |
| Templates | Jinja2 | Server-side HTML rendering |
| Container | Docker | Reproducible deployment |
| CI | GitHub Actions | Automated test runs on push |
| Testing | pytest + httpx | Integration test suite |

---

## Database Schema

```sql
-- User credentials (hashed passwords)
CREATE TABLE users_cred (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Wallet balances
CREATE TABLE user_details (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(255),
    balance DECIMAL(12,2) DEFAULT 5000.00
);

-- Transfer history
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    sender_username VARCHAR(50),
    receiver_username VARCHAR(50),
    amount DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Platform fee ledger
CREATE TABLE platform_fee (
    id SERIAL PRIMARY KEY,
    sender_username VARCHAR(50),
    receiver_username VARCHAR(50),
    fee_amount DECIMAL(12,2),
    original_amount DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## API Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/` | Landing page | No |
| GET | `/login` | Login page | No |
| POST | `/auth/login` | Authenticate user, set JWT cookie | No |
| GET | `/signup` | Signup page | No |
| POST | `/auth/signup` | Register new user | No |
| GET | `/wallet` | Wallet dashboard | Yes (JWT) |
| POST | `/transfer` | Send money to another user | Yes (JWT) |
| GET | `/rank` | Leaderboard by balance | No |

---

## Security

- **JWT tokens** stored as `httponly` cookies — not accessible via JavaScript
- **bcrypt** password hashing with 72-byte truncation
- **Sender identity from JWT** — never trusted from form input (prevents spoofing)
- **Idempotency keys** — prevent duplicate transfers from double-clicks
- **Environment variables** — all credentials in `.env`, never hardcoded
- **SSL enforced** on all database connections

---

## Running Locally

### Prerequisites
- Python 3.11+
- Docker (optional)

### With Python

```bash
# Clone the repo
git clone https://github.com/N0teveryth1ng/Apex_Ledger.git
cd Apex_Ledger

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Fill in your DB and Redis credentials

# Run the server
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

### With Docker

```bash
docker build -t apexledger .
docker run --env-file .env -p 8000:8000 apexledger
```

---

## Environment Variables

Create a `.env` file with the following:

```env
SECRET_KEY=your-secret-key

DB_HOST=your-db-host
DB_NAME=your-db-name
DB_PORT=5432
DB_USER=your-db-user
DB_PASSWORD=your-db-password

REDIS_HOST=your-redis-host
REDIS_PORT=6379
REDIS_USERNAME=default
REDIS_PASSWORD=your-redis-password
```

---

## Running Tests

```bash
pytest test_main.py -v
```

Tests cover:
- Home and auth page rendering
- Wallet redirect without JWT
- Login with wrong password
- Signup flow and duplicate username prevention
- Transfer minimum amount validation

---

## CI/CD

GitHub Actions runs the full test suite on every push to `main`.

```
push to main
     │
     ▼
Install Python 3.11 + dependencies
     │
     ▼
Run pytest test_main.py -v
     │
     ▼
Pass ✓ or Fail ✗
```

---

<div align="center">
Built by <a href="https://github.com/N0teveryth1ng">N0teveryth1ng</a>
</div>
