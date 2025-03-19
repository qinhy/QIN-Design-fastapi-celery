import datetime
import os
import sys
sys.path.append("..")
from config import *

import threading
from typing import Literal, Optional
from fastapi.responses import FileResponse
from celery import Task
from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, RabbitmqMongoApp, RedisApp, ServiceOrientedArchitecture, TaskModel
from Task.BasicAPIs import BasicCeleryTask
from User.UserAPIs import AuthService, UserModels, router as users_router

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
        def __init__(self, model, BasicApp, level='INFO'):
            super().__init__(model, BasicApp, level)
            self.model:Fibonacci.Model = self.model

        def __call__(self, *args, **kwargs):
            """Executes the Fibonacci calculation based on the mode (fast/slow)."""
            with self.listen_stop_flag() as stop_flag:
                n = self.model.args.n

                if n <= 1:
                    self.logger.info(f"n is {n}, returning it directly.")
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
            self.logger.info("Entering fast mode.")

            a, b = 0, 1
            for i in range(2, n + 1):
                if stop_flag.is_set():
                    self.logger.warning("Stop flag detected at iteration " + str(i) + ", stopping early.")
                    return
                a, b = b, a + b

            self.logger.info(f'Fast mode result for n={n} is {b}')
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
            self.logger.info(f'Slow mode result for n={n} is {result}')
            self.model.ret.n = result

class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app,
                        ACTION_REGISTRY={'Fibonacci': Fibonacci,}):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)
        self.router.routes = []

        self.router.get("/")(self.get_doc_page)        
        self.router.get("/tasks/")(
                                    self.api_auth_list_tasks)
        self.router.get("/tasks/meta/{task_id}")(
                                    self.api_auth_task_meta)
        self.router.get("/tasks/stop/{task_id}")(
                                    self.api_auth_task_stop)
        self.router.get("/workers/")(
                                    self.api_auth_get_workers)
        self.router.get("/action/list")(
                                    self.api_auth_perform_action_list)
        self.router.post("/action/{name}")(
                                    self.api_auth_perform_action)
        self.router.post("/action/{name}/schedule/")(
                                    self.api_auth_schedule_perform_action)
        

        self.router.post("/auth/fibonacci/")(self.api_auth_fibonacci)
        self.router.post("/auth/local/fibonacci/")(self.api_auth_fibonacci)
        
        @self.celery_app.task(bind=True)
        def fibonacci(t: Task, fib_task_model_dump: dict) -> int:
            """Celery task to calculate the nth Fibonacci number."""
            model = Fibonacci.Model(**fib_task_model_dump)
            model.task_id=t.request.id
            model = Fibonacci.Action(model,BasicApp=BasicApp)()
            return self.is_json_serializable(model.model_dump())

        self.fibonacci = fibonacci
    
    async def get_doc_page(self,):
        return FileResponse(os.path.join(os.path.dirname(__file__), "gui.html"))
    
    def api_auth_list_tasks(self,
        current_payload: UserModels.PayloadModel = Depends(AuthService.get_current_payload)):
        user = UserModels.USER_DB.find_user_by_email(current_payload.email)
        tasks_id = user.metadata.get('tasks_id',[])
        return [self.BasicApp.get_task_meta(i) for i in tasks_id]
    
    def api_auth_task_meta(self,task_id: str,
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        return self.api_task_meta(task_id)
    
    def api_auth_task_stop(self,task_id: str,
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        return self.api_task_stop(task_id)
    
    def api_auth_get_workers(self,
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        return self.api_get_workers()
    
    def api_auth_perform_action_list(self,
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        return self.api_perform_action_list()
    
    def _add_user_task(self,user_email:str,task:TaskModel):
        user = UserModels.USER_DB.find_user_by_email(user_email)
        tasks_id:list = user.metadata.get('tasks_id',[])
        tasks_id.append(task.task_id)
        user.metadata['tasks_id'] = tasks_id
        user.get_controller().update(metadata=user.metadata)

    def api_auth_perform_action(self,
        name: str, 
        data: dict,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)"),
        current_payload: UserModels.PayloadModel = Depends(AuthService.get_current_payload)):
        res = self.api_perform_action(name,data,eta)
        self._add_user_task(current_payload.email,res)
        return res
    
    def api_auth_schedule_perform_action(self,
        name: str, 
        data: dict,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
                        description="Choose a timezone from the list"),
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        res = self.api_schedule_perform_action(name,data,execution_time,timezone)
        self._add_user_task(current_payload.email,res)        
        return res
    
    ########################### basic function with auth    
    async def api_auth_fibonacci(self, fib_task: Fibonacci.Model,                      
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)"),
        current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        self.api_ok()
        res = self.api_perform_action('Fibonacci',fib_task.model_dump(),eta)        
        self._add_user_task(current_payload.email,res)
        return res

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
api.include_router(users_router, prefix="", tags=["users"])