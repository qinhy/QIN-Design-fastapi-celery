import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture


class PrimeNumberChecker(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Checks if a given number is prime.
Supports two checking modes:
- basic: Uses a simple brute-force approach
- smart: Uses optimized algorithms for faster checking
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            mode: Literal['basic', 'smart'] = Field("smart", description="Check mode: 'basic' (brute-force) or 'smart' (optimized)")

            def is_smart(self):
                return self.mode == 'smart'

        class Args(BaseModel):
            number: int = Field(13, description="The number to check for primality")

        class Return(BaseModel):
            is_prime: Optional[bool] = Field(None, description="Whether the number is prime")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass
        
        @staticmethod
        def examples():
            return [
                {"param": {"mode": "smart"}, "args": {"number": 13}},
                {"param": {"mode": "basic"}, "args": {"number": 10}},
                {"param": {"mode": "smart"}, "args": {"number": 1}},
            ]
        
        version:Version = Version()
        param: Param = Param()
        args: Args = Param()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: PrimeNumberChecker.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                number = self.model.args.number
                if number < 2:
                    self.log_and_send(f"{number} is not prime (less than 2).")
                    self.model.ret.is_prime = False
                    return self.model

                is_smart = self.model.param.is_smart()
                mode = "smart" if is_smart else "basic"
                self.log_and_send(f"Checking if {number} is prime using {mode} mode.")

                result = self._is_prime(number, stop_flag, is_smart)
                if stop_flag.is_set():
                    return self.to_stop()

                self.log_and_send(f"{number} is {'prime' if result else 'not prime'}.")
                self.model.ret.is_prime = result
                return self.model

        def to_stop(self):
            self.log_and_send("Stop flag triggered. Aborting prime check.", PrimeNumberChecker.Levels.WARNING)
            self.model.ret.is_prime = False
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

        def _is_prime(self, n: int, stop_flag: threading.Event, is_smart: bool) -> bool:
            if is_smart:
                if n == 2:
                    return True
                if n % 2 == 0:
                    return False
                i = 3
                while i * i <= n:
                    if stop_flag.is_set():
                        return False
                    if n % i == 0:
                        return False
                    i += 2
                return True
            else:
                for i in range(2, n):
                    if stop_flag.is_set():
                        return False
                    if n % i == 0:
                        return False
                return True
