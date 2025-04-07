# Standard library imports
import datetime
from typing import Literal, Optional

# FastAPI imports
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import pytz
from starlette.middleware.sessions import SessionMiddleware

# Application imports
from Task.Basic import (
    ServiceOrientedArchitecture,
    AppInterface, 
    FileSystemApp, 
    RabbitmqMongoApp, 
    RedisApp,
    TaskModel
)
from Task.BasicAPIs import BasicCeleryTask
import CustomTask
from config import *

TaskNames = [i for i in CustomTask.__dir__() if '_' not in i]
TaskClass = [CustomTask.__dict__[i] for i in CustomTask.__dir__() if '_' not in i]
TaskParentClass = [i.__bases__[0] if hasattr(i,'__bases__') else None for i in TaskClass]
ValidTask = ['ServiceOrientedArchitecture' in str(i) for i in TaskParentClass]
ACTION_REGISTRY={k:v for k,v,i in zip(TaskNames,TaskClass,ValidTask) if i}

class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app, root_fast_app:FastAPI,
                 ACTION_REGISTRY:dict[str,any]=ACTION_REGISTRY):
        super().__init__(BasicApp, celery_app, root_fast_app, ACTION_REGISTRY)    

        self.router.post("/pipeline/add")(self.api_add_pipeline)
        self.router.post("/pipeline/config")(self.api_set_config_pipeline)
        self.router.get("/pipeline/config/{name}")(self.api_get_config_pipeline)

    def create_api_pipeline_handler(self,name: str,pipeline: list[str]):        
        ACTION_REGISTRY:dict[str,ServiceOrientedArchitecture]=self.ACTION_REGISTRY

        first_in_class = ACTION_REGISTRY[pipeline[0]]
        last_out_class = ACTION_REGISTRY[pipeline[-1]]
        in_examples = first_in_class.Model.examples() if hasattr(first_in_class.Model,'examples') else None
        if in_examples:
            in_examples = [{'args':i['args']} for i in in_examples]
        
        def api_pipeline_handler(
                in_model: first_in_class.Model=Body(..., examples=in_examples),
                execution_time: str = self.EXECUTION_TIME_PARAM,
                timezone: self.VALID_TIMEZONES = self.TIMEZONE_PARAM,
        )->last_out_class.Model:
            
            self.api_ok()
            
            utc_execution_time, local_time = BasicCeleryTask.parse_execution_time(
                                            execution_time, timezone)
            # Get model data
            current_data = in_model.model_dump()
            # Get pipeline config
            pipeline_config = self.BasicApp.store().get(f'pipelines_config:{name}')
            expected_config_length = len(pipeline) + len(pipeline) - 1
            
            if pipeline_config:
                # Pipeline config should contain alternating models and mappings
                if len(pipeline_config) != expected_config_length:
                    raise HTTPException(
                        status_code=400,
                        detail="Pipeline config must follow pattern: [model1, map1to2, model2, map2to3, model3, ...]"
                    )
            else:
                pipeline_config = [None]*expected_config_length

            # Extract models and mappings from config
            pipeline_config_models = pipeline_config[::2]  # Every other item starting at 0
            pipeline_config_maps = pipeline_config[1::2]   # Every other item starting at 1
                

            # Initialize task chain with first action
            task_chain = self.perform_action.signature(
                # args=[data, name, prior_model_data, previous_name,previous_to_current_map],
                args=[
                    current_data,      # Input data
                    pipeline[0],       # First action name
                    pipeline_config_models[0],  # First model config
                    None,             # No previous action for first step
                    None              # No mapping for first step
                ]
            )

            # Chain subsequent actions
            previous_name = pipeline[0]
            for func_name, prior_model_data, mapping in zip(
                pipeline[1:],             # Remaining actions
                pipeline_config_models[1:],  # Remaining model configs
                pipeline_config_maps         # Mappings between steps
            ):
                # Add next action to chain
                task = self.perform_action.signature(
                    kwargs={
                        'name': func_name,
                        'prior_model_data': prior_model_data,
                        'previous_name': previous_name,
                        'previous_to_current_map': mapping,
                    }
                )
                task_chain = task_chain | task
                previous_name = func_name
            # Execute the chain
            chain_result = task_chain.apply_async(eta=utc_execution_time)
            # Collect all task IDs in the chain
            task_ids = []
            current_task = chain_result
            while current_task:
                task_ids.append(current_task.task_id)
                current_task = current_task.parent

            # Reverse to get IDs in execution order (first task first)
            task_ids = list(reversed(task_ids))
            
            # Log task IDs for debugging
            print(f"Pipeline task IDs in execution order: {task_ids}")
            # Return task information
            return TaskModel.create_task_response(
                chain_result, utc_execution_time, local_time, timezone)

        
        return api_pipeline_handler        

    def api_set_config_pipeline(self,
        name: str='FiboPrime',
        pipeline_config: list[dict] = [
            # 'Fibonacci'
            {
                "param": {
                    "mode": "slow"
                }
            },
            #'Fibonacci ret to PrimeNumberChecker args',
            {
                "number":"n"
            },
            # 'PrimeNumberChecker'
            {
                "param": {
                    "mode": "smart"
                }
            }
        ],
        ):
        self.api_ok()
        # FiCoChatPr
        # [
        # "Fibonacci",
        # "CollatzSequence",
        # "ChatGPTService",
        # "PrimeNumberChecker"
        # ]
        self.BasicApp.store().set(f'pipelines_config:{name}',pipeline_config)
        return {"status": "success", 'name':name, 'pipeline_config': pipeline_config}

    def api_get_config_pipeline(self,name: str='FiboPrime'):
        self.api_ok()
        pipeline_config = self.BasicApp.store().get(f'pipelines_config:{name}')
        return {"status": "success", 'name':name, 'pipeline_config': pipeline_config}
    

    def api_add_pipeline(self,name: str='FiboPrime', method: str = 'POST',
        pipeline: list[str] = ['Fibonacci','PrimeNumberChecker'],
        ):
        self.api_ok()
        # FiCoChatPr
        # [
        # "Fibonacci",
        # "CollatzSequence",
        # "ChatGPTService",
        # "PrimeNumberChecker"
        # ]
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
        self.pipelines[name] = pipeline

        # Create and add the dynamic route
        api_pipeline_handler = self.create_api_pipeline_handler(name,pipeline)
        self.router.add_api_route(
            path=path,
            endpoint=api_pipeline_handler,
            methods=[method],
            name=name,
            summary=f"Dynamic pipeline {name}:{pipeline}"
        )

        self.BasicApp.store().set('pipelines',self.pipelines)
        self.api_refresh_pipeline()
        return {"status": "created", "path": path, "method": method, "pipeline": pipeline}


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
    
elif conf.app_backend=='file':
    BasicApp:AppInterface = FileSystemApp(conf.file.url)
    
elif conf.app_backend=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(conf.rabbitmq.url,conf.rabbitmq.user,conf.rabbitmq.password,
                                             conf.mongo.url,conf.mongo.db,conf.celery.meta_table,
                                             conf.celery.broker)
else:
    raise ValueError(f'no back end of {conf.app_backend}')

celery_app = BasicApp.get_celery_app()
my_app = CeleryTask(BasicApp,celery_app,api)

## add original api
from CustomTask import Fibonacci
def my_fibo(n:int=0,mode:Literal['fast','slow']='fast'):
    m = Fibonacci.Model()
    m.param.mode = mode
    m.args.n = n
    return my_app.api_perform_action('Fibonacci', m.model_dump(),0)

my_app.add_web_api(my_fibo,'get','/myapi/fibonacci/').reload_routes()