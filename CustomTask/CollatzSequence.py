import threading
from typing import Optional, List
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
except:
    from mockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper

class CollatzSequence(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Generates the Collatz sequence starting from a given number n.
The sequence follows the rule: if n is even, divide by 2; if n is odd, multiply by 3 and add 1.
Continues until reaching 1 or the maximum number of steps (if specified).
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Parameter(BaseModel):
            max_steps: Optional[int] = Field(
                None, description="Optional limit on number of steps to prevent infinite loops"
            )

        class Arguments(BaseModel):
            n: int = Field(1, description="Starting number for the Collatz sequence (must be >= 1)")

        class Returness(BaseModel):
            sequence: List[int] = Field(default_factory=list, description="The Collatz sequence starting at n")

        
        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{
                "param": {"max_steps": 100},
                "args": {"n": 6}
            }]

        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Optional[Returness] = Returness()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: CollatzSequence.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                n = self.model.args.n
                max_steps = self.model.para.max_steps
                if n < 1:
                    self.log_and_send("Input must be >= 1. Returning empty sequence.", CollatzSequence.Levels.WARNING)
                    self.model.rets.sequence = []
                    return self.model

                sequence = []
                steps = 0
                self.log_and_send(f"Starting Collatz sequence from {n} with max_steps={max_steps}")

                while n != 1 and (max_steps is None or steps < max_steps):
                    if stop_flag.is_set():
                        return self.to_stop()
                    sequence.append(n)
                    n = n // 2 if n % 2 == 0 else 3 * n + 1
                    steps += 1

                sequence.append(1)  # Sequence always ends in 1 (unless max_steps cuts it early)
                self.model.rets.sequence = sequence
                self.log_and_send(f"Collatz sequence: {sequence}")

                return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected. Returning partial or empty sequence.", CollatzSequence.Levels.WARNING)
            self.model.rets.sequence = []
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


# Simple test code for the CollatzSequence class
if __name__ == "__main__":
    # Create a model instance
    model = CollatzSequence.Model()
    
    # Configure the model
    model.args.n = 6
    model.para.max_steps = 100
    
    action = CollatzSequence.Action(model, None)
    
    # Execute the calculation
    print("Starting Collatz sequence test...")
    result = action()
    
    # Print the result
    print(f"Collatz sequence: {result.rets.sequence}")
    
    # Test with a different number
    print("\nTesting with a different number...")
    model.args.n = 27
    result = action()
    print(f"Collatz sequence for 27: {result.rets.sequence}")
