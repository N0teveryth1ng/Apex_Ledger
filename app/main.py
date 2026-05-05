from locale import currency
from re import template
from fastapi.routing import request_response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2
from contextlib import contextmanager, redirect_stderr
from fastapi import FastAPI, Request, HTTPException, Form

import redis




app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Include login routes
from .login import router as login_router
app.include_router(login_router)



#  -------------------  add postgres DB connection ------------------- 

# # schema DB config
DB_CONFIG = {
    "host":"ep-aged-moon-amjeqez7-pooler.c-5.us-east-1.aws.neon.tech",
    "database":"neondb",
    "port":"5432",
    "user":"neondb_owner",
    "password":"npg_MVRjdOQ29ElK"
}



# redis Cloud:
r = redis.Redis(
    host='redis-13392.c270.us-east-1-3.ec2.cloud.redislabs.com',
    port=13392,
    decode_responses=True,
    username="default",
    password="BmzKHwW18rDm5z09Ekm4yVtADjNtJ4QG",
)


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

SECRET_KEY = "CHANGE_ME_IN_PRODUCTION"
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

        

# send money (user.html) page
@app.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request):
    # Get username from JWT cookie, NOT from URL!
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
    
    # Try Redis cache first
    cached_bal = r.get(f"balance:{username}")
    
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
            
        # Save to Redis cache for 60 seconds
        r.setex(f"balance:{username}", 60, str(balance))
        print(f"DEBUG: Saved {username} balance to cache: {balance}")
    
    return templates.TemplateResponse(
        "user.html",
        {"request": request, "username": username, "balance": balance}
    )




# money transfer logic 
@app.post("/transfer", response_class=HTMLResponse)
def send_money(request: Request, receiver_username: str = Form(...), amount: float = Form(...)):
    # Get sender from JWT (secure), NOT from form (prevent spoofing)
    sender_username = get_current_user(request)
    if not sender_username:
        return RedirectResponse(url="/login", status_code=303)
    
    print(f"DEBUG: Transfer {amount} from '{sender_username}' to '{receiver_username}'")
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        try:
            # Validate sender
            cur.execute("SELECT balance FROM user_details WHERE username = %s", (sender_username,))
            result = cur.fetchone()
            print(f"DEBUG: Sender balance = {result}")
            if not result:
                return {"error": f"Sender '{sender_username}' not found"}
            current_bal = result[0]
            
            if amount > current_bal:
                return {"error": f"Limit exceeded. Balance: {current_bal}, Amount: {amount}"}
            
            if amount < 10:
                return HTMLResponse(f"""
                    <script>alert("Amount must be at least or more than ₹10"); window.location="/wallet?username={sender_username}";</script>
                """)

            # Platform fee
            platform_fee = amount * 0.015
            total_deduction = amount + platform_fee

            if total_deduction > current_bal:
                return {"error": f"insufficient balance. Need ₹{total_deduction} (Amount: ₹{amount} + Fee: ₹{platform_fee})"}

            cur.execute("""
                INSERT INTO platform_fee (sender_username, receiver_username, fee_amount, original_amount)
                VALUES (%s, %s, %s, %s)
            """, (sender_username, receiver_username, platform_fee, amount))
            
            print(f"DEBUG: Platform fee recorded")

            # Check receiver
            cur.execute("SELECT 1 FROM user_details WHERE username = %s", (receiver_username,))
            if not cur.fetchone():
                return {"error": f"Receiver '{receiver_username}' not found"}
            
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
            r.delete(f"balance:{sender_username}")
            r.delete(f"balance:{receiver_username}")
            
        except Exception as e:
            conn.rollback()
            print(f"DEBUG: Transfer failed, rolled back: {e}")
            return {"error": f"Transfer failed: {str(e)}"}
    
    return RedirectResponse(url=f"/wallet?username={sender_username}", status_code=303)
    





# create new user
@app.post("/create-user")
def create_user(request: Request, username: str = Form(...)):
    print(f"DEBUG: Creating user '{username}'")
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Check if user already exists
        cur.execute("SELECT 1 FROM user_details WHERE username = %s", (username,))
        result = cur.fetchone()
        print(f"DEBUG: User exists check = {result}")
        
        if result:
            print(f"DEBUG: User '{username}' already exists, redirecting to wallet")
            return RedirectResponse(url=f"/wallet?username={username}", status_code=303)
        
        # Create new user
        cur.execute("INSERT INTO user_details (username, password, balance) VALUES (%s, %s, %s)",
                   (username, 'default123', DEFAULT_BALANCE))
        conn.commit()
        print(f"DEBUG: Created user '{username}' with balance {DEFAULT_BALANCE}")
    
    # Redirect to wallet
    return RedirectResponse(url=f"/wallet?username={username}", status_code=303)




# get the user details
@app.post("/login")
def login_user(request: Request, username: str = Form(...)):

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Check if user exists
        cur.execute("SELECT balance FROM user_details WHERE username = %s", (username,))
        result = cur.fetchone()

        if not result:
            # User not found - create new user with default balance
            cur.execute("INSERT INTO user_details (username, password, balance) VALUES (%s, %s, %s)",
                       (username, 'default123', DEFAULT_BALANCE))
            conn.commit()
            print(f"DEBUG: Created new user '{username}' with balance {DEFAULT_BALANCE}")

    # Redirect to wallet page
    return RedirectResponse(url=f"/wallet?username={username}", status_code=303)



# ranks users based on their amount balance
@app.get("/rank")
def ranking(request: Request):
    
    # Try cache first - key is "rankings" (same for all users)
    cached_rankings = r.get("rankings")
    
    if cached_rankings:
        print("DEBUG: Cache hit for rankings")
        import json
        res = json.loads(cached_rankings)
    else:
        print("DEBUG: Cache miss for rankings - querying DB")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, balance FROM user_details ORDER BY balance DESC;")
            res = cur.fetchall()
            
            if not res:
                print(f"DEBUG: No rankings found")
        
        
        # Save to cache for 5 minutes 
        import json
        # Convert tuples with Decimals to lists with floats for JSON
        rankings_list = [[row[0], float(row[1])] for row in res]
        r.setex("rankings", 300, json.dumps(rankings_list))
        print(f"DEBUG: Saved rankings to cache")
    
    return templates.TemplateResponse("rank.html", {"request": request, "rankings": res})



# routing for server running
@app.get("/")
async def root():
    return {"message": "Hello WRICK from the backend server"}