import datetime
import sys
import threading
from typing import Literal, Optional

from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.append("..")

from celery import Task
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, RabbitmqMongoApp, RedisApp, ServiceOrientedArchitecture
from Task.BasicAPIs import BasicCeleryTask
from config import *

class Fibonacci(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: Literal['fast', 'slow'] = Field("fast", description="Execution mode, either 'fast' or 'slow'")

            def is_fast(self):
                return self.mode == 'fast'

        class Args(BaseModel):
            n: int = Field(1, description="The position of the Fibonacci number to compute")

        class Return(BaseModel):
            n: int = Field(-1, description="The computed Fibonacci number at position n")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass        

        param:Param = Param()
        args:Args
        ret:Return = Return()
        logger:Logger = Logger(name='Fibonacci')

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


class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app,
                        ACTION_REGISTRY={'Fibonacci': Fibonacci,}):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)
        self.router.get("/", response_class=HTMLResponse)(self.get_doc_page)
        self.router.post("/fibonacci/")(self.api_fibonacci)
        self.router.post("/fibonacci/schedule/")(self.api_schedule_fibonacci)
        
        @self.celery_app.task(bind=True)
        def fibonacci(t: Task, fib_task_model_dump: dict) -> int:
            """Celery task to calculate the nth Fibonacci number."""
            model = Fibonacci.Model(**fib_task_model_dump)
            model.task_id=t.request.id
            model = Fibonacci.Action(model,BasicApp=BasicApp)()
            return self.is_json_serializable(model.model_dump())

        self.fibonacci = fibonacci
    
    def get_doc_page(self,):
        return RedirectResponse("/docs")
    
    ########################### basic function
    def api_fibonacci(self, fib_task: Fibonacci.Model,                      
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        return self.api_perform_action('Fibonacci',
                                fib_task.model_dump(),eta=eta)
    
    def api_schedule_fibonacci(self,
        fib_task: Fibonacci.Model,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
                        description="Choose a timezone from the list")
    ):
        return self.api_schedule_perform_action('Fibonacci',
                fib_task.model_dump(),execution_time,timezone)

########################################################
api = FastAPI()

api.add_middleware(
    CORSMiddleware,
    allow_origins=['*',],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api.add_middleware(SessionMiddleware,
                    secret_key=APP_SECRET_KEY, max_age=SESSION_DURATION)

if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp(REDIS_URL)
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,
                                             MONGO_URL,MONGO_DB,CELERY_META,
                                             CELERY_RABBITMQ_BROKER)
else:
    raise ValueError(f'no back end of {APP_BACK_END}')
ServiceOrientedArchitecture.BasicApp=BasicApp

celery_app = BasicApp.get_celery_app()
api.include_router(CeleryTask(BasicApp,celery_app).router, prefix="", tags=["fibonacci"])
    