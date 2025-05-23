import threading
from typing import Literal, Optional, Union, List
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
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
        class Param(BaseModel):
            command: Literal['ls', 'mkdir', 'rm'] = Field("ls", description="Filesystem command to execute")

        class Args(BaseModel):
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
                {"param": {"command": "ls",}, "args": {"path": "."}},
                {"param": {"command": "mkdir",}, "args": {"path": "./testdir"}},
                {"param": {"command": "rm",}, "args": {"path": "./testdir"}}
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

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                command = self.model.param.command
                path = self.model.args.path
                fs, full_path = FileInputHelper.get_fsspec_from_env_and_path(path)

                try:
                    if command == 'ls':
                        contents = fs.ls(full_path, detail=False)
                        self.model.ret.result = contents
                    elif command == 'mkdir':
                        fs.makedirs(full_path, exist_ok=True)
                        self.model.ret.result = f"Directory created: {full_path}"
                    elif command == 'rm':
                        fs.rm(full_path, recursive=True)
                        self.model.ret.result = f"Removed: {full_path}"
                    else:
                        raise ValueError(f"Unsupported command: {command}")
                except Exception as e:
                    self.log_and_send(f"Error executing command '{command}' on '{path}': {e}", level=FSSpecShell.Levels.ERROR)
                    self.model.ret.result = str(e)

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
