import datetime
import sys
import threading
from typing import Literal, Optional
sys.path.append("..")

from celery import Task
from fastapi import Query
from pydantic import BaseModel, Field

from Task.Basic import ServiceOrientedArchitecture
from basic_tasks import BasicApp, BasicCeleryTask, celery_app, api, api_ok
ServiceOrientedArchitecture.BasicApp = BasicApp

class Fibonacci(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: Literal['fast', 'slow'] = Field("fast", description="Execution mode, either 'fast' or 'slow'")

            def is_fast(self):
                return self.mode == 'fast'

        class Args(BaseModel):
            n: int = Field(1, description="The position of the Fibonacci number to compute")

        class Return(BaseModel):
            n: int = Field(-1, description="The computed Fibonacci number at position n")

        param:Param = Param()
        args:Args
        ret:Return = Return()

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model):
            # Ensure model is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)
            self.model: Fibonacci.Model = model
            self.logger = self.model.logger.init(name=f"Fibonacci:{self.model.task_id}")

        def __call__(self, *args, **kwargs):
            """Executes the Fibonacci calculation based on the mode (fast/slow)."""
            with self.listen_stop_flag() as stop_flag:
                n = self.model.args.n

                if n <= 1:
                    self.logger.info("n is " + str(n) + ", returning it directly.")
                    self.model.ret.n = n
                    return

                if self.model.param.is_fast():
                    self._compute_fast(n, stop_flag)
                else:
                    self._compute_slow(n, stop_flag)

                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected, returning 0.")
                    self.model.ret.n = 0
            return self.model

        def _compute_fast(self, n, stop_flag:threading.Event):
            """Computes Fibonacci sequence using an iterative approach (fast mode)."""
            self.logger.info("Entering fast mode.")

            a, b = 0, 1
            for i in range(2, n + 1):
                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected at iteration " + str(i) + ", stopping early.")
                    return
                a, b = b, a + b

            self.logger.info("Fast mode result for n=" + str(n) + " is " + str(b))
            self.model.ret.n = b

        def _compute_slow(self, n, stop_flag:threading.Event):
            """Computes Fibonacci sequence using a recursive approach (slow mode)."""
            self.logger.info("Entering slow mode.")

            def fib_recursive(n):
                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected during recursion, stopping early.")
                    return 0
                if n <= 1:
                    return n
                return fib_recursive(n - 1) + fib_recursive(n - 2)

            result = fib_recursive(n)
            self.logger.info("Slow mode result for n=" + str(n) + " is " + str(result))
            self.model.ret.n = result


BasicCeleryTask.ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
}

class CeleryTask(BasicCeleryTask):
    api = api

    ########################### basic function
    @staticmethod
    @celery_app.task(bind=True)
    def fibonacci(t: Task, fib_task_model_dump: dict) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        model = Fibonacci.Model(**fib_task_model_dump)
        model.task_id=t.request.id
        model = Fibonacci.Action(model)()
        return CeleryTask.is_json_serializable(model.model_dump())

    @api.post("/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model,                      
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        api_ok()
        # Calculate execution time (eta)
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

        task = CeleryTask.fibonacci.apply_async(args=[fib_task.model_dump()], eta=execution_time)
        
        res = {'task_id': task.id}
        if execution_time: res['scheduled_for'] = execution_time
        return res
    











    