import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture
from Task.UserAuthTask.UserBaseTask import UserBaseTask
from Task.UserModel import Model4User, UsersStore

class AddUser(UserBaseTask):
    @classmethod
    def description(cls):
        return """
        """

    class Model(UserBaseTask.Model):

        class Param(UserBaseTask.Model.Param):
            pass        
        
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

        class Logger(UserBaseTask.Model.Logger):
            pass        

        class Version(UserBaseTask.Model.Version):
            pass

        @staticmethod
        def examples():
            return []
            
        version:Version = Version()
        param:Param = Param()
        args:Args
        ret:Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(UserBaseTask.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model:AddUser.Model = self.model
            self.db:UsersStore = self.db
            
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

            self.model.ret.wipe_sensitive_field()
            return self.model

if __name__ == "__main__":
    import json
    print(json.dumps(AddUser.as_mcp_tool(), indent=4))