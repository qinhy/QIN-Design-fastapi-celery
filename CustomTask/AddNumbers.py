from typing import List, Optional
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper

class AddNumbers(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Sums a list of numbers and returns the total.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            # Placeholder for possible future parameters
            pass

        class Args(BaseModel):
            numbers: List[int] = Field(..., description="List of numbers to add")

        class Return(BaseModel):
            sum: int = Field(..., description="The sum of the input numbers")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {"args": {"numbers": [1, 2, 3, 4]}},
                {"args": {"numbers": [10, -5, 3]}},
                {"args": {"numbers": []}},  # Edge case: empty list
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = Return(sum=0)
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: AddNumbers.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()
                numbers = self.model.args.numbers
                result = sum(numbers)
                self.log_and_send(f"Summing {numbers} = {result}")
                self.model.ret.sum = result
            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, returning sum = 0.", AddNumbers.Levels.WARNING)
            self.model.ret.sum = 0
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

if __name__ == "__main__":
    import json
    print(json.dumps(AddNumbers.as_openai_tool()["function"]["parameters"]["properties"]["args"], indent=4))
