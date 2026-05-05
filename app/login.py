# imports
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
import psycopg2
from contextlib import contextmanager

# Database config 
DB_CONFIG = {
    "host": "ep-aged-moon-amjeqez7-pooler.c-5.us-east-1.aws.neon.tech",
    "database": "neondb",
    "port": "5432",
    "user": "neondb_owner",
    "password": "npg_MVRjdOQ29ElK"
}

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG, sslmode='require')
    try:
        yield conn
    finally:
        conn.close()

def get_user_from_db(username: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users_cred WHERE username = %s", (username,))
        result = cur.fetchone()
        if result:
            return {"id": result[0], "username": result[1], "password_hash": result[2]}
        return None

def create_user_in_db(username: str, password_hash: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO users_cred (username, password_hash) VALUES (%s, %s)", (username, password_hash))
        conn.commit()

def create_user_in_details(username: str, password: str = "default123", balance: float = 5000.00):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO user_details (username, password, balance) VALUES (%s, %s, %s)", 
                    (username, password, balance))
        conn.commit()




SECRET_KEY = "CHANGE_ME_IN_PRODUCTION"          # Use an env var in real apps
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


router = APIRouter()
templates = Jinja2Templates(directory="templates")





# ------------------ auth -----------------------
# hash password
def hash_password(password: str):
    return pwd_context.hash(password)

# verify password
def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)


# ceate access token
def create_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# authenticate the user
def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user_from_db(username)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user

# Show login page
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Handle login POST (returns JWT token as cookie)
@router.post("/auth/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user_from_db(username)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})
    
    # Create JWT token
    token = create_token({"sub": username})
    
    # Redirect to wallet with token in cookie
    response = RedirectResponse(url=f"/wallet?username={username}", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600)
    return response

# Show signup page
@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

# Handle signup POST
@router.post("/auth/signup")
def signup_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Check if user exists
    existing = get_user_from_db(username)
    if existing:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username already exists"})
    
    # Hash password and create user
    hashed = hash_password(password)
    create_user_in_db(username, hashed)
    
    # Also create in user_details for wallet (default balance 5000)
    create_user_in_details(username, password, 5000.00)
    
    # Create JWT token
    token = create_token({"sub": username})
    
    # Redirect to wallet
    response = RedirectResponse(url=f"/wallet?username={username}", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600)
    return response


