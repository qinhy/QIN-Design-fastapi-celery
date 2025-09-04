from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, IO, List, Literal, Optional, Union
import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator

from .FileSystem import FileSystem
 
def text2hash2base32Str(text: str) -> str:
    hash_uuid = hashlib.sha256(text.encode()).digest()
    return base64.b32encode(hash_uuid).decode('utf-8').rstrip('=')

def text2hash2base64Str(text: str, salt_bytes: bytes = b'', ite: int = 10**6) -> str:
    hashed = hashlib.pbkdf2_hmac('sha256', text.encode(), salt_bytes, ite, dklen=16)
    return base64.b64encode(hashed).decode()

def text2hash(text: str, salt_bytes: bytes = b'', ite: int = 10**6) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', text.encode(), salt_bytes, ite, dklen=16)

def text2hash2uuid(text: str, salt_bytes: bytes = b'', ite: int = 10**6) -> str:
    return str(uuid.UUID(bytes=text2hash(text, salt_bytes, ite)))

def remove_hyphen(uuid_str: str) -> str:
    return uuid_str.replace('-', '')

def restore_hyphen(uuid_str: str) -> str:
    if len(uuid_str) != 32:
        raise ValueError("Invalid UUID format")
    return f'{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}'

def format_email(email: str) -> str:
    return email.lower().strip()

class UserRole:
    root = 'root'
    admin = 'admin'
    user = 'user'

class User(BaseModel):
    """
    User model representing a system user with authentication and role capabilities.
    """

    username: str = Field(...,example="johndoe",
        description="Unique username for the user, can be used for login.",
    )

    full_name: str = Field(...,example="John Doe",
        description="The full name of the user.",
    )

    email: EmailStr = Field(...,example="john.doe@example.com",
        description="User's email address, used for identification and communication.",
    )

    hashed_password: str = Field(...,example="aGVsbG9oYXNoZWRwYXNzd29yZA==",  # just a fake base64 example
        description="The hashed password of the user, stored securely.",
    )

    select_file_system : int = Field(0,
        description="Remote File System configuration, designed for use with fsspec-compatible backends.",
    )

    file_systems : List[FileSystem] = Field([],
        description="Remote File System configurations",
    )

    role: str = Field(default=UserRole.user,example="user",
        description="The role assigned to the user, determining permissions.",
    )

    disabled: bool = Field(default=False,example=False,
        description="Indicates whether the user's account is disabled.",
    )

    salt: str = Field(...,example="dGhpc2lzYXNhbHRzYW1wbGU=",
        description="Base64-encoded per-user salt used for password hashing.",
    )


    # --- Config ---
    class Config:
        validate_assignment = True
        extra = 'forbid'
    
    def decode_salt(self):
        pass

    # --- Field Validators ---
    @field_validator('username', 'full_name', mode='before')
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return format_email(value)

    # --- Password Management ---
    @classmethod
    def create_with_password(cls, password, **kwargs):
        salt = base64.b64encode(os.urandom(16)).decode()
        hashed = cls.hash_password(password, salt)
        return cls(hashed_password=hashed, salt=salt, **kwargs)

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        salt_bytes = base64.b64decode(salt.encode())
        return text2hash2base64Str(password, salt_bytes)

    def verify_password(self, password: str) -> bool:
        salt_bytes = base64.b64decode(self.salt.encode())
        return self.hashed_password == text2hash2base64Str(password, salt_bytes)

    # --- ID Generation ---
    @staticmethod
    def generate_user_id(email: str) -> str:
        email = format_email(email)
        """Generate a unique user ID based on email."""
        return f"User:{text2hash2uuid(email.lower())}"

    def get_id(self) -> str:
        """Get unique identifier for current user instance."""
        return self.generate_user_id(self.email)

    # --- Role Checks ---
    def is_root(self) -> bool:
        return self.role == UserRole.root

    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    def is_active(self) -> bool:
        return not self.disabled

    def model_dump_exclude_sensitive(self, level=0):
        """Hide sensitive fields unless explicitly requested."""
        sensitive_fields = [
            {
                'hashed_password','salt'
            },
            {
                'rank','create_time','update_time','status','metadata','auto_del'
                'hashed_password','salt',
            },
        ]        
        d = super().model_dump(exclude=sensitive_fields[level])
        if level>0:            
            d['username'] = ""
            d['full_name'] = ""
            d['salt'] = ""
            d['hashed_password'] = ""            
        return d

    def model_json_schema_exclude_sensitive(self, level=0):
        """Hide sensitive fields unless explicitly requested."""
        sensitive_fields = [
            {
                'hashed_password','salt'
            },
            {
                'rank','create_time','update_time','status','metadata','auto_del'
                'hashed_password','salt',
            },
        ]        
        d = super().model_json_schema(exclude=sensitive_fields[level])        
        return d
