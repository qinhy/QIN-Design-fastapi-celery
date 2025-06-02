import os
from typing import Optional
from .UserModel import FileSystem, Model4User, text2hash2base32Str, UsersStore

APP_INVITE_CODE = os.getenv('APP_INVITE_CODE', '123')  # Replace with appropriate default
APP_SECRET_KEY = os.getenv('APP_SECRET_KEY', 'super_secret_key')  # Caution: replace with a strong key in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))



from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
import pyotp
import qrcode

#######################################################################################
class UserModels:  
    class FileSystem(FileSystem):
        pass  
        # file_system : 
                # protocol: str
                # host: Optional[str]
                # port: Optional[int]
                # username: Optional[str]
                # password: Optional[str]
                # bucket: Optional[str]
                # root_path: Optional[str]
                # options: Optional[Dict[str, Any]]
    class User(Model4User.User):
        pass
        # username: str
        # full_name: str
        # email: EmailStr
        # hashed_password: str
        # file_system : file_system
        # role: UserRole
        # disabled: bool
        # salt: str

    class RegisterRequest(BaseModel):
        username: str
        full_name: str
        email: str
        password: str
        invite_code: str

    class EditUserRequest(BaseModel):
        # username: str
        # email: str
        file_system: Optional[FileSystem] = None
        full_name: Optional[str] = None
        new_password: Optional[str] = None
        is_remove: bool = False
        password: Optional[str] = None

    class PayloadModel(BaseModel):
        role:str = 'user'
        email: EmailStr = Field(..., description="The email address of the user")
        exp: datetime = Field(..., description="The expiration time of the token as a datetime object")
        
        def is_root(self):return self.role == 'root'

    class SessionModel(BaseModel):
        token_type: str = 'bearer'
        app_access_token: str
        user_uuid: str
        exp: datetime = Field(..., description="The expiration time of the token as a datetime object")

        def model_dump_json_dict(self)->dict:
            return json.loads(self.model_dump_json())
        
# AuthService for managing authentication
class AuthService:
    def __init__(self, user_db:UsersStore):
        self.user_db = user_db
    def add_new_user(
        self,
        username: str,
        password: str, 
        full_name: str,
        email: str,
        role: str = 'user',
        rank: list = [0],
        metadata: dict = {}
    ) -> Model4User.User:
        return self.user_db.add_new_user(
            username,
            password,
            full_name, 
            email,
            role,
            rank,
            metadata
        )
    
    def find_user_by_email(self, email: str):
        return self.user_db.find_user_by_email(email)
        
    def is_invited(self, invite_code: str = None) -> bool:
        return invite_code == APP_INVITE_CODE

    def create_access_token(self, email: str, expires_delta: timedelta = None, role: str = 'user'):
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        payload = UserModels.PayloadModel(email=email, exp=expire, role=role)
        return jwt.encode(payload.model_dump(), APP_SECRET_KEY, algorithm=ALGORITHM), payload

    def get_current_payload(self, request: Request): 
        try:
            session = UserModels.SessionModel(**request.session)
        except Exception as e:            
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
                  
        try:            
            payload = UserModels.PayloadModel(**jwt.decode(session.app_access_token, APP_SECRET_KEY, algorithms=[ALGORITHM]))
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
        
        # Expiration check
        if datetime.now(timezone.utc) > payload.exp:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")

        return payload

    def get_current_payload_if_not_local(self, request: Request):
        if request.client.host in ("127.0.0.1", "localhost"):
            return {}
        return self.get_current_payload(request)
    
    def get_current_user(self, request: Request):
        payload = self.get_current_payload(request)
        user = self.find_user_by_email(payload.email)        
        request.state.user = user
        if not user or user.disabled:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        return user
    
    def get_current_root_payload(self, request: Request): 
        payload = self.get_current_payload(request)
        if not payload.is_root():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not root")
        return payload

    def generate_otp_qr_code(self, user: UserModels.User) -> str:
        secret = text2hash2base32Str(user.email)
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name="APP")
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def verify_otp(self, otp_code: str, email: str) -> bool:
        secret = text2hash2base32Str(email)
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(otp_code)
    
    def generate_session(self, user: UserModels.User):
        access_token, payload = self.create_access_token(email=user.email, role=user.role)
        data = UserModels.SessionModel(app_access_token=access_token, user_uuid=user.get_id(), exp=payload.exp).model_dump_json_dict()
        return data
    
    def generate_login_qr(self, uid):
        uri = f"/qr?token={uid}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

