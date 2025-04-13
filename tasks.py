# Standard library imports
import datetime
import time
from threading import Thread
from typing import Literal

# FastAPI imports
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Custom imports
from CustomTask.MT5Manager import Book, MT5Account
from Task.Basic import (
    AppInterface,
    FileSystemApp,
    RabbitmqMongoApp,
    RedisApp,
    ServiceOrientedArchitecture,
    TaskModel
)
from Task.BasicAPIs import BasicCeleryTask,EXECUTION_TIME_PARAM,VALID_TIMEZONES,TIMEZONE_PARAM 
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
                in_model: first_in_class.Model=Body(..., examples=in_examples), # type: ignore
                execution_time: str = self.EXECUTION_TIME_PARAM,
                timezone: self.VALID_TIMEZONES = self.TIMEZONE_PARAM,
        )->dict:#last_out_class.Model:
            
            self.api_ok()
            
            utc_execution_time, local_time, (next_execution_time_str,timezone_str) = self.parse_execution_time(execution_time, timezone)
        
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
            # task_chain = self.perform_action.signature(
            #     # args=[data, name, prior_model_data, previous_name,previous_to_current_map],
            #     args=[
            #         current_data,      # Input data
            #         pipeline[0],       # First action name
            #         pipeline_config_models[0],  # First model config
            #         None,             # No previous action for first step
            #         None              # No mapping for first step
            #     ]
            # )

            # Initialize task chain with first action
            task_chain = self.celery_perform_simple_action.signature(                
                args=[
                    current_data,
                    pipeline_config_models[0],
                ]
            )

            # Chain subsequent actions
            for func_name, prior_model_data, mapping in zip(
                pipeline[1:],             # Remaining actions
                pipeline_config_models[1:],  # Remaining model configs
                pipeline_config_maps         # Mappings between steps
            ):
                # Add next action to chain
                task = self.celery_perform_translate_action.signature(
                    #  previous_data: dict, 
                    #  action_name:str, previous_to_current_map:dict, prior_data:dict,
                    kwargs={
                        'action_name': func_name,
                        'previous_to_current_map': mapping,
                        'prior_data': prior_model_data,
                    }
                )
                task_chain = task_chain | task
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
            self.BasicApp.set_task_status(task.task_id,status='SENDED')
            if next_execution_time_str:
                return TaskModel.create_task_response(
                    chain_result, utc_execution_time, local_time, timezone,
                    (next_execution_time_str,timezone_str))
            else:
                return TaskModel.create_task_response(
                    chain_result, utc_execution_time, local_time, timezone, None)
                    
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


from CustomTask import BookService, MT5CopyLastRatesService
class MT5CeleryTask(CeleryTask):
    def __init__(self, BasicApp, celery_app, root_fast_app:FastAPI, ACTION_REGISTRY = ACTION_REGISTRY):
        super().__init__(BasicApp, celery_app, root_fast_app, ACTION_REGISTRY)
        
        self.router.get( "/myfibo")(self.api_my_fibo)
        self.router.get( "/accounts/info")(self.api_account_info)
        self.router.get( "/books/")(self.api_get_books)
        self.router.post("/books/send")(self.api_book_send)
        self.router.post("/books/send/schedule")(self.api_schedule_book_send)
        self.router.post("/books/close")(self.api_book_close)
        self.router.post("/books/change/price")(self.api_book_change_price)
        self.router.post("/books/change/tpsl")(self.api_book_change_tp_sl)
        self.router.get( "/rates/")(self.api_rates_copy)

    def api_delete_task_delay(self,task_id:str,delay:int=30):
        self.api_ok()
        def delete_task_delay(task_id=task_id,delay=delay):
            print(f"deleting task {task_id} in {delay} seconds")
            time.sleep(delay)
            print(f"deleting task.")
            self.BasicApp.delete_task_meta(task_id)
            print(f"task {task_id} deleted")

        Thread(target=delete_task_delay,args=()).start()
        return {"status": "success", "task_id": task_id, "delay": delay}
# {
#   "param": {
#     "account": {
#         "account_id": xxxxx,
#         "password": "xxxxx",
#         "account_server": "xxxx"
#       },
#     "action": "account_info"
#   }
# }
    def api_my_fibo(self,n:int=13,mode:Literal['fast','slow']='fast'):
        m = Fibonacci.Model()
        m.param.mode = mode
        m.args.n = n
        res = self.api_perform_action('Fibonacci', m.model_dump(),'NOW')        
        self.api_delete_task_delay(res['task_id'],30)
        return res

    def api_account_info(self, acc: MT5Account):
        """Endpoint to fetch account information."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'account_info'
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res
    
    def api_get_books(self, acc: MT5Account):
        """Endpoint to get books for a given MT5 account."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'getBooks'
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res

    def api_book_send(self, acc: MT5Account, book: Book):
        """Endpoint to send a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'send'
        m.param.book= book
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res

    def api_schedule_book_send(self, acc: MT5Account, 
        symbol:str='USDJPY',sl:float=147.0,tp:float=150.0,price_open:float=148.0,volume:float=0.01,
        execution_time:str=EXECUTION_TIME_PARAM,
        timezone:VALID_TIMEZONES=TIMEZONE_PARAM
    ):
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'send'
        m.param.book= Book(symbol=symbol,sl=sl,tp=tp,price_open=price_open,volume=volume).as_plan()
        return self.api_perform_action('BookService', m.model_dump(), execution_time,timezone)

    def api_book_close(self, acc: MT5Account, book: Book):
        """Endpoint to close a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'close'
        m.param.book= book
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res
    
    def api_book_change_price(self, acc: MT5Account, book: Book, p: float):
        """Endpoint to change the price of a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'changeP'
        m.param.book= book
        m.param.book.price_open = p
        m.args.p = p
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res

    def api_book_change_tp_sl(self, acc: MT5Account, book: Book, tp: float, sl: float):
        """Endpoint to change tp sl values of a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'changeTS'
        m.param.book= book
        m.param.book.tp = tp
        m.param.book.sl = sl
        m.args.tp = tp
        m.args.sl = sl
        res = self.api_perform_action('BookService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res
    
    def api_rates_copy(self, acc: MT5Account, symbol: str, timeframe: str, count: int, debug: bool = False):
        """
        Endpoint to copy rates for a given MT5 account, symbol, timeframe, and count.
        """
        m = MT5CopyLastRatesService.Model()
        m.param.account = acc
        m.args.symbol = symbol
        m.args.timeframe = timeframe
        m.args.count = count
        m.args.debug = debug
        res = self.api_perform_action('MT5CopyLastRatesService', m.model_dump(),'NOW')
        self.api_delete_task_delay(res['task_id'],30)
        return res
    
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
my_app = MT5CeleryTask(BasicApp,celery_app,api)

## add original api
from CustomTask import Fibonacci
def my_fibo(n:int=0,mode:Literal['fast','slow']='fast'):
    m = Fibonacci.Model()
    m.param.mode = mode
    m.args.n = n
    return my_app.api_perform_action('Fibonacci', m.model_dump(),'NOW')

my_app.add_web_api(my_fibo,'get','/myapi/fibonacci/').reload_routes()