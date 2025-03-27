import datetime
from typing import Literal, Optional

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, RabbitmqMongoApp, RedisApp
from Task.BasicAPIs import BasicCeleryTask
import CustomTask
from config import *

TaskNames = [i for i in CustomTask.__dir__() if '_' not in i]
TaskClass = [CustomTask.__dict__[i] for i in CustomTask.__dir__() if '_' not in i]
TaskParentClass = [i.__bases__[0] if hasattr(i,'__bases__') else None for i in TaskClass]
ValidTask = ['ServiceOrientedArchitecture' in str(i) for i in TaskParentClass]
ACTION_REGISTRY={k:v for k,v,i in zip(TaskNames,TaskClass,ValidTask) if i}

class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app,
                 ACTION_REGISTRY:dict[str,any]=ACTION_REGISTRY):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)

        # Auto-generate endpoints for each action
        for action_name, action_class in ACTION_REGISTRY.items():
            self.add_web_api(
                self._make_api_action_handler(action_name, action_class),
                'post',f"/{action_name.lower()}/")
            self.add_web_api(
                self._make_api_schedule_handler(action_name, action_class),
                'post',f"/{action_name.lower()}/schedule/")
    
    def add_web_api(self, func, method: str = 'post', endpoint: str = '/'):
        method = method.lower().strip()
        allowed_methods = {
            'get': self.router.get,
            'post': self.router.post,
            'put': self.router.put,
            'delete': self.router.delete,
            'patch': self.router.patch,
            'options': self.router.options,
            'head': self.router.head,
        }

        if method not in allowed_methods:
            raise ValueError(
                f"Method '{method}' is not allowed. "
                f"Supported methods: {', '.join(allowed_methods)}")

        allowed_methods[method](endpoint)(func)

    def _make_api_action_handler(self, action_name, action_class):
        examples = action_class.Model.examples() if hasattr(action_class.Model,'examples') else None
        eta_example: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
        if examples:
            def handler(task_model: action_class.Model=Body(..., examples=examples),eta=eta_example):
                return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        else:
            def handler(task_model: action_class.Model,eta=eta_example):
                return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        return handler

    def _make_api_schedule_handler(self, action_name, action_class):
        examples = action_class.Model.examples() if hasattr(action_class.Model,'examples') else None
        execution_time_example = Query(
                            datetime.datetime.now(datetime.timezone.utc).isoformat().split('.')[0],
                            description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS")
        timezone_Literal = Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"]
        timezone_Literal_example = Query("Asia/Tokyo", description="Choose a timezone from the list")
        if examples:
            def handler(task_model: action_class.Model=Body(..., examples=examples),
                        execution_time: str = execution_time_example,
                        timezone: timezone_Literal = timezone_Literal_example):
                        return self.api_schedule_perform_action(action_name, task_model.model_dump(), execution_time, timezone)
        else:
            def handler(task_model: action_class.Model,
                        execution_time: str = execution_time_example,
                        timezone: timezone_Literal = timezone_Literal_example):
                        return self.api_schedule_perform_action(action_name, task_model.model_dump(), execution_time, timezone)
        return handler
        

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

celery_app = BasicApp.get_celery_app()
my_app = CeleryTask(BasicApp,celery_app)

## add original api
from CustomTask import Fibonacci
def my_fibo(n:int=0,mode:Literal['fast','slow']='fast'):
    m = Fibonacci.Model()
    m.param.mode = mode
    m.args.n = n
    return my_app.api_perform_action('Fibonacci', m.model_dump(),0)

my_app.add_web_api(my_fibo,'get','/myapi/fibonacci/')

api.include_router(my_app.router, prefix="", tags=["Tasks"])
    