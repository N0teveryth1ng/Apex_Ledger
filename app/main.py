from locale import currency
from re import template
from fastapi.routing import request_response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2
from contextlib import contextmanager, redirect_stderr
from fastapi import FastAPI, Request, HTTPException, Form

app = FastAPI()
templates = Jinja2Templates(directory="templates")




#  -------------------  add postgres DB connection ------------------- 

# # schema DB config
DB_CONFIG = {
    "host":"ep-aged-moon-amjeqez7-pooler.c-5.us-east-1.aws.neon.tech",
    "database":"neondb",
    "port":"5432",
    "user":"neondb_owner",
    "password":"npg_MVRjdOQ29ElK"
}


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




# send money (user.html) page
@app.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request, username: str = "Wrick"):
    
    with get_db_connection() as conn:
        cur = conn.cursor() 
        cur.execute("SELECT balance FROM user_details WHERE username = %s", (username,))
        result = cur.fetchone()

        if not result:
            return {"error": f"User '{username}' not found in database"}
        balance = result[0]
   
    return templates.TemplateResponse(
        "user.html",
        {"request": request, "username": username, "balance": balance}
    )




# money transfer logic 
@app.post("/transfer", response_class=HTMLResponse)
def send_money(request: Request, sender_username: str = Form(...), receiver_username: str = Form(...), amount: float = Form(...)):
    print(f"DEBUG: Transfer {amount} from '{sender_username}' to '{receiver_username}'")
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT balance FROM user_details WHERE username = %s", (sender_username,))
        result = cur.fetchone()
        print(f"DEBUG: Sender balance = {result}")
        if not result:
            return {"error": f"Sender '{sender_username}' not found"}
        current_bal = result[0]
        
        # if current bal < amt we're sending then it will not transfer 
        if amount > current_bal:
            return {"error": f"Limit exceeded. Balance: {current_bal}, Amount: {amount}"}
        
        # minimum balance prevention ($10) 
        if amount < 10:
            return HTMLResponse(f"""
                <script>alert("Amount must be at least or more than ₹10"); window.location="/wallet?username={sender_username}";</script>
            """)

        # Check receiver exists
        cur.execute("SELECT 1 FROM user_details WHERE username = %s", (receiver_username,))
        if not cur.fetchone():
            return {"error": f"Receiver '{receiver_username}' not found"}
        
        # Update balances
        cur.execute("UPDATE user_details SET balance = balance - %s WHERE username = %s", (amount, sender_username))
        cur.execute("UPDATE user_details SET balance = balance + %s WHERE username = %s", (amount, receiver_username))
        
        # records in the transactions 
        cur.execute("""
            INSERT INTO transactions (sender_username, receiver_username, amount)
            VALUES (%s, %s, %s)
        """, (sender_username, receiver_username, amount))
        
        conn.commit()
        print(f"DEBUG: Transfer committed")
    
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

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT username, balance FROM user_details ORDER BY balance DESC;")
        res = cur.fetchall()

        if not res:
           print(f"details not found") 

    return templates.TemplateResponse("rank.html", {"request": request, "rankings": res})



# routing for server running
@app.get("/")
async def root():
    return {"message": "Hello WRICK from the backend server"}