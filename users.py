from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import APIRouter, Depends, HTTPException, status, Request
from jose import JWTError, jwt
import requests
import bcrypt
from datetime import datetime, timedelta, timezone
import uuid
import sqlite3
import secrets
import re
import os
import base64
import sys
import uuid
import hashlib
import numpy as np


def hash2uuid(text: str, salt: bytes = b'', ite: int = 10**6):
    return str(uuid.UUID(bytes=hashlib.pbkdf2_hmac('sha256', text.encode(), salt, ite, dklen=16)))


def remove_hyphen(uuid: str):
    return uuid.replace('-', '')


def restore_hyphen(uuid: str):
    if len(uuid) != 32:
        raise ValueError("Invalid UUID format")
    return f'{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}'


def list2base64Str(l: list):
    if l is None:
        l = []
    t = np.asarray(l)
    return base64.b64encode(t).decode()


def base64Str2list(bs: str):
    r = base64.decodebytes(bs.encode())
    return np.frombuffer(r).tolist()


def print_char(content: str) -> str:
    sys.stdout.write(f'{content}')
    sys.stdout.flush()
    return content

# os.environs
# OPENAI_GPT_MODEL = 'gpt-3.5-turbo-16k',gpt-4-0613','gpt-3.5-turbo',
# APP_BASE_URL = '',
# APP_DATABASE = /path/to/'database.db',
# APP_INVITE_CODE = '123',
# APP_LANG = 'ja'
# SERPER_API_KEY =
# OPENAI_API_KEY =
# FILEBROWSERPASS = 'admin password'

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

DATABASE = os.environ.get('APP_DATABASE', os.path.join(
    os.path.split(__file__)[0], 'data', 'database.db'))
INVITE_CODE = os.environ.get('APP_INVITE_CODE', '123')

