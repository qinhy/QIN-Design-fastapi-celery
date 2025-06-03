import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.UserAuthTask.UserBaseTask import UserBaseTask
from Task.UserModel import Model4User,FileSystem

class EditUser(UserBaseTask):
    @classmethod
    def description(cls):return """Add a new user to the system."""

    class Model(UserBaseTask.Model):
        
        class Version(UserBaseTask.Model.Version):
            pass
        
        class Args(BaseModel):
            # username: str
            # email: str
            file_system: Optional[FileSystem] = None
            file_systems: Optional[list[FileSystem]] = None
            full_name: Optional[str] = None
            new_password: Optional[str] = None
            is_remove: bool = False
            password: Optional[str] = None

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

    # class PayloadModel(BaseModel):
    #     role:str = 'user'
    #     email: EmailStr = Field(..., description="The email address of the user")
    #     exp: datetime = Field(..., description="The expiration time of the token as a datetime object")
        
    #     def is_root(self):return self.role == 'root'

    # class SessionModel(BaseModel):
    #     token_type: str = 'bearer'
    #     app_access_token: str
    #     user_uuid: str
    #     exp: datetime = Field(..., description="The expiration time of the token as a datetime object")

    #     def model_dump_json_dict(self)->dict:
    #         return json.loads(self.model_dump_json())
        
    class Action(UserBaseTask.Action):
        def forward(self):
            self.model:EditUser.Model = self.model
            # self.log_and_send("Registering user...")
            
            hash_password_fn = UserModels.User.hash_password

            try:
                new_password = self.model.new_password or self.model.password
                ups = {}
                if self.model.full_name:
                    ups['full_name'] = self.model.full_name
                if self.model.file_system:
                    ups['file_system'] = json.loads(self.model.file_system.model_dump_json())
                if new_password and self.model.password:
                    if not current_user.verify_password(self.model.password):
                        raise HTTPException(status_code=400, detail="Incorrect password")
                    ups['hashed_password'] = hash_password_fn(new_password,current_user.salt)
                if ups:
                    current_user.get_controller().update(**ups)
                    return {"status": "success", "message": "User info updated successfully"}
                return {"status": "success", "message": "User info not changes"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to update user info: {e}")
            
        def edit_user_info(self, self.model: UserModels.EditUserRequest,):

if __name__ == "__main__":
    import json
    print(json.dumps(EditUser.as_mcp_tool(), indent=4))