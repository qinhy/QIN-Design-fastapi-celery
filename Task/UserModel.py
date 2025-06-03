from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, IO, List, Literal, Optional, Union
import uuid
import fsspec
from pydantic import BaseModel, EmailStr, Field, field_validator


#
# ─── 1. COMMON BASE MODEL ───────────────────────────────────────────────────────
#
class BaseFileSystemConfig(BaseModel):
    """
    Common fields for every filesystem configuration.
    The actual `protocol` is determined by subclasses via Literal[...] below.
    """
    protocol: Optional[str] = Field(
        None,
        description="Storage protocol identifier (e.g. 's3', 'gcs', 'file')."
    )
    permissions: Optional[str] = Field(
        'rw',
        description="Linux-like permissions. At minimum, use 'r', 'w', or 'rw'. "
                    "You may also supply a full 9-character string (e.g. 'rwxr-xr--')."
    )
    expire_time: Optional[datetime] = Field(
        None,
        description="UTC-aware expiration time. Must include tzinfo=UTC."
    )
    root_path: Optional[str] = Field(
        default=None,
        description="Optional root path inside the remote filesystem (e.g. 'folder/subfolder').",
        example="folder/subfolder"
    )
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra config passed to fsspec (e.g. anon=True).",
        example={"anon": False}
    )

    #
    # ─── Validators for common fields ────────────────────────────────────────────
    #
    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        # Allow either a short string like 'r', 'w', 'rw' (length 1 or 2),
        # or a full 9-character string like 'rwxr-xr--'
        if len(v) not in (1, 2, 9):
            raise ValueError("`permissions` must be 'r', 'w', 'rw', or 9 chars (e.g. 'rwxr-xr--').")

        invalid = [c for c in v if c not in "rwx-"]
        if invalid:
            raise ValueError(
                f"`permissions` contains invalid character(s): {invalid!r}. "
                "Allowed: 'r', 'w', 'x', '-'."
            )
        return v

    @field_validator("expire_time")
    @classmethod
    def _validate_expire_time(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None or v.tzinfo.utcoffset(v) != timezone.utc.utcoffset(v):
            raise ValueError("`expire_time` must be timezone-aware and set to UTC.")
        return v


#
# ─── 2. PER-PROTOCOL CONFIG SUBCLASSES ───────────────────────────────────────────
#
class FileConfig(BaseFileSystemConfig):
    protocol: Literal["file"] = "file"
    # No additional fields needed.


class MemoryConfig(BaseFileSystemConfig):
    protocol: Literal["memory"] = "memory"
    # No additional fields needed.


class S3Config(BaseFileSystemConfig):
    protocol: Literal["s3"] = "s3"

    bucket: Optional[str] = Field(
        None,
        description="S3 bucket name (e.g. 'my-bucket')."
    )
    region: Optional[str] = Field(
        None,
        description="AWS region (e.g. 'us-west-2')."
    )
    key: Optional[str] = Field(
        None,
        description="AWS access key ID."
    )
    secret: Optional[str] = Field(
        None,
        description="AWS secret access key."
    )
    token: Optional[str] = Field(
        None,
        description="AWS session token (for temporary credentials)."
    )
    endpoint_url: Optional[str] = Field(
        None,
        description="Custom S3 endpoint (e.g. 'https://s3.us-west-2.amazonaws.com')."
    )
    anon: Optional[bool] = Field(
        None,
        description="If True, access S3 anonymously (public bucket)."
    )


class GCSConfig(BaseFileSystemConfig):
    protocol: Literal["gcs"] = "gcs"

    project: Optional[str] = Field(
        None,
        description="Google Cloud project ID (e.g. 'my-gcp-project')."
    )
    token: Optional[str] = Field(
        None,
        description="GCS OAuth2 token or service account JSON."
    )


class ABFSConfig(BaseFileSystemConfig):
    protocol: Literal["abfs"] = "abfs"

    account_name: Optional[str] = Field(
        None,
        description="Azure storage account name."
    )
    account_key: Optional[str] = Field(
        None,
        description="Azure storage account key."
    )
    sas_token: Optional[str] = Field(
        None,
        description="Azure Shared Access Signature (SAS) token."
    )
    connection_string: Optional[str] = Field(
        None,
        description="Full Azure connection string."
    )


class AzConfig(BaseFileSystemConfig):
    protocol: Literal["az"] = "az"

    account_name: Optional[str] = Field(
        None,
        description="Azure Data Lake Gen2 storage account name."
    )
    account_key: Optional[str] = Field(
        None,
        description="Azure Data Lake Gen2 storage account key."
    )
    sas_token: Optional[str] = Field(
        None,
        description="Azure SAS token for AADL Gen2."
    )
    connection_string: Optional[str] = Field(
        None,
        description="Full Azure Data Lake Gen2 connection string."
    )


class FTPConfig(BaseFileSystemConfig):
    protocol: Literal["ftp"] = "ftp"

    host: Optional[str] = Field(
        None,
        description="FTP server hostname (e.g. 'ftp.example.com')."
    )
    username: Optional[str] = Field(
        None,
        description="FTP username."
    )
    password: Optional[str] = Field(
        None,
        description="FTP password."
    )
    port: Optional[int] = Field(
        21,
        description="FTP port (defaults to 21)."
    )


class SFTPConfig(BaseFileSystemConfig):
    protocol: Literal["sftp"] = "sftp"

    host: Optional[str] = Field(
        None,
        description="SFTP server hostname (e.g. 'sftp.example.com')."
    )
    username: Optional[str] = Field(
        None,
        description="SFTP username."
    )
    password: Optional[str] = Field(
        None,
        description="SFTP password."
    )
    port: Optional[int] = Field(
        22,
        description="SFTP port (defaults to 22)."
    )
    key_filename: Optional[str] = Field(
        None,
        description="Path to private key file for SFTP authentication."
    )


class HTTPConfig(BaseFileSystemConfig):
    protocol: Literal["http", "https"] = "http"

    host: Optional[str] = Field(
        None,
        description="HTTP(S) server hostname (e.g. 'example.com')."
    )
    port: Optional[int] = Field(
        None,
        description="Optional port (will be omitted if None)."
    )
    client_kwargs: Optional[Dict[str, Any]] = Field(
        None,
        description="Extra arguments passed to the HTTP client (e.g. headers)."
    )


#
# ─── 3. DISCRIMINATED UNION TYPE FOR ANY CONFIG ─────────────────────────────────
#
SystemConfig = Union[
    FileConfig,
    MemoryConfig,
    S3Config,
    GCSConfig,
    ABFSConfig,
    AzConfig,
    FTPConfig,
    SFTPConfig,
    HTTPConfig,
]


#
# ─── 4. THE FileSystem “WRAPPER” ────────────────────────────────────────────────
#
class FileSystem(
    FileConfig,
    MemoryConfig,
    S3Config,
    GCSConfig,
    ABFSConfig,
    AzConfig,
    FTPConfig,
    SFTPConfig,
    HTTPConfig,
):
    """
    A single class that both carries its own config (via the shared BaseFileSystemConfig fields)
    and exposes convenience methods (`ls()`, `makedirs()`, `rm()`, `open_for_read()`, `open_for_write()`, `open_for_append()`)
    on top of fsspec, with permission and expire_time checks.
    
    Because every subclass already enforces protocol, you can load one of them directly:
    
        fs = FileSystem(**my_dict)
    
    Pydantic will pick the correct subclass (e.g. S3Config, FTPConfig, etc.) automatically,
    based on the `protocol` field.
    """
    # internal cache for fsspec filesystem instance
    protocol: Literal["file","memory","s3","gcs","abfs","az","ftp","sftp","http","https"] = "file"
    _fs: Any = None
    _schemas:Any = {        
        'File':FileConfig,
        'Memory':MemoryConfig,
        'S3':S3Config,
        'GCS':GCSConfig,
        'ABFS':ABFSConfig,
        'Az':AzConfig,
        'FTP':FTPConfig,
        'SFTP':SFTPConfig,
        'HTTP':HTTPConfig,
    }
    

    class Config:
        extra = "allow"
        json_schema_extra = {
            "examples": [
                # 1) Local File System
                {
                    "protocol": "file",
                    "root_path": "/data/project",
                    "permissions": "rw"
                },
                # 2) In-Memory File System
                {
                    "protocol": "memory",
                    "root_path": "/virtual/tmp"
                },
                # 3) S3
                {
                    "protocol": "s3",
                    "bucket": "my-bucket",
                    "region": "us-west-2",
                    "key": "AKIA...KEY",
                    "secret": "SECRET…",
                    "token": "SESSION_TOKEN",
                    "endpoint_url": "https://s3.us-west-2.amazonaws.com",
                    "anon": False,
                    "root_path": "backups/2024",
                    "permissions": "rw"
                },
                # 4) Google Cloud Storage (GCS)
                {
                    "protocol": "gcs",
                    "project": "my-gcp-project",
                    "token": "GCP_SERVICE_ACCOUNT_JSON",
                    "root_path": "gcs-folder/subfolder"
                },
                # 5) Azure Blob File System (ABFS)
                {
                    "protocol": "abfs",
                    "account_name": "mystorageaccount",
                    "account_key": "ACCOUNT_KEY...",
                    "sas_token": "SAS_TOKEN",
                    "connection_string": "DefaultEndpointsProtocol=...",
                    "root_path": "data/exports"
                },
                # 6) Azure Data Lake Gen2 (AZ)
                {
                    "protocol": "az",
                    "account_name": "mydatalake",
                    "account_key": "DL_KEY...",
                    "sas_token": "SAS_TOKEN",
                    "connection_string": "DefaultEndpointsProtocol=...",
                    "root_path": "lake/raw"
                },
                # 7) FTP
                {
                    "protocol": "ftp",
                    "host": "ftp.example.com",
                    "username": "ftpuser",
                    "password": "ftppass",
                    "port": 21,
                    "root_path": "public_html"
                },
                # 8) SFTP
                {
                    "protocol": "sftp",
                    "host": "sftp.example.com",
                    "username": "sftpuser",
                    "password": "sftppass",
                    "port": 22,
                    "key_filename": "/home/user/.ssh/id_rsa",
                    "root_path": "uploads"
                },
                # 9) HTTP
                {
                    "protocol": "http",
                    "host": "files.example.com",
                    "port": 443,
                    "client_kwargs": {"headers": {"Authorization": "Bearer ..."}},
                    "root_path": "files"
                },
            ]
        }

    def get_valid_schemas(self):
        return self._schemas    

    def get_fsspec_full_path(self, path: Optional[str] = None) -> str:
        """
        Build the full URI/path for the file on this remote filesystem,
        handling common protocols.
        """
        if path is None:
            path_obj = Path(".")
        else:
            normalized = str(path).lstrip("/\\")
            path_obj = Path(normalized) if normalized else Path(".")

        protocol = self.protocol.lower()
        root_path_obj = Path(self.root_path or "")
        rel_path = root_path_obj / path_obj
        path_str = rel_path.as_posix()

        # ─── S3 / GCS ────────────────────────────────────────────────────────────
        if protocol in {"s3", "s3a", "gcs", "gs"}:
            bucket = self.bucket
            if not bucket:
                raise ValueError(f"'bucket' must be set for protocol '{protocol}'")
            return f"{protocol}://{bucket}/{path_str}"

        # ─── FTP ───────────────────────────────────────────────────────────────────
        if protocol == "ftp":
            host = self.host
            if not host:
                raise ValueError("`host` must be set for FTP protocol.")
            return f"ftp://{host}/{path_str}"

        # ─── SFTP ──────────────────────────────────────────────────────────────────
        if protocol == "sftp":
            host = self.host
            if not host:
                raise ValueError("`host` must be set for SFTP protocol.")
            user_part = f"{self.username}@" if self.username else ""
            port_part = f":{self.port}" if self.port else ""
            return f"sftp://{user_part}{host}{port_part}/{path_str}"

        # ─── HTTP / HTTPS ─────────────────────────────────────────────────────────
        if protocol in {"http", "https"}:
            host = self.host
            if not host:
                raise ValueError("`host` must be set for HTTP/HTTPS protocol.")
            port_part = f":{self.port}" if self.port else ""
            return f"{protocol}://{host}{port_part}/{path_str}"

        # ─── LOCAL FILE ────────────────────────────────────────────────────────────
        if protocol == "file":
            return str(rel_path)

        # ─── FALLBACK for anything else ────────────────────────────────────────────
        host = self.host
        port_part = f":{self.port}" if self.port else ""
        bucket_part = f"/{self.bucket}" if self.bucket else ""
        return f"{protocol}://{host}{port_part}{bucket_part}/{path_str}"

    def get_fs_and_path(self, path: Any) -> tuple[fsspec.AbstractFileSystem, str]:
        """
        Instantiate or re-use a cached fsspec filesystem object,
        then compute the “full path” URI or real-path to hand off to fsspec.
        """
        full_path = self.get_fsspec_full_path(path)
        if self._fs is None:
            fs_kwargs = self.model_dump(exclude=['protocol'],exclude_none=True)
            fs: fsspec.AbstractFileSystem = fsspec.filesystem(self.protocol, **fs_kwargs)
            self._fs = fs
        return self._fs, full_path

    def ls(
        self,
        path: Any,
        detail: bool = False
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """
        If detail=False:  returns a List[str] of paths (no metadata dicts).
        If detail=True:   returns a List[dict], where each dict now has {"name", "size", …}
                          plus an added "isDir": True/False flag.
        """
        fs, full_path = self.get_fs_and_path(path)

        if not detail:
            # Simply return the list of path‐strings
            return fs.ls(full_path, detail=False)  # type: ignore[return-value]
        else:
            # Get the usual metadata dicts from fsspec
            entries: List[Dict[str, Any]] = fs.ls(full_path, detail=True)  # type: ignore[return-value]

            # Add an "isDir" boolean to each dict. Most fsspec backends include
            # a "type" key whose value is either "file" or "directory". If your FS
            # returns something different, you can fall back on fs.isdir(name).
            for info in entries:
                name = info.get("name") or info.get("Key") or info.get("path")  # some backends differ on the key
                # Try to read "type" first:
                entry_type = info.get("type")
                if entry_type is not None:
                    info["isDir"] = (entry_type == "directory")
                else:
                    # If "type" isn’t present, explicitly ask the filesystem:
                    info["isDir"] = fs.isdir(name)  # note: this does an extra stat call

            return json.loads(json.dumps(entries))

    def makedirs(self, path: Any, exist_ok: bool = True) -> None:
        fs, full_path = self.get_fs_and_path(path)
        return fs.makedirs(full_path, exist_ok=exist_ok)

    def rm(self, path: Any, recursive: bool = True) -> Any:
        fs, full_path = self.get_fs_and_path(path)
        return fs.rm(full_path, recursive=recursive)

    #
    # ─── 5. UPDATED: open_for_read / open_for_write / open_for_append ────────────
    #
    def _check_expired(self) -> None:
        """
        Raise a ValueError if the current time is ≥ expire_time (UTC).
        """
        if self.expire_time is not None:
            now_utc = datetime.now(timezone.utc)
            if now_utc >= self.expire_time:
                raise ValueError(
                    f"Configuration expired at {self.expire_time.isoformat()}; "
                    f"current UTC time is {now_utc.isoformat()}."
                )

    def _check_permission(self, mode: str) -> None:
        """
        Basic permissions check: if reading ('r' in mode), ensure 'r' in self.permissions;
        if writing or appending ('w' or 'a' in mode), ensure 'w' in self.permissions.
        """
        perms = self.permissions or ""
        # read check
        if "r" in mode:
            if "r" not in perms:
                raise PermissionError(f"Read not allowed: permissions={perms!r}")
        # write/append check
        if any(m in mode for m in ("w", "a", "x")):
            if "w" not in perms:
                raise PermissionError(f"Write not allowed: permissions={perms!r}")

    def open_for_read(self, path: Any, mode: str = "rb") -> IO[bytes] | IO[str]:
        """
        Open the given path in read-mode and return the file-like object.
        By default, `mode="rb"` returns a binary buffer; if you want text, pass `mode="r"`.
        """
        self._check_expired()
        self._check_permission(mode)

        fs, full_path = self.get_fs_and_path(path)
        return fs.open(full_path, mode)

    def open_for_write(self, path: Any, mode: str = "wb") -> IO[bytes] | IO[str]:
        """
        Open the given path in write-mode and return the file-like object.
        By default, `mode="wb"` writes bytes; if you want text, pass `mode="w"`.
        """
        self._check_expired()
        self._check_permission(mode)

        fs, full_path = self.get_fs_and_path(path)
        return fs.open(full_path, mode)

    def open_for_append(self, path: Any, mode: str = "ab") -> IO[bytes] | IO[str]:
        """
        Open the given path in append-mode and return the file-like object.
        By default, `mode="ab"` expects bytes; if you want text, pass `mode="a"`.
        """
        self._check_expired()
        self._check_permission(mode)

        fs, full_path = self.get_fs_and_path(path)
        return fs.open(full_path, mode)


# class FileSystem(BaseModel):
#     """
#     Remote File System configuration, designed for use with fsspec-compatible backends.
#     """
#     protocol: str = Field(
#         'file',
#         description="Filesystem protocol, such as 's3', 'gcs', 'ftp', 'sftp', 'http', etc.",
#         example="s3"
#     )
#     host: Optional[str] = Field(
#         default=None,
#         description="Host or endpoint for the filesystem, if applicable (e.g., S3-compatible API endpoint or WebDAV server).",
#         example="s3.amazonaws.com"
#     )
#     port: Optional[int] = Field(
#         default=None,
#         description="Port number, if required by the protocol.",
#         example=443
#     )
#     username: Optional[str] = Field(
#         default=None,
#         description="Username or access key for authentication.",
#         example="myuser"
#     )
#     password: Optional[str] = Field(
#         default=None,
#         description="Password or secret access key for authentication.",
#         example="mysecret"
#     )
#     permissions: str = Field(
#         default='rw',
#         description="Permissions for the filesystem in Linux-style (e.g., 'rw', 'rwx', etc.).",
#         example="rw"
#     )
#     bucket: Optional[str] = Field(
#         default=None,
#         description="Bucket, container, or root path for the remote storage.",
#         example="my-data-bucket"
#     )
#     root_path: Optional[str] = Field(
#         default=None,
#         description="Optional root path within the remote filesystem.",
#         example="folder/subfolder"
#     )
#     options: Optional[Dict[str, Any]] = Field(
#         default_factory=dict,
#         description="Additional configuration options (passed directly to fsspec).",
#         example={"anon": False}
#     )

#     _fs:Any=None
#     _full_path:Any=None

#     class Config:
#         extra = "allow"
#         json_schema_extra = {
#             "examples": [
#                 {
#                     # "summary": "Amazon S3 Example",
#                     "protocol": "s3",
#                     "host": "s3.amazonaws.com",
#                     "port": 443,
#                     "username": "AKIAIOSFODNN7EXAMPLE",
#                     "password": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
#                     "bucket": "my-data-bucket",
#                     "root_path": "myproject/data",
#                     "options": {
#                         "region_name": "us-west-2",
#                         "anon": False
#                     }                    
#                 },
#                 {
#                     # "summary": "Google Cloud Storage Example",
#                     "protocol": "gcs",
#                     "bucket": "my-gcs-bucket",
#                     "root_path": "datasets",
#                     "options": {
#                         "token": "path/to/service-account.json"
#                     }                    
#                 },
#                 {
#                     # "summary": "WebDAV Example",
#                     "protocol": "webdav",
#                     "host": "webdav.example.com",
#                     "port": 443,
#                     "username": "alice",
#                     "password": "SuperSecret",
#                     "root_path": "/public/files",
#                     "options": {
#                         "protocol": "https"
#                     }                    
#                 },
#                 {
#                     # "summary": "SFTP Example",
#                     "protocol": "sftp",
#                     "host": "sftp.example.com",
#                     "port": 22,
#                     "username": "bob",
#                     "password": "anotherSecret!",
#                     "root_path": "/home/bob/data",
#                     "options": {
#                         "known_hosts": "/home/bob/.ssh/known_hosts"
#                     }                    
#                 }
#             ]
#         }


#     def fsspec_kwargs(self) -> Dict[str, Any]:
#         """
#         Constructs a dictionary of keyword arguments suitable for fsspec.filesystem().
#         Sensitive values like password are unwrapped.
#         """
#         kwargs = dict(self.options or {})

#         # Add top-level attributes if present
#         if self.host is not None:
#             kwargs["host"] = self.host
#         if self.port is not None:
#             kwargs["port"] = self.port
#         if self.username is not None:
#             # Some backends expect 'username', others 'user'—user should adjust if needed
#             kwargs["username"] = self.username
#         if self.password is not None:
#             kwargs["password"] = self.password
#         if self.bucket is not None:
#             # Some protocols expect 'bucket' as a top-level argument, e.g. s3fs
#             kwargs["bucket"] = self.bucket

#         # root_path is typically for path construction, not fsspec kwargs, so skip it here

#         return kwargs

#     def get_fsspec_full_path(self, path: Optional[str] = None) -> str:
#         """
#         Build the full URI/path for the file on this remote file system, handling common protocols.
#         """
#         if path is None:
#             path = Path(".")  # Default to current directory

#         # Remove leading slashes (both / and \) to make it relative
#         normalized = path.lstrip("/\\")
#         path = Path(normalized) if normalized else Path(".")
    
#         protocol = self.protocol.lower()
#         root_path = Path(self.root_path or "")
#         rel_path:Path = root_path / path

#         # Path part (converted to posix) for URIs
#         path_str = rel_path.as_posix()

#         if protocol in {"s3", "s3a", "gs", "gcs"}:
#             if not self.bucket:
#                 raise ValueError(f"Bucket must be specified for protocol '{protocol}'")
#             # e.g., s3://my-bucket/path/to/file
#             return f"{protocol}://{self.bucket}/{path_str}"

#         elif protocol == "ftp":
#             if not self.host:
#                 raise ValueError("Host must be specified for FTP protocol.")
#             return f"{protocol}://{self.host}/{path_str}"

#         elif protocol == "sftp":
#             if not self.host:
#                 raise ValueError("Host must be specified for SFTP protocol.")
#             user_part = f"{self.username}@" if self.username else ""
#             port_part = f":{self.port}" if self.port else ""
#             return f"{protocol}://{user_part}{self.host}{port_part}/{path_str}"

#         elif protocol in {"webdav", "http", "https"}:
#             if not self.host:
#                 raise ValueError("Host must be specified for WebDAV/HTTP protocol.")
#             port_part = f":{self.port}" if self.port else ""
#             return f"{protocol}://{self.host}{port_part}/{path_str}"

#         elif protocol == "file":
#             # Local filesystem, resolve to absolute path
#             return str(rel_path)

#         else:
#             # Fallback: protocol://host[:port]/bucket/path
#             host = self.host or ""
#             port_part = f":{self.port}" if self.port else ""
#             bucket_part = f"/{self.bucket}" if self.bucket else ""
#             return f"{protocol}://{host}{port_part}{bucket_part}/{path_str}"

#     def get_fs_and_path(self, path)->tuple[fsspec.AbstractFileSystem,str]:
#         """
#         Build fsspec filesystem and full path from model configuration and input path.
#         """
#         # Build the full path
#         full_path:str = self.get_fsspec_full_path(path)
#         if self._fs is None:
#             fs_kwargs = self.fsspec_kwargs()
#             fs:fsspec.AbstractFileSystem = fsspec.filesystem(self.protocol, **fs_kwargs)
#             self._fs = fs
#         return self._fs, full_path

#     def ls(self, path, detail=False):
#         fs, full_path = self.get_fs_and_path(path)
#         return fs.ls( full_path, detail=detail)

#     def makedirs(self, path, exist_ok=True):
#         fs, full_path = self.get_fs_and_path(path)
#         return fs.makedirs(full_path, exist_ok=exist_ok)
        
#     def rm(self, path, recursive=True):
#         fs, full_path = self.get_fs_and_path(path)
#         return fs.rm( full_path, recursive=recursive)


####################################################################
# a = FileSystem()
# a.root_path = 'D://DL'
# print(a.model_dump(exclude_none=True))
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

    file_system : Optional[FileSystem] = Field(None,
        description="Remote File System configuration, designed for use with fsspec-compatible backends.",
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
    
