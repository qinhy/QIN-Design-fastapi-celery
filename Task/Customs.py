from pydantic import BaseModel
from .Basic import ServiceOrientedArchitecture

class Fibonacci(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):
        
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

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model):
            # Ensure model is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)            
            self.model: Fibonacci.Model = model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                n = self.model.args.n
                if n <= 1:
                    self.model.ret.n = n
                else:
                    if self.model.param.is_fast():
                        a, b = 0, 1
                        for _ in range(2, n + 1):
                            if stop_flag.is_set():
                                break
                            a, b = b, a + b
                        res = b
                    else:
                        def fib_r(n):
                            if stop_flag.is_set(): return 0
                            if n<1:return n
                            return(fib_r(n-1) + fib_r(n-2))                    
                        res = fib_r(n)
                    self.model.ret.n = res
                        
                if stop_flag.is_set():
                    self.model.ret.n = 0
                
                return self.model