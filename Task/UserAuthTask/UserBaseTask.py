import os
import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture
from Task.UserModel import Model4User, UsersStore

class UserBaseTask(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return ""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
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
        args:Args
        ret:Optional[Return] = None
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model:UserBaseTask.Model = self.model
            self._prepare_db()
        
        def _prepare_db(self):        
            
            backend: Literal["redis", "file", "mongo"] = os.environ['APP_BACK_END']
            pub_key_path: Optional[str] = None
            priv_key_path: Optional[str] = None

            self.db = UsersStore(encryptor=None)
            if "redis" in backend:
                backend_url: str = os.environ['REDIS_URL']
                self.db.redis_backend(redis_URL=backend_url)
            elif "file" in backend:
                backend_url: str = os.environ['FILE_DIR']
                self.db.file_backend(file_path=backend_url)
            elif "mongo" in backend:
                backend_url: str = os.environ['MONGO_URL']
                self.db.mongo_backend(mongo_URL=backend_url)

        def forward(self):
            raise NotImplementedError
            
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()
                    
                # execute the action
                self.forward()
                            
            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected.", UserBaseTask.Levels.WARNING)
            self.model.ret = None
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(UserBaseTask.as_mcp_tool(), indent=4))