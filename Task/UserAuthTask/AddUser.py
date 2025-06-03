import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.UserAuthTask.UserBaseTask import UserBaseTask
from Task.UserModel import Model4User

class AddUser(UserBaseTask):
    @classmethod
    def description(cls):return """Add a new user to the system."""

    class Model(UserBaseTask.Model):
        
        class Version(UserBaseTask.Model.Version):
            pass
        
        class Args(BaseModel):            
            username: str
            full_name: str
            email: str
            password: str
            invite_code: str

            # rank: list = [0]
            # metadata: dict = {}

        @staticmethod
        def examples():return [{
            "args": {
                "username": "test",
                "full_name": "test",
                "email": "test@tes.com",
                "password": "test",
                "invite_code": "test",
                # "rank": [0],
                # "metadata": {}
            }}]

        version:Version = Version()
        args:Args

    class Action(UserBaseTask.Action):
        def forward(self):
            self.model:AddUser.Model = self.model
            self.log_and_send("Registering user...")
            self.model.ret = self.db.add_new_user(
                        self.model.args.username,
                        self.model.args.password,
                        self.model.args.full_name, 
                        self.model.args.email,
                        'user',
                        [0],
                        {})
            self.model.ret.wipe_sensitive_field()
            self.log_and_send("User registered.")

if __name__ == "__main__":
    import json
    print(json.dumps(AddUser.as_mcp_tool(), indent=4))