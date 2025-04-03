# Standard library imports
import datetime
from typing import Literal, Optional

# FastAPI imports
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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
        
    def create_pipeline_handler(self,pipeline: list[str],                    
                                eta: Optional[int]=0):        
        ACTION_REGISTRY:dict[str,ServiceOrientedArchitecture]=self.ACTION_REGISTRY

        first_in_class = ACTION_REGISTRY[pipeline[0]]
        last_out_class = ACTION_REGISTRY[pipeline[-1]]
        in_examples = first_in_class.Model.examples() if hasattr(first_in_class.Model,'examples') else None
        
        async def pipeline_handler(
                in_model: first_in_class.Model=Body(..., examples=in_examples),
                eta: Optional[int]=eta
        )->last_out_class.Model:
            
            current_data = in_model.model_dump()
            
            # Create a chain of tasks
            task_chain = None
            for i, func_name in enumerate(pipeline):
                if i == 0:
                    # Start the chain with the first task, signature will not execute immediately
                    task_chain = self.perform_action.signature(func_name, current_data)
                else:
                    # Add subsequent tasks to the chain
                    # Each task will receive the result of the previous task
                    task_chain = task_chain.chain(
                        self.perform_action.signature(name=func_name))
                            
            # Calculate execution time (eta)
            now_t = datetime.datetime.now(datetime.timezone.utc)
            execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

            # chain_result is a task object with task_id and other attributes
            chain_result = task_chain.apply_async(eta=execution_time)

            # You can access task_id with chain_result.task_id
            task_id = chain_result.task_id
            
            return TaskModel(task_id=task_id,
                            scheduled_for_utc=execution_time
                            ).model_dump(exclude_none=True)
        
            # # This will wait for the entire chain to complete
            # final_result = chain_result.get()                
            # # For compatibility with the existing return format
            # result.append(final_result)

            # result.append(ACTION_REGISTRY[func_name].Model.examples()[0])
            # return {"result": result}
        
        return pipeline_handler
    
    def api_add_pipeline(self,name: str='FiboPrime', method: str = 'POST',
                         pipeline: list[str] = ['Fibonacci','PrimeNumberChecker'],
                         eta: Optional[int]=0):
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
        self.pipelines[name] = pipeline

        # Create and add the dynamic route
        pipeline_handler = self.create_pipeline_handler(pipeline,eta)
        self.router.add_api_route(
            path=path,
            endpoint=pipeline_handler,
            methods=[method],
            name=name,
            summary=f"Dynamic pipeline {name}:{pipeline}"
        )

        # self.refresh_openapi(self.router)
        self.BasicApp.store().set('pipelines',self.pipelines)
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