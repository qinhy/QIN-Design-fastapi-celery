from pydantic import BaseModel, EmailStr, Field
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status, Request
from jose import JWTError, jwt
import requests
from datetime import datetime, timedelta, timezone
import secrets
import os
from .UserModel import UsersStore,Model4User

INVITE_CODE = os.environ.get('APP_INVITE_CODE', '123')
SECRET_KEY = os.environ.get('APP_SECRET_KEY', secrets.token_urlsafe(32))

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
SESSION_DURATION = ACCESS_TOKEN_EXPIRE_MINUTES * 60
UVICORN_PORT = 8000
EX_IP = requests.get('https://v4.ident.me/').text

db = UsersStore()
db.redis_backend()
router = APIRouter()
#######################################################################################
class UserModels:
    class User(Model4User.User):
        pass
        # username:str
        # full_name: str
        # role:str = 'user'
        # hashed_password:str # text2hash2base64Str(password),
        # email:str
        # disabled: bool=False

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

    class PayloadModel(BaseModel):
        email: EmailStr = Field(..., description="The email address of the user")
        exp: datetime = Field(..., description="The expiration time of the token as a datetime object")

    class SessionModel(BaseModel):
        token_type: str = 'bearer'
        app_access_token: str
        user_uuid: str
        
# AuthService for managing authentication
class AuthService:
    @staticmethod
    def create_access_token(email: str, expires_delta: timedelta = None):
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        payload = UserModels.PayloadModel(email=email,exp=expire)
        return jwt.encode(payload.model_dump(), SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    async def get_current_user(request: Request): 
        try:
            session = UserModels.SessionModel(**request.session)
        except Exception as e:            
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
          
        try:            
            payload = UserModels.PayloadModel(**jwt.decode(session.app_access_token, SECRET_KEY, algorithms=[ALGORITHM]))
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

        user = db.find_user_by_email(payload.email)
        if not user or user.disabled:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        
        return user

# OAuth routes
class OAuthRoutes:
    @staticmethod
    @router.get("/register", response_class=HTMLResponse)
    async def get_register_page():
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'templates', "register.html"))

    @staticmethod
    @router.post("/register")
    async def register_user(request: UserModels.RegisterRequest):
        # 1. **Email Format Validation**:
        # 2. **Password Strength Validation**:
        # 3. **Checking for Missing Fields**:
        # 4. **Duplicate Username/Email Checks**:
        # 5. **Invite Code Expiration**:
        # 6. **Validation for Other Fields**:
        # 7. **Rate Limiting**:
        # 8. **Cross-Site Request Forgery (CSRF) Tokens**:

        data = request.model_dump()
        
        if data.pop('invite_code') != INVITE_CODE:
            raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Invalid invite code")

        if db.find_user_by_email(request.email) is not None:            
            raise HTTPException(status_code=400, detail="Username already exists")
        
        data['hashed_password'] = UserModels.User.hash_password(data.pop('password'))
        db.add_new_user(**data)
        return {"status": "success", "message": "User registered successfully"}

    @staticmethod
    @router.post("/token")
    def get_token(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
        email = form_data.username

        user = db.find_user_by_email(email)        
        if user is None  or not user.check_password(form_data.password):
            raise HTTPException(status_code=400, detail="Incorrect username or password")

        access_token = AuthService.create_access_token(email=email)
        data = UserModels.SessionModel(app_access_token=access_token,user_uuid=user.get_id()).model_dump()
        request.session.update(data)
        
        return data
        
    @staticmethod
    @router.get("/login", response_class=HTMLResponse)
    async def get_login_page():
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'templates', "login.html"))

    @staticmethod
    @router.get("/edit", response_class=HTMLResponse)
    async def get_edit_page(current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'templates', "edit.html"))
    
    @staticmethod
    @router.get("/", response_class=HTMLResponse)
    async def read_home(current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'templates', 'edit.html'))
    
    @staticmethod
    @router.post("/edit")
    async def edit_user_info(request: UserModels.EditUserRequest, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        if not current_user.check_password(request.password):
            raise HTTPException(status_code=400, detail="Incorrect password")

        try:
            new_password = request.new_password or request.password
            current_user.get_controller().update(
                full_name=request.full_name,
                hashed_password=UserModels.User.hash_password(new_password),
            )
            return {"status": "success", "message": "User info updated successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update user info: {e}")

    @staticmethod
    @router.post("/remove")
    async def remove_account(request: UserModels.EditUserRequest, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        if not current_user.check_password(request.password):
            raise HTTPException(status_code=400, detail="Incorrect password")

        try:
            current_user.get_controller().delete()
            return {"status": "success", "message": "User account removed successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove account: {e}")


    @staticmethod
    @router.get("/me")
    async def read_users_me(current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return dict(**current_user.model_dump(),uuid=current_user.get_id())

    @staticmethod
    @router.get("/session")
    def read_session(request: Request, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return dict(**current_user.model_dump(),app_access_token=request.session.get("app_access_token", ""))

    @router.get("/icon/{icon_name}", response_class=HTMLResponse)
    async def read_icon(icon_name: str, current_user: UserModels.User = Depends(AuthService.get_current_user)):
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'icon', icon_name))

    @staticmethod
    @router.get("/logout")
    async def logout(request: Request):
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
