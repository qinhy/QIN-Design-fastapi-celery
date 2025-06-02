import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture
from Task.UserModel import Model4User, UsersStore

class RegisterUser(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """

        """

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            backend: Literal["redis", "file", "mongo"] = "redis"
            backend_url: str = "redis://localhost:6379"

        class Args(BaseModel):            
            username: str
            full_name: str
            email: str
            password: str
            invite_code: str
            rank: list = [0]
            metadata: dict = {}

        class Return(Model4User.User):
            pass

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass        

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return []
            
        version:Version = Version()
        param:Param = Param()
        args:Args
        ret:Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model:RegisterUser.Model = self.model
            self.db = UsersStore(encryptor=None)
            if self.model.param.backend == "redis":
                self.db.redis_backend(redis_URL=self.model.param.backend_url)
            elif self.model.param.backend == "file":
                self.db.file_backend(file_path=self.model.param.backend_url)
            elif self.model.param.backend == "mongo":
                self.db.mongo_backend(mongo_URL=self.model.param.backend_url)
            
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                self.log_and_send("Registering user...")
                self.db.add_new_user(
                            self.model.args.username,
                            self.model.args.password,
                            self.model.args.full_name, 
                            self.model.args.email,
                            'user',
                            self.model.args.rank,
                            {})
                            
            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected.", RegisterUser.Levels.WARNING)
            self.model.ret.n = 0
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(RegisterUser.as_mcp_tool(), indent=4))