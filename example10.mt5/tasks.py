import datetime
import sys
sys.path.append("..")

from typing import Literal, Optional
from fastapi.responses import HTMLResponse, RedirectResponse

from celery import Task
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, RabbitmqMongoApp, RedisApp, ServiceOrientedArchitecture
from Task.BasicAPIs import BasicCeleryTask
from config import *

from MT5Manager import Book, BookService, MT5Account, MT5CopyLastRatesService


class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app,
                        ACTION_REGISTRY={'BookService': BookService,}):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)
        self.router.get("/", response_class=HTMLResponse)(self.get_doc_page)
        self.router.post("/bookservice/")(self.api_book_service)
        self.router.post("/bookservice/schedule/")(self.api_schedule_book_service)
        self.router.get("/accounts/info")(self.api_account_info)
        self.router.get("/books/")(self.api_get_books)
        self.router.post("/books/send")(self.api_book_send)
        self.router.post("/books/send/schedule")(self.api_schedule_book_send)
        self.router.post("/books/close")(self.api_book_close)
        self.router.post("/books/change/price")(self.api_book_change_price)
        self.router.post("/books/change/tpsl")(self.api_book_change_tp_sl)
        self.router.get("/rates/")(self.api_rates_copy)
        
        @self.celery_app.task(bind=True)
        def celery_book_service(t: Task, acc: MT5Account, book: Book, action: str,**kwargs):
            """Celery task to calculate the nth book_service number."""
            model = BookService.Model.build(acc,book,action in ['send'])
            model.task_id = t.request.id
            ba = BookService.Action(model)
            res = ba.change_run(action, kwargs)()
            
            if action == 'getBooks':
                res = {f'{b.symbol}-{b.price_open}-{b.volume}-{b.ticket}': b.model_dump() for b in res.ret.books}
            elif action in ['send', 'changeP', 'changeTS', 'account_info']:
                res = res.ret.books[0].model_dump()
            else:
                res = res.model_dump()
            return self.is_json_serializable(res)

        self.celery_book_service = celery_book_service


        @celery_app.task(bind=True)
        def celery_rates_copy(t:Task,acc:MT5Account,
                    symbol:str,timeframe:str,count:int,debug:bool=False):
            model = MT5CopyLastRatesService.Model.build(acc)
            model.task_id = t.request.id
            act = MT5CopyLastRatesService.Action(model)
            res = act(symbol=symbol,timeframe=timeframe,count=count,debug=debug)
            return res.ret.model_dump()
        
        self.celery_rates_copy = celery_rates_copy
    
    async def get_doc_page(self,):
        return RedirectResponse("/docs")
    
    ########################### basic service
    async def api_book_service(self, acc: MT5Account, book: Book, action: str,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        self.api_ok()
        # Calculate execution time (eta)
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

        task = self.celery_book_service.apply_async(args=[acc.model_dump(),book.model_dump(),action], eta=execution_time)
        
        res = {'task_id': task.id}
        if execution_time: res['scheduled_for'] = execution_time
        return res
    
    async def api_schedule_book_service(self, acc: MT5Account, book: Book, action: str,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
                        description="Choose a timezone from the list")
    ):
        self.api_ok()
        """API to execute BookService task at a specific date and time, with timezone support."""
        # Convert to UTC for Celery
        local_dt,execution_time_utc = self.convert_to_utc(execution_time,timezone)
        
        # Schedule the task in UTC
        task = self.celery_book_service.apply_async(args=[acc.model_dump(),book.model_dump(),action], eta=execution_time)
        
        return {
            "task_id": task.id,
            f"scheduled_for_{timezone}": local_dt.isoformat(),
            "scheduled_for_utc": execution_time_utc.isoformat(),
            "timezone": timezone
        }
    
    async def api_rates_copy(self, acc: MT5Account, symbol: str, timeframe: str, count: int, debug: bool = False):
        """
        Endpoint to copy rates for a given MT5 account, symbol, timeframe, and count.
        
        :param acc: MT5Account object
        :param symbol: The symbol for which to copy rates
        :param timeframe: The timeframe for which to copy rates
        :param count: The number of rates to copy
        :param debug: Optional flag to enable debugging
        :return: Task ID of the Celery task
        """
        task = self.celery_rates_copy.delay(acc.model_dump(), symbol, timeframe, count, debug)
        return {'task_id': task.id}
    
    ########################### reuse basic service async and await
    async def api_account_info(self, acc: MT5Account):
        """Endpoint to fetch account information."""
        return await self.api_book_service(acc, Book(), action='account_info', eta=0)
    
    async def api_get_books(self, acc: MT5Account):
        """Endpoint to get books for a given MT5 account."""
        return await self.api_book_service(acc, Book(), action='getBooks', eta=0)

    async def api_book_send(self, acc: MT5Account, book: Book):
        """Endpoint to send a book."""
        return await self.api_book_service(acc, book, action='send', eta=0)

    async def api_schedule_book_send(self, acc: MT5Account, book: Book,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0],
           description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York",
                          "Europe/London", "Europe/Paris",
                          "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
                          ] = Query("Asia/Tokyo", 
                                    description="Choose a timezone from the list")
    ):
        return await self.api_schedule_book_service(acc.model_dump(), book.model_dump(), 'send', execution_time,timezone)

    async def api_book_close(self, acc: MT5Account, book: Book):
        """Endpoint to close a book."""
        return await self.api_book_service(acc, book, action='close', eta=0)
    
    async def api_book_change_price(self, acc: MT5Account, book: Book, p: float):
        """Endpoint to change the price of a book."""
        return await self.api_book_service(acc, book, action='changeP', p=p, eta=0)

    async def api_book_change_tp_sl(self, acc: MT5Account, book: Book, tp: float, sl: float):
        """Endpoint to change tp sl values of a book."""
        return await self.api_book_service(acc, book, action='changeTS', tp=tp, sl=sl, eta=0)

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
api.include_router(CeleryTask(BasicApp,celery_app).router, prefix="", tags=["bookservice"])
    