
from datetime import datetime
import os
from pathlib import Path
import uuid
import base64
import hashlib
from enum import Enum
from typing import Optional, Dict, Any
import fsspec
from pydantic import BaseModel, Field, EmailStr, field_validator



class FileSystem(BaseModel):
    """
    Remote File System configuration, designed for use with fsspec-compatible backends.
    """
    protocol: str = Field(
        'file',
        description="Filesystem protocol, such as 's3', 'gcs', 'ftp', 'sftp', 'http', etc.",
        example="s3"
    )
    host: Optional[str] = Field(
        default=None,
        description="Host or endpoint for the filesystem, if applicable (e.g., S3-compatible API endpoint or WebDAV server).",
        example="s3.amazonaws.com"
    )
    port: Optional[int] = Field(
        default=None,
        description="Port number, if required by the protocol.",
        example=443
    )
    username: Optional[str] = Field(
        default=None,
        description="Username or access key for authentication.",
        example="myuser"
    )
    password: Optional[str] = Field(
        default=None,
        description="Password or secret access key for authentication.",
        example="mysecret"
    )
    bucket: Optional[str] = Field(
        default=None,
        description="Bucket, container, or root path for the remote storage.",
        example="my-data-bucket"
    )
    root_path: Optional[str] = Field(
        default=None,
        description="Optional root path within the remote filesystem.",
        example="folder/subfolder"
    )
    options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional configuration options (passed directly to fsspec).",
        example={"anon": False}
    )

    class Config:
        extra = "allow"
        json_schema_extra = {
            "examples": [
                {
                    "summary": "Amazon S3 Example",
                    "value": {
                        "protocol": "s3",
                        "host": "s3.amazonaws.com",
                        "port": 443,
                        "username": "AKIAIOSFODNN7EXAMPLE",
                        "password": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                        "bucket": "my-data-bucket",
                        "root_path": "myproject/data",
                        "options": {
                            "region_name": "us-west-2",
                            "anon": False
                        }
                    }
                },
                {
                    "summary": "Google Cloud Storage Example",
                    "value": {
                        "protocol": "gcs",
                        "bucket": "my-gcs-bucket",
                        "root_path": "datasets",
                        "options": {
                            "token": "path/to/service-account.json"
                        }
                    }
                },
                {
                    "summary": "WebDAV Example",
                    "value": {
                        "protocol": "webdav",
                        "host": "webdav.example.com",
                        "port": 443,
                        "username": "alice",
                        "password": "SuperSecret",
                        "root_path": "/public/files",
                        "options": {
                            "protocol": "https"
                        }
                    }
                },
                {
                    "summary": "SFTP Example",
                    "value": {
                        "protocol": "sftp",
                        "host": "sftp.example.com",
                        "port": 22,
                        "username": "bob",
                        "password": "anotherSecret!",
                        "root_path": "/home/bob/data",
                        "options": {
                            "known_hosts": "/home/bob/.ssh/known_hosts"
                        }
                    }
                }
            ]
        }


    def fsspec_kwargs(self) -> Dict[str, Any]:
        """
        Constructs a dictionary of keyword arguments suitable for fsspec.filesystem().
        Sensitive values like password are unwrapped.
        """
        kwargs = dict(self.options or {})

        # Add top-level attributes if present
        if self.host is not None:
            kwargs["host"] = self.host
        if self.port is not None:
            kwargs["port"] = self.port
        if self.username is not None:
            # Some backends expect 'username', others 'user'—user should adjust if needed
            kwargs["username"] = self.username
        if self.password is not None:
            kwargs["password"] = self.password
        if self.bucket is not None:
            # Some protocols expect 'bucket' as a top-level argument, e.g. s3fs
            kwargs["bucket"] = self.bucket

        # root_path is typically for path construction, not fsspec kwargs, so skip it here

        return kwargs

    def get_fsspec_full_path(self, path: Optional[str] = None) -> str:
        """
        Build the full URI/path for the file on this remote file system, handling common protocols.
        """
        if path is None:
            path = Path(".")  # Default to current directory

        # Remove leading slashes (both / and \) to make it relative
        normalized = path.lstrip("/\\")
        path = Path(normalized) if normalized else Path(".")
    
        protocol = self.protocol.lower()
        root_path = Path(self.root_path or "")
        rel_path:Path = root_path / path

        # Path part (converted to posix) for URIs
        path_str = rel_path.as_posix()

        if protocol in {"s3", "s3a", "gs", "gcs"}:
            if not self.bucket:
                raise ValueError(f"Bucket must be specified for protocol '{protocol}'")
            # e.g., s3://my-bucket/path/to/file
            return f"{protocol}://{self.bucket}/{path_str}"

        elif protocol == "ftp":
            if not self.host:
                raise ValueError("Host must be specified for FTP protocol.")
            return f"{protocol}://{self.host}/{path_str}"

        elif protocol == "sftp":
            if not self.host:
                raise ValueError("Host must be specified for SFTP protocol.")
            user_part = f"{self.username}@" if self.username else ""
            port_part = f":{self.port}" if self.port else ""
            return f"{protocol}://{user_part}{self.host}{port_part}/{path_str}"

        elif protocol in {"webdav", "http", "https"}:
            if not self.host:
                raise ValueError("Host must be specified for WebDAV/HTTP protocol.")
            port_part = f":{self.port}" if self.port else ""
            return f"{protocol}://{self.host}{port_part}/{path_str}"

        elif protocol == "file":
            # Local filesystem, resolve to absolute path
            return str(rel_path)

        else:
            # Fallback: protocol://host[:port]/bucket/path
            host = self.host or ""
            port_part = f":{self.port}" if self.port else ""
            bucket_part = f"/{self.bucket}" if self.bucket else ""
            return f"{protocol}://{host}{port_part}{bucket_part}/{path_str}"

    def get_fs_and_path(self, path):
        """
        Build fsspec filesystem and full path from model configuration and input path.
        """
        fs_kwargs = self.fsspec_kwargs()
        fs:fsspec.AbstractFileSystem = fsspec.filesystem(self.protocol, **fs_kwargs)
        # Build the full path
        full_path:str = self.get_fsspec_full_path(path)
        return fs, full_path

####################################################################
# a = FileSystem()
# a.root_path = 'D://DL'
# print(a.get_fsspec_full_path('/xv_sdk'))
# exit()
####################################################################
#         
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

class UserRole(str, Enum):
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

    file_system : Optional[FileSystem] = Field(None,
        description="Remote File System configuration, designed for use with fsspec-compatible backends.",
    )

    role: UserRole = Field(default=UserRole.user,example="user",
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
        print(password)
        salt_bytes = base64.b64decode(self.salt.encode())
        print(salt_bytes)
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

    # --- Representation ---
    def model_dump(self, *args, **kwargs):
        """Hide sensitive fields unless explicitly requested."""
        exclude = kwargs.pop('exclude', set())
        sensitive_fields = {'hashed_password','salt',}
        if not kwargs.get('include', None):
            exclude = set(exclude)
            exclude.update(sensitive_fields)            
        return super().model_dump(*args, exclude=exclude, **kwargs)

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

    def __init__(self) -> None:
        super().__init__()
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
    
