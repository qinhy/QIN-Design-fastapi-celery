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