try:
    from ..Storages.BasicModel import BasicStore, Controller4Basic, Model4Basic
except Exception as e:
    from Storages.BasicModel import BasicStore, Controller4Basic, Model4Basic

class Controller4User:
    class AbstractObjController(Controller4Basic.AbstractObjController):
        pass
    class UserController(AbstractObjController):
        def __init__(self, store, model):
            self.model:Model4User.User = model
            self._store:UsersStore = store

        def set_password(self,password):
            self.update(hashed_password=text2hash2base64Str(password))

        def set_name(self,):
            pass

        def set_role(self,):
            pass

        def get_licenses(self,):
            pass

        def add_license(self,):
            pass

        def delete_license(self,):
            pass

        def get_appusages(self,):
            pass

        def add_appusage(self,):
            pass

        def delete_appusage(self,):
            pass
        
    class AppController(AbstractObjController):
        def __init__(self, store, model):
            self.model:Model4User.App = model
            self._store:UsersStore = store

        def delete(self):
            pass
    class LicenseController(AbstractObjController):
        def __init__(self, store, model):
            self.model:Model4User.License = model
            self._store:UsersStore = store

        def delete(self):
            pass

    class AppUsageController(AbstractObjController):
        def __init__(self, store, model):
            self.model:Model4User.AppUsage = model
            self._store:UsersStore = store

        def delete(self):
            pass

class Model4User:
    class AbstractObj(Model4Basic.AbstractObj):
        pass
  
    class User(AbstractObj,User):
        
        def gen_new_id(self) -> str:
            return self.generate_user_id(self.email)
        
        def _utc(days=50000):
            utc_now = datetime.now(timezone.utc)
            future_offset = timedelta(days=days)
            future_utc = utc_now + future_offset
            return future_utc

        def wipe_sensitive_field(self, level=0):
            """Hide sensitive fields unless explicitly requested."""
            self.hashed_password = ""
            self.salt = ""
            
            if level==1:
                self.rank = [0]
                self.status = ""
            if level==2:            
                self.username = ""
                self.full_name = ""            
                self.create_time = self._utc()
                self.update_time = self._utc()
                self.auto_del = False

        _controller: Controller4User.UserController = None
        def get_controller(self)->Controller4User.UserController: return self._controller
        def init_controller(self,store):self._controller = Controller4User.UserController(store,self)

    class App(AbstractObj):
        parent_App_id:str
        running_cost:int = 0
        major_name:str = None
        minor_name:str = None
        
        _controller: Controller4User.AppController = None
        def get_controller(self)->Controller4User.AppController: return self._controller
        def init_controller(self,store):self._controller = Controller4User.AppController(store,self)

    class License(AbstractObj):
        user_id:str
        access_token:str = None
        bought_at:datetime = None
        expiration_date:datetime = None
        running_time:int = 0
        max_running_time:int = 0
        
        _controller: Controller4User.LicenseController = None
        def get_controller(self)->Controller4User.LicenseController: return self._controller
        def init_controller(self,store):self._controller = Controller4User.LicenseController(store,self)

    class AppUsage(AbstractObj):
        user_id:str
        App_id:str
        license_id:str
        start_time:datetime = None
        end_time:datetime = None
        running_time_cost:int = 0
        
        _controller: Controller4User.AppUsageController = None
        def get_controller(self)->Controller4User.AppUsageController: return self._controller
        def init_controller(self,store):self._controller = Controller4User.AppUsageController(store,self)

class UsersStore(BasicStore):
    def __init__(self, encryptor=None):
        super().__init__(None, encryptor)
        self.tmp_user_uuids = {}
    
    def _get_class(self, id: str, modelclass=Model4User):
        return super()._get_class(id, modelclass)

    def add_new_user(self, username:str,password:str,full_name:str,
            email:str,role:str='user',rank:list=[0], metadata={}) -> Model4User.User:
        tmp = Model4User.User.create_with_password(
                    username=username,
                    role=role,
                    full_name=full_name,
                    password=password,
                    email=email,
                    rank=rank,
                    metadata=metadata)
                    
        if self.exists(tmp.gen_new_id()):
            return None
            raise ValueError('user already exists!')
        return self.add_new_obj(tmp)
    
    # def add_new_app(self, major_name:str,minor_name:str,running_cost:int=0,parent_App_id:str=None) -> Model4User.App:
    #     return self.add_new_obj(Model4User.App(major_name=major_name,minor_name=minor_name,
    #                                        running_cost=running_cost,parent_App_id=parent_App_id))
        
    def find_all_users(self)->list[Model4User.User]:
        return self.find_all('User:*')
    
    def find_user_by_email(self,email)->Model4User.User:
        self.tmp_user_uuids[email] = self.tmp_user_uuids.get(email,Model4User.User.generate_user_id(email))
        return self.find(self.tmp_user_uuids[email])
    
