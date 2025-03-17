
import datetime
import sys
from typing import Literal, Optional
sys.path.append("..")

from fastapi import HTTPException, Query
from celery.app import task as Task

from basic_tasks import BasicApp, BasicCeleryTask, api, api_ok

from Task.Customs import ServiceOrientedArchitecture
from Task.Basic import ServiceOrientedArchitecture
ServiceOrientedArchitecture.BasicApp = BasicApp
from MT5Manager import Book, BookService, MT5Account, MT5CopyLastRatesService, MT5Manager


celery_app = BasicApp.get_celery_app()
def api_ok():
    if BasicApp.check_services():return
    raise HTTPException(
        status_code=503, detail={'error': 'service not healthy'})

class CeleryTask(BasicCeleryTask):
    api = api
    
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
    @api.post("/books/send/schedule")
    def api_book_send(acc: MT5Account, book: Book,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0],
           description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York",
                          "Europe/London", "Europe/Paris",
                          "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
                          ] = Query("Asia/Tokyo", 
                                    description="Choose a timezone from the list")
    ):
        api_ok()
        """API to execute Fibonacci task at a specific date and time, with timezone support."""
        # Convert to UTC for Celery
        local_dt,execution_time_utc = CeleryTask.convert_to_utc(execution_time,timezone)
        
        """Endpoint to send a book."""
        task = CeleryTask.book_action.apply_async(
            args=[acc.model_dump(), book.model_dump(), 'send'], eta=execution_time)

        return {
            "args":[book.model_dump(), 'send'],
            "task_id": task.id,
            f"scheduled_for_{timezone}": local_dt.isoformat(),
            "scheduled_for_utc": execution_time_utc.isoformat(),
            "timezone": timezone
        }
    
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
