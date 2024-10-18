from typing import Any
from pydantic import BaseModel

class ServiceOrientedArchitecture:
    class Model(BaseModel):
        pass
    class Result(BaseModel):
        pass
    class Action:
        def __call__(self, *args, **kwargs):
            return ServiceOrientedArchitecture.Result()


class Fibonacci(ServiceOrientedArchitecture):

    class Model(BaseModel):
        class Input(BaseModel):
            n: int = 1
        class Output(BaseModel):
            n: int = 1

        args:Input
        ret:Output = None
    class Action:
        def __init__(self, model):
            # Ensure fib_task is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)
            
            self.model: Fibonacci.Model = model

        def __call__(self, *args: Any, **kwds: Any):
            return self.calculate()

        def calculate(self):
            """Calculates the nth Fibonacci number."""
            n = self.model.Input.n
            if n <= 0:
                self.model.Output.n = n
                return self.model
            elif n == 1:
                self.model.Output.n = n
                return self.model
            else:
                a, b = 0, 1
                for _ in range(2, n + 1):
                    a, b = b, a + b
                self.model.Output.n = b
                return self.model

# Usage example
# if __name__ == "__main__":
#     fib_task = Fibonacci(n=10)
#     action = FibonacciAction(fib_task)
#     result = action()
#     print(f"The 10th Fibonacci number is: {result}")
