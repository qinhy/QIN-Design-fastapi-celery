import datetime
from typing import Literal, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import ServiceOrientedArchitecture
from Task.Basic import AppInterface, FileSystemApp, RabbitmqMongoApp, RedisApp
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

        self.router.post("/pipeline/add")(self.api_add_pipeline)

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
            'get':    self.router.get,
            'post':   self.router.post,
            'put':    self.router.put,
            'delete': self.router.delete,
            'patch':  self.router.patch,
            'options':self.router.options,
            'head':   self.router.head,
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
            def handler(task_model: action_class.Model=Body(..., examples=examples),eta: Optional[int]=eta_example):
                return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        else:
            def handler(task_model: action_class.Model,eta: Optional[int]=eta_example):
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
        
    def api_add_pipeline(self,name: str='FiboPrime', method: str = 'POST', pipeline: list[str] = ['Fibonacci','PrimeNumberChecker']):
        self.api_ok()
        path = f"/pipeline/{name}"
        method = method.upper()

        # Validate function names
        invalid_funcs = [fn for fn in pipeline if fn not in self.ACTION_REGISTRY]
        if invalid_funcs:
            raise HTTPException(
                status_code=400,
                detail=f"Service [{invalid_funcs}] are not supported."
            )
        
        if len(pipeline)<2:
            raise HTTPException(
                status_code=400,
                detail=f"pipeline should contains more than 2 services."
            )
             

        # Save pipeline and register route name
        self.pipelines = self.api_list_pipelines()
        self.pipelines[name] = name
        
        def create_dynamic_handler(pipeline: list[str]):
            first_in_class = ACTION_REGISTRY[pipeline[0]]
            last_out_class = ACTION_REGISTRY[pipeline[1]]
            """Create a dynamic route handler based on a pipeline of functions."""
            async def dynamic_handler(in_model: first_in_class.Model)->dict:
                result = []
                for func_name in pipeline:
                    result.append(ACTION_REGISTRY[func_name].Model.examples()[0])
                return {"result": result}
            return dynamic_handler
        
        # Create and add the dynamic route
        dynamic_handler = create_dynamic_handler(pipeline)
        self.router.add_api_route(
            path=path,
            endpoint=dynamic_handler,
            methods=[method],
            name=name,
            summary=f"Dynamic pipeline {name}:{pipeline}"
        )

        # self.refresh_openapi(self.router)
        self.BasicApp.store().set('pipelines',self.pipelines)
        return {"status": "created", "path": path, "method": method, "pipeline": pipeline}
    
    def delete_pipeline(self, name: str):
        self.api_ok()
        self.pipelines = self.api_list_pipelines()
        self.router.routes = [route for route in self.router.routes if route.name != name]
        del self.pipelines[name]
        self.BasicApp.store().set('pipelines',self.pipelines)

    def refresh_pipeline(self):
        # get frome redis
        # self.pipelines = self.api_list_pipelines()
        # add and delete
        # to update my_app local pipeline dicts
        # self.router.routes = [route for route in self.router.routes if route.name != name]
        pass

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
    
def refresh_openapi(app: FastAPI) -> None:
    """Refresh the OpenAPI schema after dynamic route changes."""
    app.openapi_schema = None
    app.openapi = lambda: get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    

if conf.app_backend=='redis':
    BasicApp:AppInterface = RedisApp(conf.redis.url)
    
elif conf.app_backend=='file':
    BasicApp:AppInterface = FileSystemApp(conf.file.url)
    
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

# new apis for pipeline
@api.get("/pipeline/refresh", summary="refresh existing pipelines")
def refresh_pipeline():
    my_app.refresh_pipeline()
    # Remove all routes that came from `my_app.router`
    router_route_names = {route.name for route in my_app.router.routes}
    api.router.routes = [
        route for route in api.router.routes
        if not (isinstance(route, APIRoute) and route.name in router_route_names)
    ]
    # re include
    api.include_router(my_app.router, prefix="", tags=["Tasks"])
    refresh_openapi(api)
    return {"status": "refreshed"}

@api.delete("/pipeline/delete", summary="Delete an existing pipeline")
def delete_pipeline(name: str):
    my_app.delete_pipeline(name)
    refresh_openapi(api)
    return {"status": "deleted", "pipeline": name}

api.include_router(my_app.router, prefix="", tags=["Tasks"])