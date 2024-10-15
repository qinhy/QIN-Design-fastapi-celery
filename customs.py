from typing import Any
from pydantic import BaseModel

class Fibonacci(BaseModel):
    n: int = 1

class FibonacciAction:
    def __init__(self, model: Fibonacci):
        
        # Ensure fib_task is a Fibonacci instance, even if a dict is passed
        if isinstance(model, dict):
            model = Fibonacci(**model)
        
        self.fib_task = model

    def __call__(self, *args: Any, **kwds: Any):
        return self.calculate()

    def calculate(self) -> int:
        """Calculates the nth Fibonacci number."""
        n = self.fib_task.n
        if n <= 0:
            return 0
        elif n == 1:
            return 1
        else:
            a, b = 0, 1
            for _ in range(2, n + 1):
                a, b = b, a + b
            return b

# Usage example
# if __name__ == "__main__":
#     fib_task = Fibonacci(n=10)
#     action = FibonacciAction(fib_task)
#     result = action()
#     print(f"The 10th Fibonacci number is: {result}")