SECRET_KEY = secrets.token_urlsafe(32)
SESSION_DURATION = ACCESS_TOKEN_EXPIRE_MINUTES * 60
UVICORN_PORT = 8000
EX_IP = requests.get('https://v4.ident.me/').text


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT UNIQUE,
            hashed_password TEXT,
            user_uuid TEXT UNIQUE,
            disabled BOOLEAN
        );
        """)


init_db()
router = APIRouter()
# docker_client = docker.from_env()
#######################################################################################

class UserModels:
    class User(BaseModel):
        username: str = ''
        full_name: str = ''
        email: str = ''
        hashed_password: str = ''
        user_uuid: str = ''
        disabled: bool = False
        # CREATE TABLE IF NOT EXISTS users (
        #     username TEXT PRIMARY KEY,
        #     full_name TEXT,
        #     email TEXT,
        #     hashed_password TEXT,
        #     user_uuid TEXT UNIQUE,
        #     disabled BOOLEAN
        # );

        @staticmethod
        def from_list(l):
            data = dict(zip(UserModels.User().model_dump().keys(), l))
            return UserModels.User(**data)

    class RegisterRequest(BaseModel):
        username: str
        full_name: str
        email: str
        password: str
        invite_code: str

    class EditUserRequest(BaseModel):
        # username: str
        full_name: str
        # email: str
        new_password: str
        is_remove: bool
        password: str


class UserService:
    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    @staticmethod
    def get_user_by_email(email: str):
        with sqlite3.connect(DATABASE) as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user:
                return UserModels.User.from_list(user)

    def get_user_by_uuid(id: str):
        with sqlite3.connect(DATABASE) as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE user_uuid=?", (id,)).fetchone()
            if user:
                return UserModels.User.from_list(user)

    @staticmethod
    def format_email(email: str) -> str:
        EMAIL_REGEX = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        if not re.match(EMAIL_REGEX, email):
            raise ValueError("Invalid email format")
        return email.lower().strip()

    @staticmethod
    def insert_user(username, full_name, email, hashed_password, user_uuid, disabled=False):
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("INSERT INTO users (username, full_name, email, hashed_password, user_uuid, disabled) VALUES (?, ?, ?, ?, ?, ?)",
                         (username, full_name, email, hashed_password, user_uuid, disabled))
        return True

    @staticmethod
    def update_user_info(full_name, email, hashed_password, disabled=False):
        """Update user information."""
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("UPDATE users SET full_name=?, email=?, hashed_password=?, disabled=?",
                         (full_name, email, hashed_password, disabled))

    @staticmethod
    def remove_user(email: str):
        with sqlite3.connect(DATABASE) as conn:
            conn.execute("DELETE FROM users WHERE email=?", (email,))


class AuthService:

    @staticmethod
    def create_access_token(*, data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + \
                timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    async def get_current_user(request: Request):
        token = request.session.get("app_access_token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("email")
            if email is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid authentication credentials")

        user = UserService.get_user_by_email(email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    @staticmethod
    async def is_current_user_active(current_user: UserModels.User = Depends(get_current_user)):
        if current_user.disabled:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user


class OAuthRoutes:
    @staticmethod
    @router.get("/register", response_class=HTMLResponse)
    async def get_register_page():
        return FileResponse(os.path.join(os.path.split(__file__)[0], 'data', 'templates', "register.html"))

    @staticmethod
    @router.post("/register")
    async def register_user(request: UserModels.RegisterRequest):
        formatted_email = UserService.format_email(request.email)
        hashed_password = UserService.hash_password(request.password)
        user_uuid = remove_hyphen(
            hash2uuid(f'{formatted_email}{hashed_password}'))  # str(uuid.uuid4())
        if request.invite_code != INVITE_CODE:
            raise HTTPException(
                status_code=400, detail="invite code not valid")

        try:
            res = []
            res.append(UserService.insert_user(
                request.username, request.full_name, formatted_email, hashed_password, user_uuid))
            return {"status": "success", "message": "User registered successfully"}
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=400, detail="Username already exists")

    @staticmethod
    @router.post("/edit")
    async def edit_user_info(request: UserModels.EditUserRequest, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        """Edit user information."""
        # First, verify the password
        if not UserService.verify_password(request.password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect password")
        try:
            # Update user info
            if request.new_password == '':
                request.new_password = request.password
            hashed_password = UserService.hash_password(request.new_password)
            UserService.update_user_info(
                request.full_name, current_user.email, hashed_password, current_user.disabled)
            return {"status": "success", "message": "User info updated successfully"}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to update user info: {e}")

    @staticmethod
    @router.post("/remove")
    async def remove_account(request: UserModels.EditUserRequest, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        # First, verify the password
        if not UserService.verify_password(request.password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect password")
        try:
            UserService.remove_user(current_user.email)
            return {"status": "success", "message": "User account removed successfully"}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to remove account: {e}")

    @staticmethod
    @router.get("/login", response_class=HTMLResponse)
    async def get_login_page():
        return FileResponse(os.path.join(os.path.split(__file__)[0], 'data', 'templates', "login.html"))

    @staticmethod
    @router.get("/edit", response_class=HTMLResponse)
    async def get_edit_page():
        return FileResponse(os.path.join(os.path.split(__file__)[0], 'data', 'templates', "edit.html"))

    @staticmethod
    @router.post("/token")
    def get_token(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
        print(form_data.__dict__)
        email = form_data.username
        user = UserService.get_user_by_email(email)
        print(user)
        if not user or not UserService.verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=400, detail="Incorrect username or password")

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = AuthService.create_access_token(
            data={"email": email}, expires_delta=access_token_expires
        )
        request.session["uuid"] = user.user_uuid
        request.session["app_access_token"] = access_token

        print(access_token)
        user_uuid = user.user_uuid
        return {"app_access_token": access_token, "token_type": "bearer", "uuid": user.user_uuid}

    @staticmethod
    @router.get("/me")
    async def read_users_me(current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return {**current_user.model_dump()}

    @staticmethod
    @router.get("/session")
    def read_session(request: Request, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return {**current_user.model_dump(), "app_access_token": request.session.get("app_access_token", "")}

    @staticmethod
    @router.get("/", response_class=HTMLResponse)
    async def read_home(current_user: UserModels.User = Depends(AuthService.get_current_user)):
        this_dir, this_filename = os.path.split(__file__)
        return FileResponse(os.path.join(this_dir, 'data', 'templates', 'edit.html'))

    @router.get("/icon/{icon_name}", response_class=HTMLResponse)
    async def read_home(request: Request, icon_name: str, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        this_dir, this_filename = os.path.split(__file__)
        return FileResponse(os.path.join(this_dir, 'data', 'icon', icon_name))

    @staticmethod
    @router.get("/logout")
    async def logout(request: Request, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        # Clear the session
        request.session.clear()
        return {"status": "logged out"}

# app = FastAPI(title="app")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[ '*',],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSION_DURATION)

# app.include_router(router, prefix="", tags=["users"])
