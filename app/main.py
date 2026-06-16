from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2
from contextlib import contextmanager
from fastapi import FastAPI, Request, Form

import redis
import time
from typing import Any
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()


app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Include login routes
from .login import router as login_router
app.include_router(login_router)



#  -------------------  add postgres DB connection ------------------- 

# # schema DB config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "").strip(),
    "database": os.getenv("DB_NAME", "").strip(),
    "port": os.getenv("DB_PORT", "5432").strip(),
    "user": os.getenv("DB_USER", "").strip(),
    "password": os.getenv("DB_PASSWORD", "").strip(),
}



# redis Cloud:
r = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    username=os.getenv("REDIS_USERNAME", "default"),
    password=os.getenv("REDIS_PASSWORD"),
    socket_connect_timeout=0.2,
    socket_timeout=0.2
)

_redis_ok = True
_redis_last_fail = 0.0
_REDIS_COOLDOWN = 30

def rc(fn, *args, **kwargs) -> Any:
    global _redis_ok, _redis_last_fail
    if not _redis_ok and time.time() - _redis_last_fail < _REDIS_COOLDOWN:
        return None
    try:
        result = fn(*args, **kwargs)
        _redis_ok = True
        return result
    except Exception:
        _redis_ok = False
        _redis_last_fail = time.time()
        return None


# # DB connection manager 
@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG, sslmode='require')
    try:
        yield conn
    finally:
        conn.close()






#  -----------------   routing and stuff ---------------------

# render index.html templates

DEFAULT_BALANCE = 5000



# home route
@app.get("/home", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "name": "User"}
    )




# JWT verification helper
from jose import jwt, JWTError

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"

def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

# Rate limiter disabled for tests - re-enable with: from slowapi import Limiter

# send money (user.html) page
@app.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request):
    # Get username from JWT cookie, NOT from URL!
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
    
    # Try Redis cache first
    cached_bal = rc(r.get, f"balance:{username}")
    if cached_bal:
        print(f"DEBUG: Cache hit for {username}")
        balance = float(cached_bal)
    else:
        print(f"DEBUG: Cache miss for {username} - querying DB")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT balance FROM user_details WHERE username = %s", (username,))
            result = cur.fetchone()

            if not result:
                return HTMLResponse(f"<h1>Error: User '{username}' not found in database</h1><a href='/signup'>Sign up here</a>")
            balance = result[0]

        rc(r.setex, f"balance:{username}", 60, str(balance))

    # Generate idempotency key to prevent double-clicks
    import uuid
    idempotency_key = str(uuid.uuid4())
    rc(r.setex, f"idempotency:{idempotency_key}", 300, "unused")
    
    return templates.TemplateResponse(
        "user.html",
        {"request": request, "username": username, "balance": balance, "idempotency_key": idempotency_key}
    )




# money transfer logic 
@app.post("/transfer", response_class=HTMLResponse)
def send_money(request: Request, receiver_username: str = Form(...), amount: float = Form(...), idempotency_key: str = Form(...)):
    # Get sender from JWT (secure), NOT from form (prevent spoofing)
    sender_username = get_current_user(request)
    if not sender_username:
        return RedirectResponse(url="/login", status_code=303)
    
    # Check idempotency key - prevent double-clicks
    if rc(r.get, f"idempotency:{idempotency_key}") == "used":
        return HTMLResponse(f"<h1>Error</h1><p>Transfer already processed. Please check your balance.</p><a href='/wallet'>Go to Wallet</a>")
    rc(r.set, f"idempotency:{idempotency_key}", "used", ex=300)
    
    print(f"DEBUG: Transfer {amount} from '{sender_username}' to '{receiver_username}'")
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        try:
            # Validate sender
            cur.execute("SELECT balance FROM user_details WHERE username = %s", (sender_username,))
            result = cur.fetchone()
            print(f"DEBUG: Sender balance = {result}")
            if not result:
                return HTMLResponse(f"<h1>Error</h1><p>Sender '{sender_username}' not found</p><a href='/wallet'>Back to Wallet</a>")
            current_bal = result[0]
            
            if amount > current_bal:
                return HTMLResponse(f"<h1>Error</h1><p>Limit exceeded. Balance: ₹{current_bal}, Amount: ₹{amount}</p><a href='/wallet'>Back to Wallet</a>")
            
            if amount < 10:
                return HTMLResponse(f"""
                    <script>alert("Amount must be at least or more than ₹10"); window.location="/wallet?username={sender_username}";</script>
                """)

            # Platform fee
            platform_fee = amount * 0.015
            total_deduction = amount + platform_fee

            if total_deduction > current_bal:
                return HTMLResponse(f"<h1>Error</h1><p>Insufficient balance. Need ₹{total_deduction} (Amount: ₹{amount} + Fee: ₹{platform_fee})</p><a href='/wallet'>Back to Wallet</a>")

            cur.execute("""
                INSERT INTO platform_fee (sender_username, receiver_username, fee_amount, original_amount)
                VALUES (%s, %s, %s, %s)
            """, (sender_username, receiver_username, platform_fee, amount))
            
            print(f"DEBUG: Platform fee recorded")

            # Check receiver
            cur.execute("SELECT 1 FROM user_details WHERE username = %s", (receiver_username,))
            if not cur.fetchone():
                return HTMLResponse(f"<h1>Error</h1><p>Receiver '{receiver_username}' not found</p><a href='/wallet'>Back to Wallet</a>")
            
            # Update balances
            cur.execute("UPDATE user_details SET balance = balance - %s WHERE username = %s", (amount, sender_username))
            cur.execute("UPDATE user_details SET balance = balance + %s WHERE username = %s", (amount, receiver_username))
            
            # Record transaction
            cur.execute("""
                INSERT INTO transactions (sender_username, receiver_username, amount)
                VALUES (%s, %s, %s)
            """, (sender_username, receiver_username, amount))
            
            conn.commit()
            print(f"DEBUG: Transfer committed")
            
            # Clear Redis cache
            rc(r.delete, f"balance:{sender_username}")
            rc(r.delete, f"balance:{receiver_username}")
            
        except Exception as e:
            conn.rollback()
            print(f"DEBUG: Transfer failed, rolled back: {e}")
            return HTMLResponse(f"<h1>Error</h1><p>Transfer failed: {str(e)}</p><a href='/wallet'>Back to Wallet</a>")
    
    return RedirectResponse(url="/wallet", status_code=303)



# ranks users based on their amount balance
@app.get("/rank")
def ranking(request: Request):
    
    # Try cache first - key is "rankings" (same for all users)
    import json
    cached_rankings = rc(r.get, "rankings")
    if cached_rankings:
        print("DEBUG: Cache hit for rankings")
        res = json.loads(cached_rankings)
    else:
        res = None

    if res is None:
        print("DEBUG: Cache miss for rankings - querying DB")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, balance FROM user_details ORDER BY balance DESC;")
            res = cur.fetchall()

            if not res:
                print(f"DEBUG: No rankings found")

        try:
            rankings_list = [[row[0], float(row[1])] for row in res]
            r.setex("rankings", 300, json.dumps(rankings_list))
            print(f"DEBUG: Saved rankings to cache")
        except Exception:
            pass
    
    return templates.TemplateResponse("rank.html", {"request": request, "rankings": res})



# Root route - landing page
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "name": "User"}
    )