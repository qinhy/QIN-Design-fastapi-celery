from typing import Any
from pydantic import BaseModel

class ServiceOrientedArchitecture:
    class Model(BaseModel):
        class Param(BaseModel):
            pass
        class Args(BaseModel):
            pass
        class Return(BaseModel):
            pass
    class Action:
        def __call__(self, *args, **kwargs):
            return ServiceOrientedArchitecture.Model.Return()


class Fibonacci(ServiceOrientedArchitecture):

    class Model(BaseModel):        
        class Param(BaseModel):
            mode: str = 'fast'
            def is_fast(self):
                return self.mode=='fast'
        class Args(BaseModel):
            n: int = 1
        class Return(BaseModel):
            n: int = -1

        param:Param = Param()
        args:Args
        ret:Return = Return()

    class Action:
        def __init__(self, model):
            # Ensure model is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)
            
            self.model: Fibonacci.Model = model

        def __call__(self, *args: Any, **kwds: Any):
            return self.calculate()

        def calculate(self):
            n = self.model.args.n
            if n <= 1:
                self.model.ret.n = n
            else:
                if self.model.param.is_fast():
                    a, b = 0, 1
                    for _ in range(2, n + 1):
                        a, b = b, a + b
                    res = b
                else:
                    def fib_r(n):
                        return(fib_r(n-1) + fib_r(n-2))                    
                    res = fib_r(n)
                self.model.ret.n = res
            return self.model