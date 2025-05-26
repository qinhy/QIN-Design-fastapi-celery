import threading
from typing import Dict, Literal, Optional, Union, List
import fsspec
from pydantic import BaseModel, Field, SecretStr

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
    from Task.UserModel import User
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper
    from UserModel import User

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
    options: Optional[Dict[str, str]] = Field(
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


class FSSpecShell(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Performs filesystem operations using `fsspec`, simulating basic shell commands:
- `ls`: List contents of a directory.
- `mkdir`: Create a directory (with parents).
- `rm`: Remove a file or directory (recursively if a directory).
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Param(ServiceOrientedArchitecture.Model.Param):
            pass

        class Args(BaseModel):
            command: Literal['ls', 'mkdir', 'rm'] = Field("ls", description="Filesystem command to execute")

            path: str = Field(".", description="Target path for the command")

        class Return(BaseModel):
            result: Union[str, List[str]] = Field(default="", description="Result of the command")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                { "args": {"command": "ls","path": "."}},
                { "args": {"command": "mkdir","path": "./testdir"}},
                { "args": {"command": "rm","path": "./testdir"}}
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: FSSpecShell.Model = self.model
            self.user:User = self.model.param.user
            self.fs_config = self.user.file_system

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                command = self.model.args.command
                path = self.model.args.path

                try:
                    fs, full_path = self.get_fs_and_path(path)
                    result = None

                    if command == 'ls':
                        result = fs.ls(full_path, detail=False)
                    elif command == 'mkdir':
                        fs.makedirs(full_path, exist_ok=True)
                        result = f"Directory created: {full_path}"
                    elif command == 'rm':
                        fs.rm(full_path, recursive=True)
                        result = f"Removed: {full_path}"
                    else:
                        raise ValueError(f"Unsupported command: {command}")

                    self.model.ret.result = result

                except Exception as e:
                    self.log_and_send(
                        f"Error executing command '{command}' on '{path}': {e}",
                        level=FSSpecShell.Levels.ERROR
                    )
                    self.model.ret.result = str(e)

                return self.model

        def get_fs_and_path(self, path):
            """
            Build fsspec filesystem and full path from model configuration and input path.
            """
            # Assume self.model.fs_config is a FileSystem model as defined earlier
            fs_config = self.fs_config
            fs_kwargs = fs_config.fsspec_kwargs()
            fs = fsspec.filesystem(fs_config.protocol, **fs_kwargs)
            # Build the full path
            full_path = fs_config.get_fsspec_full_path(path)
            return fs, full_path
        
        def to_stop(self):
            self.log_and_send("Stop flag triggered. Aborting command.", FSSpecShell.Levels.WARNING)
            self.model.ret.result = "Command stopped."
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(FSSpecShell.as_mcp_tool(), indent=4))
