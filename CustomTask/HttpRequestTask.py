import threading
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
import requests

try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class HttpRequestTask(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Performs HTTP requests to specified URLs.
Supports GET and POST methods.
Returns the status code and content of the response.
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            method: Literal['GET', 'POST'] = Field("GET",
                                        description="HTTP method: GET or POST")

        class Args(BaseModel):
            url: str = Field("https://httpbin.org/get",
                description="Target URL for the HTTP request")
            data: Optional[Dict[str, Any]] = Field(None,    
                description="Data for POST requests")

        class Return(BaseModel):
            status_code: int = Field(-1, description="HTTP status code")
            content: Optional[str] = Field(None, description="Response content")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {"param": {"method": "GET"}, 
                    "args": {"url": "https://httpbin.org/get"}},
                {"param": {"method": "POST"}, 
                    "args": {"url": "https://httpbin.org/post", 
                    "data": {"key": "value"}}}
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: HttpRequestTask.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                url = self.model.args.url
                method = self.model.param.method
                data = self.model.args.data

                self.log_and_send(f"Performing {method} request to {url}")

                try:
                    if method == 'GET':
                        response = requests.get(url)
                    else:
                        response = requests.post(url, json=data)
                    self.model.ret.status_code = response.status_code
                    self.model.ret.content = response.text
                    self.log_and_send(f"Received status {response.status_code}")
                except Exception as e:
                    self.model.ret.status_code = -1
                    self.model.ret.content = str(e)
                    self.log_and_send(f"Request failed: {e}", HttpRequestTask.Levels.WARNING)

            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, aborting HTTP request.", HttpRequestTask.Levels.WARNING)
            self.model.ret.status_code = 0
            self.model.ret.content = None
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})