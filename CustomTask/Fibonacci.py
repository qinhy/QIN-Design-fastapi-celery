import threading
from typing import Literal, Optional
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class Fibonacci(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: Literal['fast', 'slow'] = Field("fast", description="Execution mode, either 'fast' or 'slow'")

            def is_fast(self):
                return self.mode == 'fast'

        class Args(BaseModel):
            n: int = Field(..., description="The position of the Fibonacci number to compute")

        class Return(BaseModel):
            n: int = Field(-1, description="The computed Fibonacci number at position n")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{ "param": {"mode": "fast"},"args": {"n": 13}},]
        
        @classmethod
        def description(cls):
            return """
Computes the Fibonacci number at a given position n.
Supports two computation modes:
- fast: Uses iterative approach, more efficient
- slow: Uses recursive approach, less efficient but demonstrates the mathematical concept
            """

        @classmethod
        def as_mcp_tool(cls):
            "https://modelcontextprotocol.io/docs/concepts/tools"
            "To be used in MCP tools"
            param_schema = cls.Param.schema()
            args_schema = cls.Args.schema()

            # Determine if "param" and/or "args" should be required at the top level
            top_level_required = []
            if param_schema.get("required"):
                top_level_required.append("param")
            if args_schema.get("required"):
                top_level_required.append("args")

            return [{
                "name": cls.__name__.lower(),
                "description": cls.description().strip(),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param": param_schema,
                        "args": args_schema,
                    },
                    "required": top_level_required
                },
                "annotations": {
                    "title": cls.__name__.replace("_", " "),
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False
                }
            }]

        @classmethod
        def as_openai_tool(cls):
            "https://modelcontextprotocol.io/docs/concepts/tools"
            "To be used in MCP tools"
            param_schema = cls.Param.schema()
            args_schema = cls.Args.schema()

            # Determine if "param" and/or "args" should be required at the top level
            top_level_required = []
            if param_schema.get("required"):
                top_level_required.append("param")
            if args_schema.get("required"):
                top_level_required.append("args")

            return [{
                "name": cls.__name__.lower(),
                "description": cls.description().strip(),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param": param_schema,
                        "args": args_schema,
                    },
                    "required": top_level_required
                },
                "annotations": {
                    "title": cls.__name__.replace("_", " "),
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False
                }
            }]
        version:Version = Version()
        param:Param = Param()
        args:Args
        ret:Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model:Fibonacci.Model = self.model
            
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                n = self.model.args.n
                if n <= 1:
                    self.log_and_send(f"n = {n}, returning it directly.")
                    self.model.ret.n = n
                    return self.model

                # Determine which mode to use
                is_fast = self.model.param.is_fast()
                mode = "fast" if is_fast else "slow"
                self.log_and_send(f"Entering {mode} mode.")

                result = self._compute_fib(n, stop_flag, is_fast)
                if stop_flag.is_set():
                    return self.to_stop()

                self.log_and_send(f"{mode} mode result for n={n} is {result}")
                self.model.ret.n = result

            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, returning 0.", Fibonacci.Levels.WARNING)
            self.model.ret.n = 0
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

        def _compute_fib(self, n: int, stop_flag: threading.Event, is_fast: bool) -> int:
            """Computes Fibonacci using either fast (iterative) or slow (recursive) logic."""
            if is_fast:
                # Fast (iterative)
                a, b = 0, 1
                for _ in range(2, n + 1):
                    if stop_flag.is_set():
                        return 0
                    a, b = b, a + b
                return b
            else:
                # Slow (recursive)
                def fib_recursive(x: int) -> int:
                    if stop_flag.is_set():
                        return 0
                    if x <= 1:
                        return x
                    return fib_recursive(x - 1) + fib_recursive(x - 2)
                return fib_recursive(n)

if __name__ == "__main__":
    import json
    print(json.dumps(Fibonacci.Model.as_mcp_tools(), indent=4))