# OAuth routes
class OAuthRoutes:
    def __init__(self, auth_service:AuthService):
        self.auth_service = auth_service
        self.user_db = auth_service.user_db
        self.router = APIRouter()
        self.router.post("/register")(self.register_user)
        self.router.post("/token")(self.get_token)
        self.router.post("/edit")(self.edit_user_info)
        self.router.post("/remove")(self.remove_account)
        self.router.get("/me")(self.read_users_me)
        self.router.get("/session")(self.read_session)
        self.router.get("/otp/qr")(self.get_otp_qr)
        self.router.get("/qr")(self.get_login_qr)
        self.router.get("/qr/{uid}")(self.get_login_qr_uid)
        self.router.get("/qr/login/{uid}")(self.login_qr)
        self.router.get("/otp/login/{email}/{code}")(self.get_otp_token)
        self.router.get("/icon/{icon_name}", response_class=HTMLResponse)(self.read_icon)
        self.router.get("/logout")(self.logout)

    def register_user(self, request: UserModels.RegisterRequest):
        data = request.model_dump()
        
        if not self.auth_service.is_invited(data.get('invite_code')):
            raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Invalid invite code")

        if self.auth_service.find_user_by_email(request.email) is not None:            
            raise HTTPException(status_code=400, detail="Username already exists")
        
        self.auth_service.add_new_user(**data)
        return {"status": "success", "message": "User registered successfully"}

    def get_token(self, form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
        email = form_data.username
        user = self.auth_service.find_user_by_email(email)        
        if user is None or not user.verify_password(form_data.password):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        
        data = self.auth_service.generate_session(user)
        request.session.update(data)
        return data

    def get_current_user_from_request(self, request: Request):
        if hasattr(request,'state') and hasattr(request.state,'user'):
            return request.state.user
        else:
            return self.auth_service.get_current_user(request)

    def edit_user_info(self, edit_request: UserModels.EditUserRequest,
                       request: Request):
        current_user = self.get_current_user_from_request(request)
        hash_password_fn = UserModels.User.hash_password

        try:
            new_password = edit_request.new_password or edit_request.password
            ups = {}
            if edit_request.full_name:
                ups['full_name'] = edit_request.full_name
            if edit_request.file_system:
                ups['file_system'] = json.loads(edit_request.file_system.model_dump_json())
            if new_password and edit_request.password:
                if not current_user.verify_password(edit_request.password):
                    raise HTTPException(status_code=400, detail="Incorrect password")
                ups['hashed_password'] = hash_password_fn(new_password,current_user.salt)
            if ups:
                current_user.get_controller().update(**ups)
                return {"status": "success", "message": "User info updated successfully"}
            return {"status": "success", "message": "User info not changes"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update user info: {e}")

    def remove_account(self, edit_request: UserModels.EditUserRequest,
                       request: Request):
        current_user = self.get_current_user_from_request(request)

        if not current_user.verify_password(edit_request.password):
            raise HTTPException(status_code=400, detail="Incorrect password")

        try:
            current_user.get_controller().delete()
            return {"status": "success", "message": "User account removed successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove account: {e}")

    def read_users_me(self,request:Request):
        current_user = self.get_current_user_from_request(request)
        return dict(**current_user.model_dump_exclude_sensitive(), uuid=current_user.get_id())

    def read_session(self, request: Request):
        current_user = self.get_current_user_from_request(request)

        session = UserModels.SessionModel(**request.session)
        return dict(**current_user.model_dump(), app_access_token=session.app_access_token,
                    timeout=session.exp - datetime.now(timezone.utc))

    def get_otp_qr(self,request:Request):
        current_user = self.get_current_user_from_request(request)

        return StreamingResponse(self.auth_service.generate_otp_qr_code(current_user), media_type="image/png")

    def get_login_qr(self, request: Request = None):
        return RedirectResponse(f'/qr/{str(uuid.uuid4())}')

    def get_login_qr_uid(self, uid: str, request: Request = None):
        try:
            uid = str(uuid.UUID(uid))
        except Exception as e:
            return RedirectResponse(f'/{uid}')
        
        try:
            user = self.auth_service.get_current_user(request)
            return RedirectResponse('/')
        except Exception as e:
            pass

        data = self.user_db.get(uid)
        if data is None or len(data) == 0:
            self.user_db.set(uid, {})
            return StreamingResponse(self.auth_service.generate_login_qr(uid), media_type="image/png")
        else:
            session = UserModels.SessionModel(**data)
            user = self.user_db.find(session.user_uuid)
            data = self.auth_service.generate_session(user)
            request.session.update(data)
            self.user_db.delete(uid)
            return RedirectResponse('/')

    def login_qr(self, uid: str, request: Request):
        current_user = self.get_current_user_from_request(request)

        session = UserModels.SessionModel(**request.session)
        if self.user_db.exists(uid):
            self.user_db.set(uid, session.model_dump_json_dict())
            return {"status": "success", "message": "Logged in successfully"}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    def get_otp_token(self, code: str, email: str, request: Request = None):
        con = self.auth_service.verify_otp(code, email)
        if not con: 
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
        user = self.auth_service.find_user_by_email(email)
        data = self.auth_service.generate_session(user)
        request.session.update(data)        
        return data

    def read_icon(self, icon_name: str, request: Request):
        current_user = self.get_current_user_from_request(request)
        return FileResponse(os.path.join(os.path.dirname(__file__), 'data', 'icon', icon_name))

    def logout(self, request: Request):
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