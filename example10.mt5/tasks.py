import sys
sys.path.append("..")

from celery.app import task as Task
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import FastAPI, HTTPException
    
from Task.Customs import ServiceOrientedArchitecture
from Task.Basic import AppInterface,RedisApp,RabbitmqMongoApp
from MT5Manager import Book, BookService, MT5Account, MT5CopyLastRatesService, MT5Manager

def config():
    import os
    import requests
    os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')

    # for app back {redis | mongodbrabbitmq}
    APP_BACK_END = os.getenv('APP_BACK_END', 'redis')  # Defaulting to a common local endpoint
    APP_INVITE_CODE = os.getenv('APP_INVITE_CODE', '123')  # Replace with appropriate default
    APP_SECRET_KEY = os.getenv('APP_SECRET_KEY', 'super_secret_key')  # Caution: replace with a strong key in production

    # Constants with clear definitions
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))  # Use environment variable with a default fallback
    SESSION_DURATION = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    UVICORN_PORT = int(os.getenv('UVICORN_PORT', 8000))  # Using an environment variable fallback
    FLOWER_PORT = int(os.getenv('UVICORN_PORT', 5555))  # Using an environment variable fallback
    # External service URLs with sensible defaults
    RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'localhost:15672')
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'guest')

    MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    MONGO_DB = os.getenv('MONGO_DB', 'tasks')

    CELERY_META = os.getenv('CELERY_META', 'celery_taskmeta')
    CELERY_RABBITMQ_BROKER = os.getenv('CELERY_RABBITMQ_BROKER', 'amqp://localhost')

    # Redis URL configuration with fallback
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Handle external IP fetching gracefully with error handling
    try:
        EX_IP = requests.get('https://v4.ident.me/').text
    except requests.RequestException:
        EX_IP = '127.0.0.1'  # Fallback to a default value if the request fails
    print('APP_BACK_END :',APP_BACK_END)
    print('APP_INVITE_CODE :',APP_INVITE_CODE)
    print('APP_SECRET_KEY :',APP_SECRET_KEY)
    print('ALGORITHM :',ALGORITHM)
    print('ACCESS_TOKEN_EXPIRE_MINUTES :',ACCESS_TOKEN_EXPIRE_MINUTES)
    print('SESSION_DURATION :',SESSION_DURATION)
    print('UVICORN_PORT :',UVICORN_PORT)
    print('FLOWER_PORT :',FLOWER_PORT)
    print('EX_IP :',EX_IP)

    if APP_BACK_END=='mongodbrabbitmq':
        print('RABBITMQ_URL :',RABBITMQ_URL)
        print('RABBITMQ_USER :',RABBITMQ_USER)
        print('RABBITMQ_PASSWORD :',RABBITMQ_PASSWORD)

        print('MONGO_URL :',MONGO_URL)
        print('MONGO_DB :',MONGO_DB)

        print('CELERY_META :',CELERY_META)
        print('CELERY_RABBITMQ_BROKER :',CELERY_RABBITMQ_BROKER)
    if APP_BACK_END=='redis':
        # Redis URL configuration with fallback
        print('REDIS_URL :',REDIS_URL)
    return (APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,
            ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,
            FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,
            MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP)

APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP = config()

if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp(REDIS_URL)
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,
                                             MONGO_URL,MONGO_DB,CELERY_META,
                                             CELERY_RABBITMQ_BROKER)
else:
    raise ValueError(f'no back end of {APP_BACK_END}')
ServiceOrientedArchitecture.BasicApp  = BasicApp

celery_app = BasicApp.get_celery_app()
def api_ok():
    if BasicApp.check_services():return
    raise HTTPException(
        status_code=503, detail={'error': 'service not healthy'})

