import threading
from typing import Literal, Optional, Union, List
import fsspec
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
    from Task.UserModel import User,FileSystem
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper
    from UserModel import User,FileSystem

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
            
            if self.user:
                self.fs_config = self.user.file_system
            else:
                self.fs_config = FileSystem()

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
