# Standard library imports
import datetime
from typing import Literal, Optional

# FastAPI imports
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import pytz

# Custom imports
from CustomTask.MT5Manager import Book, MT5Account
from Task.Basic import (
    AppInterface,
    FileSystemApp,
    RabbitmqMongoApp,
    RedisApp,
    ServiceOrientedArchitecture
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
        
    def create_api_pipeline_handler(self,pipeline: list[str]):        
        ACTION_REGISTRY:dict[str,ServiceOrientedArchitecture]=self.ACTION_REGISTRY

        first_in_class = ACTION_REGISTRY[pipeline[0]]
        last_out_class = ACTION_REGISTRY[pipeline[-1]]
        in_examples = first_in_class.Model.examples() if hasattr(first_in_class.Model,'examples') else None
        
        def api_pipeline_handler(
                in_model: first_in_class.Model=Body(..., examples=in_examples),
                execution_time: str = Query(
                    'NOW',
                    description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS (2025-04-03T06:00:30), NOW: no use"
                ),
                timezone: Literal[
                    "UTC", "Asia/Tokyo", "America/New_York", "Europe/London",
                    "Europe/Paris", "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
                ] = Query(
                    "Asia/Tokyo",
                    description="Choose a timezone from the list, if execution_time is not NOW"
                )
        )->last_out_class.Model:
            
            self.api_ok()
            
            # Parse execution time
            utc_execution_time = None
            local_time = None

            try:
                if execution_time.upper() == "NOW":
                    utc_execution_time = datetime.datetime.now(datetime.timezone.utc)
                elif execution_time.isdigit():
                    delay_seconds = int(execution_time)
                    utc_execution_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay_seconds)
                else:
                    # Parse the datetime string
                    local_time = datetime.datetime.strptime(execution_time, "%Y-%m-%dT%H:%M:%S")
                    # Localize it to the given timezone
                    tz = pytz.timezone(timezone)
                    local_time = tz.localize(local_time)
                    # Convert to UTC
                    utc_execution_time = local_time.astimezone(pytz.UTC)
            except Exception as e:
                raise ValueError(f"Invalid execution_time format: {execution_time}. Error: {str(e)}")
            
            # Get model data
            current_data = in_model.model_dump()
            
            # Build task chain
            task_chain = self.perform_action.signature(args=[current_data, pipeline[0]])
            previous_name = pipeline[0]
            for func_name in pipeline[1:]:
                task_chain = task_chain | self.perform_action.signature(
                            kwargs={'name':func_name, 'previous_name':previous_name})
                previous_name = func_name
                
            # Execute the chain
            chain_result = task_chain.apply_async(eta=utc_execution_time)
            
            # Return task information
            return TaskModel(task_id=chain_result.task_id,
                            scheduled_for_the_timezone=local_time,
                            timezone=timezone if local_time is not None else None,
                            scheduled_for_utc=utc_execution_time,
                        ).model_dump(exclude_none=True)

        
        return api_pipeline_handler        
    
    def api_add_pipeline(self,name: str='FiboPrime', method: str = 'POST',
        pipeline: list[str] = ['Fibonacci','PrimeNumberChecker'],
        ):        
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
        api_pipeline_handler = self.create_api_pipeline_handler(pipeline)
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
        
        self.router.get( "/accounts/info")(self.api_account_info)
        self.router.get( "/books/")(self.api_get_books)
        self.router.post("/books/send")(self.api_book_send)
        self.router.post("/books/send/schedule")(self.api_schedule_book_send)
        self.router.post("/books/close")(self.api_book_close)
        self.router.post("/books/change/price")(self.api_book_change_price)
        self.router.post("/books/change/tpsl")(self.api_book_change_tp_sl)
        self.router.get( "/rates/")(self.api_rates_copy)


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

    def api_account_info(self, acc: MT5Account):
        """Endpoint to fetch account information."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'account_info'
        return self.api_perform_action('BookService', m.model_dump(),'NOW')
    
    def api_get_books(self, acc: MT5Account):
        """Endpoint to get books for a given MT5 account."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'getBooks'
        return self.api_perform_action('BookService', m.model_dump(),'NOW')

    def api_book_send(self, acc: MT5Account, book: Book):
        """Endpoint to send a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'send'
        m.param.book= book
        return self.api_perform_action('BookService', m.model_dump(),'NOW')

    def api_schedule_book_send(self, acc: MT5Account, 
    symbol:str='USDJPY',sl:float=147.0,tp:float=150.0,price_open:float=148.0,volume:float=0.01,
    execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0],
           description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York",
                          "Europe/London", "Europe/Paris",
                          "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
                          ] = Query("Asia/Tokyo", 
                                    description="Choose a timezone from the list")
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
        return self.api_perform_action('BookService', m.model_dump(),'NOW')
    
    def api_book_change_price(self, acc: MT5Account, book: Book, p: float):
        """Endpoint to change the price of a book."""
        m = BookService.Model()
        m.param.account = acc
        m.param.action= 'changeP'
        m.param.book= book
        m.param.book.price_open = p
        m.args.p = p
        return self.api_perform_action('BookService', m.model_dump(),'NOW')

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
        return self.api_perform_action('BookService', m.model_dump(),'NOW')
    
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
        return self.api_perform_action('MT5CopyLastRatesService', m.model_dump(),'NOW')
    
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