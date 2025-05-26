
import os
import uuid
import base64
import hashlib
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, SecretStr, EmailStr, field_validator


def text2hash2base32Str(text:str):
    hash_uuid = hashlib.sha256(text.encode()).digest()
    return base64.b32encode(hash_uuid).decode('utf-8').strip('=')

def text2hash2base64Str(text:str,salt:bytes = b'',ite:int = 10**6):
    return base64.b64encode(hashlib.pbkdf2_hmac('sha256', text.encode(), salt, ite, dklen=16)).decode()

def text2hash(text:str,salt:bytes = b'',ite:int = 10**6):
    return hashlib.pbkdf2_hmac('sha256', text.encode(), salt, ite, dklen=16)

def text2hash2uuid(text:str,salt:bytes = b'',ite:int = 10**6):
    return str(uuid.UUID(bytes=text2hash(text,salt,ite)))

def remove_hyphen(uuid:str):
    return uuid.replace('-', '')

def restore_hyphen(uuid:str):
    if len(uuid) != 32:
        raise ValueError("Invalid UUID format")
    return f'{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}'

def format_email(email: str) -> str:
    return email.lower().strip()


# --- Enum for Roles ---
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
    password: Optional[SecretStr] = Field(
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
        schema_extra = {
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
            kwargs["password"] = self.password.get_secret_value()
        if self.bucket is not None:
            # Some protocols expect 'bucket' as a top-level argument, e.g. s3fs
            kwargs["bucket"] = self.bucket

        # root_path is typically for path construction, not fsspec kwargs, so skip it here

        return kwargs

    def get_fsspec_full_path(self, path: Optional[str] = None) -> str:
        """
        Build the full URI/path for the file on this remote file system, handling common protocols.
        """
        protocol = self.protocol.lower()
        # Build the relative path inside the bucket/root
        parts = []
        if self.root_path:
            parts.append(self.root_path.strip("/"))
        if path:
            parts.append(path.lstrip("/"))
        rel_path = "/".join(parts)

        if protocol in {"s3", "s3a", "gs", "gcs"}:
            if not self.bucket:
                raise ValueError("Bucket must be specified for protocol '%s'" % protocol)
            # e.g., s3://my-bucket/optional/prefix/file.txt
            return f"{protocol}://{self.bucket}/{rel_path}"
        elif protocol == "ftp":
            if not self.host:
                raise ValueError("Host must be specified for FTP protocol.")
            # e.g., ftp://ftp.example.com/folder/file.txt
            return f"ftp://{self.host}/{rel_path}"
        elif protocol == "sftp":
            if not self.host:
                raise ValueError("Host must be specified for SFTP protocol.")
            # e.g., sftp://user@host:port/folder/file.txt
            user_part = f"{self.username}@" if self.username else ""
            port_part = f":{self.port}" if self.port else ""
            return f"sftp://{user_part}{self.host}{port_part}/{rel_path}"
        elif protocol in {"webdav", "http", "https"}:
            if not self.host:
                raise ValueError("Host must be specified for WebDAV/HTTP protocol.")
            port_part = f":{self.port}" if self.port else ""
            # e.g., webdav://host[:port]/folder/file.txt
            return f"{protocol}://{self.host}{port_part}/{rel_path}"
        elif protocol == "file":
            # Local filesystem, just join paths
            import os
            base = self.root_path or ""
            if path:
                return os.path.join(base, path)
            return base
        else:
            # Fallback: protocol://host[:port]/bucket/root_path/path
            host = self.host or ""
            port_part = f":{self.port}" if self.port else ""
            bucket_part = f"/{self.bucket}" if self.bucket else ""
            uri = f"{protocol}://{host}{port_part}{bucket_part}"
            if rel_path:
                uri += f"/{rel_path}"
            return uri

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

    file_system : FileSystem = Field(FileSystem(),
        description="Remote File System configuration, designed for use with fsspec-compatible backends.",
    )

    role: UserRole = Field(default=UserRole.user,example="user",
        description="The role assigned to the user, determining permissions.",
    )

    disabled: bool = Field(default=False,example=False,
        description="Indicates whether the user's account is disabled.",
    )

    salt: str = Field(default=None,example="dGhpc2lzYXNhbHRzYW1wbGU=",
        description="Base64-encoded per-user salt used for password hashing.",
    )


    # --- Config ---
    class Config:
        validate_assignment = True
        extra = 'forbid'

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
    def create_with_password(cls, **kwargs):
        password = kwargs.pop("password")
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


