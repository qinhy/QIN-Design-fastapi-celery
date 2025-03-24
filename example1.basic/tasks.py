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
        def __init__(self, model, BasicApp, level='INFO'):
            super().__init__(model, BasicApp, level)
            self.model:Fibonacci.Model = self.model

        def log_and_send(self, info:str):
            self.logger.log(self.logger.level,info)
            self.send_data_to_task({'info':info})

        def __call__(self, *args, **kwargs):
            """Executes the Fibonacci calculation based on the mode (fast/slow)."""
            with self.listen_stop_flag() as stop_flag:
                n = self.model.args.n

                if n <= 1:
                    info = f"n is {n}, returning it directly."
                    self.log_and_send(info)
                    self.model.ret.n = n
                    return self.model

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
            info = "Entering fast mode."
            self.log_and_send(info)

            a, b = 0, 1
            for i in range(2, n + 1):
                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected at iteration " + str(i) + ", stopping early.")
                    return
                a, b = b, a + b

            info = f'Fast mode result for n={n} is {b}'
            self.log_and_send(info)
            self.model.ret.n = b

        def _compute_slow(self, n, stop_flag:threading.Event):
            """Computes Fibonacci sequence using a recursive approach (slow mode)."""
            info = "Entering slow mode."
            self.log_and_send(info)

            def fib_recursive(n):
                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected during recursion, stopping early.")
                    return 0
                if n <= 1:
                    return n
                return fib_recursive(n - 1) + fib_recursive(n - 2)

            result = fib_recursive(n)
            info = f'Slow mode result for n={n} is {result}'
            self.log_and_send(info)
            self.model.ret.n = result

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
    