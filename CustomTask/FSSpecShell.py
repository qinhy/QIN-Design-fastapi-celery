import threading
from typing import Literal, Optional, Union, List
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
    from Task.UserModel import User,FileSystem
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper

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
            self.fs_config = FileSystem()

            if self.user and self.user.file_system:
                self.fs_config = self.user.file_system
                

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                command = self.model.args.command
                path = self.model.args.path

                try:
                    result = None
                    if command == 'ls':
                        result = self.fs_config.ls(path, detail=False)
                    elif command == 'mkdir':
                        self.fs_config.makedirs(path, exist_ok=True)
                        result = f"Directory created: {path}"
                    elif command == 'rm':
                        self.fs_config.rm(path, recursive=True)
                        result = f"Removed: {path}"
                    else:
                        raise ValueError(f"Unsupported command: {command}")

                    self.model.ret.result = result

                except Exception as e:
                    self.log_and_send(
                        f"Error executing command '{command}' on '{path}': {e}",
                        level=FSSpecShell.Levels.ERROR
                    )
                    self.model.ret.result = str(e)

                self.model.param.user = None
                return self.model

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