class CeleryTask:

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
    
    @staticmethod
    @api.get("/", response_class=HTMLResponse)
    async def get_doc_page():
        return RedirectResponse("/docs")
    
    ########################### essential function
    @staticmethod
    def is_json_serializable(value) -> bool:
        res = isinstance(value, (int, float, bool, str,
                                 list, dict, set, tuple)) or value is None
        if res: return value
        raise ValueError("Result is not JSON serializable")

    @api.get("/tasks/")
    def api_list_tasks():
        api_ok()
        return BasicApp.get_tasks_list()

    @api.get("/tasks/meta/{task_id}")
    def api_task_meta(task_id: str):
        api_ok()
        return BasicApp.get_task_meta(task_id)

    @api.get("/tasks/stop/{task_id}")
    def api_task_stop(task_id: str):
        api_ok()
        BasicApp.send_data_to_task(task_id,{'status': 'REVOKED'})

    @api.get("/workers/")
    def get_workers():
        # current_user: UserModels.User = Depends(AuthService.get_current_root_user)):
        api_ok()
        inspector = celery_app.control.inspect()
        active_workers = inspector.active() or {}
        stats:dict[str,dict] = inspector.stats() or {}

        workers = []
        for worker_name, data in stats.items():
            workers.append({
                "worker_name": worker_name,
                "status": "online" if worker_name in active_workers else "offline",
                "active_tasks": len(active_workers.get(worker_name, [])),
                "total_tasks": data.get('total', 0)
            })
        return workers

    ########################### original function
    @staticmethod
    @celery_app.task(bind=True)
    def add_terminal(t:Task, broker: str, path: str):
        return MT5Manager().get_singleton().add_terminal(broker,path)    
    
    @staticmethod
    @api.post("/terminals/add")
    def api_add_terminal(broker: str, path: str):
        api_ok()
        """Endpoint to add a terminal to MT5."""
        task = CeleryTask.add_terminal.delay(broker, path)
        return {'task_id': task.id}
        
    @staticmethod
    @celery_app.task(bind=True)
    def get_terminal(t:Task):
        print(MT5Manager().get_singleton().terminals)
        return { k:[i.exe_path for i in v] for k,v in MT5Manager().get_singleton().terminals.items()}
    
    @staticmethod
    @api.get("/terminals/")
    def api_get_terminal():
        api_ok()
        task = CeleryTask.get_terminal.delay()
        return {'task_id': task.id}
    
    @staticmethod
    @celery_app.task(bind=True)
    def book_action(t: Task, acc: MT5Account, book: Book, action: str,**kwargs):
        """
        Generic task for performing book-related actions.
        
        :param acc: MT5Account object
        :param book: Book object
        :param action: The action to perform (e.g., 'getBooks', 'send', 'close', 'changeP', 'changeTS')
        :param kwargs: Additional parameters for the action (e.g., price, tp, sl)
        :return: The result of the action
        """

        model = BookService.Model.build(acc,book,action in ['send'])
        model.task_id = t.request.id
        ba = BookService.Action(model)
        res = ba.change_run(action, kwargs)()
        
        if action == 'getBooks':
            return {f'{b.symbol}-{b.price_open}-{b.volume}-{b.ticket}': b.model_dump() for b in res.ret.books}
        elif action in ['send', 'changeP', 'changeTS', 'account_info']:
            return res.ret.books[0].model_dump()
        else:
            return res.model_dump()
        
    @staticmethod
    @api.get("/accounts/info")
    def api_account_info(acc: MT5Account):
        api_ok()
        """Endpoint to fetch account information."""
        task = CeleryTask.book_action.delay(acc.model_dump(), Book().model_dump(), action='account_info')
        return {'task_id': task.id}
    
    @staticmethod
    @api.get("/books/")
    def api_get_books(acc: MT5Account):
        api_ok()
        """Endpoint to get books for a given MT5 account."""
        task = CeleryTask.book_action.delay(acc.model_dump(), Book().model_dump(), action='getBooks')
        return {'task_id': task.id}

    
    @staticmethod
    @api.post("/books/send")
    def api_book_send(acc: MT5Account, book: Book):
        api_ok()
        """Endpoint to send a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='send')
        return {'task_id': task.id}

    
    @staticmethod
    @api.post("/books/close")
    def api_book_close(acc: MT5Account, book: Book):
        api_ok()
        """Endpoint to close a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='close')
        return {'task_id': task.id}

    
    @staticmethod
    @api.post("/books/change/price")
    def api_book_change_price(acc: MT5Account, book: Book, p: float):
        api_ok()
        """Endpoint to change the price of a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='changeP', p=p)
        return {'task_id': task.id}

    
    @staticmethod
    @api.post("/books/change/tpsl")
    def api_book_change_tp_sl(acc: MT5Account, book: Book, tp: float, sl: float):
        api_ok()
        """Endpoint to change tp sl values of a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='changeTS', tp=tp, sl=sl)
        return {'task_id': task.id}

    
    @staticmethod
    @celery_app.task(bind=True)
    def rates_copy(t:Task,acc:MT5Account,
                   symbol:str,timeframe:str,count:int,debug:bool=False):
        model = MT5CopyLastRatesService.Model.build(acc)
        model.task_id = t.request.id
        act = MT5CopyLastRatesService.Action(model)
        res = act(symbol=symbol,timeframe=timeframe,count=count,debug=debug)
        return res.ret.model_dump()
    
    @staticmethod
    @api.get("/rates/")
    def api_rates_copy(acc: MT5Account, symbol: str, timeframe: str, count: int, debug: bool = False):
        api_ok()
        """
        Endpoint to copy rates for a given MT5 account, symbol, timeframe, and count.
        
        :param acc: MT5Account object
        :param symbol: The symbol for which to copy rates
        :param timeframe: The timeframe for which to copy rates
        :param count: The number of rates to copy
        :param debug: Optional flag to enable debugging
        :return: Task ID of the Celery task
        """
        task = CeleryTask.rates_copy.delay(acc.model_dump(), symbol, timeframe, count, debug)
        return {'task_id': task.id}
