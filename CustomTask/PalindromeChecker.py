import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture

class PalindromeChecker(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            mode: Literal['basic', 'smart'] = Field("smart", description="Mode: 'basic' (simple reverse) or 'smart' (efficient comparison)")

            def is_smart(self):
                return self.mode == 'smart'

        class Args(BaseModel):
            text: str = Field(..., description="The string to check for palindrome")

        class Return(BaseModel):
            is_palindrome: bool = Field(False, description="Whether the string is a palindrome")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        @staticmethod
        def examples():
            return [
                {"param": {"mode": "smart"}, "args": {"text": "racecar"}},
                {"param": {"mode": "basic"}, "args": {"text": "hello"}},
                {"param": {"mode": "smart"}, "args": {"text": "A man a plan a canal Panama"}},
            ]
        
        param: Param = Param()
        args: Args
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name='PalindromeChecker')

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: PalindromeChecker.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                text = self.model.args.text.strip().lower()
                is_smart = self.model.param.is_smart()
                mode = "smart" if is_smart else "basic"

                self.log_and_send(f"Checking if '{text}' is a palindrome using {mode} mode.")

                result = self._is_palindrome(text, stop_flag, is_smart)
                if stop_flag.is_set():
                    return self.to_stop()

                self.log_and_send(f"'{text}' is {'a palindrome' if result else 'not a palindrome'}.")
                self.model.ret.is_palindrome = result
                return self.model

        def to_stop(self):
            self.log_and_send("Stop flag triggered. Aborting palindrome check.", PalindromeChecker.Levels.WARNING)
            self.model.ret.is_palindrome = False
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

        def _is_palindrome(self, text: str, stop_flag: threading.Event, is_smart: bool) -> bool:
            if is_smart:
                left, right = 0, len(text) - 1
                while left < right:
                    if stop_flag.is_set():
                        return False
                    if text[left] != text[right]:
                        return False
                    left += 1
                    right -= 1
                return True
            else:
                return text == text[::-1]
