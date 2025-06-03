import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture
from Task.UserModel import Model4User, UsersStore

class UserBaseTask(ServiceOrientedArchitecture):
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
            pub_key_path: Optional[str] = None
            priv_key_path: Optional[str] = None

        class Args(BaseModel):
            pass

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
            self.model:UserBaseTask.Model = self.model
            self._prepare_db()
        
        def _prepare_db(self):        
            self.db = UsersStore(encryptor=None)
            if "redis" in self.model.param.backend:
                self.db.redis_backend(redis_URL=self.model.param.backend_url)
            elif "file" in self.model.param.backend:
                self.db.file_backend(file_path=self.model.param.backend_url)
            elif "mongo" in self.model.param.backend:
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
            self.log_and_send("Stop flag detected.", UserBaseTask.Levels.WARNING)
            self.model.ret.n = 0
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(UserBaseTask.as_mcp_tool(), indent=4))