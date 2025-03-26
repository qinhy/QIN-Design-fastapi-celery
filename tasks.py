import datetime
from typing import Literal, Optional

from fastapi.responses import HTMLResponse, RedirectResponse

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, RabbitmqMongoApp, RedisApp, ServiceOrientedArchitecture
from Task.BasicAPIs import BasicCeleryTask
import CustomTask
from config import *

TaskNames = [i for i in CustomTask.__dir__() if '_' not in i]
TaskClass = [CustomTask.__dict__[i] for i in CustomTask.__dir__() if '_' not in i]
TaskParentClass = [i.__bases__[0] if hasattr(i,'__bases__') else None for i in TaskClass]
ValidTask = ['ServiceOrientedArchitecture' in str(i) for i in TaskParentClass]
ACTION_REGISTRY={k:v for k,v,i in zip(TaskNames,TaskClass,ValidTask) if i}

class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app, ACTION_REGISTRY:dict[str,any]=ACTION_REGISTRY):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)
        self.router.get("/", response_class=HTMLResponse)(self.get_doc_page)
        # self.router.post("/fibonacci/")(self.api_fibonacci)
        # self.router.post("/fibonacci/schedule/")(self.api_schedule_fibonacci)
    
        # Auto-generate endpoints for each action
        for action_name, action_class in ACTION_REGISTRY.items():
            # Direct execution endpoint
            self.router.post(f"/{action_name.lower()}/")(
                self._make_api_action_handler(action_name, action_class)
            )
            # Scheduled execution endpoint
            self.router.post(f"/{action_name.lower()}/schedule/")(
                self._make_api_schedule_handler(action_name, action_class)
            )
    
    def get_doc_page(self,):
        return RedirectResponse("/docs")

    def _make_api_action_handler(self, action_name, action_class):
        def handler(task_model: action_class.Model,
                    eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")):
            return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        return handler

    def _make_api_schedule_handler(self, action_name, action_class):
        def handler(
            task_model: action_class.Model,
            execution_time: str = Query(
                datetime.datetime.now(datetime.timezone.utc).isoformat().split('.')[0],
                description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"
            ),
            timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                              "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query(
                "Asia/Tokyo", description="Choose a timezone from the list")
        ):
            return self.api_schedule_perform_action(action_name, task_model.model_dump(), execution_time, timezone)
        return handler
    ########################### basic function
    # def api_fibonacci(self, fib_task: Fibonacci.Model,                      
    #     eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    # ):
    #     return self.api_perform_action('Fibonacci',
    #                             fib_task.model_dump(),eta=eta)
    
    # def api_schedule_fibonacci(self,
    #     fib_task: Fibonacci.Model,
    #     execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
    #     timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
    #                     "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
    #                     description="Choose a timezone from the list")
    # ):
    #     return self.api_schedule_perform_action('Fibonacci',
    #             fib_task.model_dump(),execution_time,timezone)

########################################################
conf = AppConfig()
print(conf.validate_backend().model_dump())
api = FastAPI()

api.add_middleware(
    CORSMiddleware,
    allow_origins=['*',],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
api.add_middleware(SessionMiddleware,
                    secret_key=conf.secret_key, max_age=conf.session_duration)

if conf.app_backend=='redis':
    BasicApp:AppInterface = RedisApp(conf.redis.url)
elif conf.app_backend=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(conf.rabbitmq.url,conf.rabbitmq.user,conf.rabbitmq.password,
                                             conf.mongo.url,conf.mongo.db,conf.celery.meta_table,
                                             conf.celery.broker)
else:
    raise ValueError(f'no back end of {conf.app_backend}')
ServiceOrientedArchitecture.BasicApp=BasicApp

celery_app = BasicApp.get_celery_app()
api.include_router(CeleryTask(BasicApp,celery_app).router, prefix="", tags=["fibonacci"])
    