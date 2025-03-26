from typing import Optional
from CustomTask.MT5Manager import Book, MT5Account, MT5Action, MT5Manager
from Task.Basic import ServiceOrientedArchitecture
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(e)

from pydantic import BaseModel    
        
class BookServiceActionTypes:
    send:str ='send'
    changeP:str ='changeP'
    changeTS:str ='changeTS'
    account_info:str ='account_info'
    getBooks:str = 'getBooks'

class BookService(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):
            
        class Param(BaseModel):
            account:MT5Account
            book:Book
            action:str = BookServiceActionTypes.account_info

        class Args(BaseModel):
            p:float=-1.0 #price
            tp:float=0.0
            sl:float=0.0

        class Return(BaseModel):
            first_book:Optional[Book] = None
            books:list[Book] = []
            books_dict:dict[str,Book] = {}

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        param:Param
        args:Args = Args()
        ret:Return = Return()
        logger:Logger = Logger(name='BookService')

        @staticmethod
        def build(acc:MT5Account,book:Book,plan=False):
            if isinstance(acc, dict):
                acc = MT5Account(**acc)
            if isinstance(book, dict):
                book = Book(**book)
            if plan:book = book.as_plan()
            param = BookService.Model.Param(account=acc,book=book)
            return BookService.Model(param=param)
        
    class Action(MT5Action, ServiceOrientedArchitecture.Action):
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            action = self.model.param.action
            acc = self.model.param.account
            book = self.model.param.book
            self.model = BookService.Model.build(acc,book,action in ['send'])            
            self.change_run(action, kwargs)
            res = MT5Manager().get_singleton().do(self)
            if isinstance(res,Book):
                res = [res]
            self.model.ret.books = res
            return self.model
        
        def __init__(self, model=None):
            if isinstance(model, dict):
                # Remove keys with None values from the dictionary
                nones = [k for k, v in model.items() if v is None]
                for i in nones:
                    del model[i]
                # Initialize the model as an instance of BookService.Model
                model = BookService.Model(**model)
            # Store the model instance
            self.model: BookService.Model = model
            account = self.model.param.account

            super().__init__(account)
            self.book = self.model.param.book
        
        def log_and_send(self,info:str):
            self.logger.log(info)
            self.send_data_to_task(info)

        def change_run(self, func_name, kwargs):
            self.log_and_send(f'change run: {func_name}, {kwargs}')
            self.model.args = BookService.Model.Args(**kwargs)
            self.book_run = lambda: getattr(self.book, func_name)(**kwargs)
            return self

        def run(self):
            # tbs = {f'{b.symbol}-{b.price_open}-{b.volume}':b.model_dump() for b in Book().getBooks()}
            action = self.model.param.action
            self.model:BookService.Model = self.book_run()            
            if action == BookServiceActionTypes.getBooks:
                self.model.ret.books_dict = {f'{b.symbol}-{b.price_open}-{b.volume}-{b.ticket}': b for b in self.model.ret.books}
                self.model.ret.books = []
            elif action in [BookServiceActionTypes.send,
                            BookServiceActionTypes.changeP,
                            BookServiceActionTypes.changeTS,
                            BookServiceActionTypes.account_info]:
                self.model.ret.first_book = self.model.ret.books[0]
                self.model.ret.books = []
            else:
                self.model.ret.first_book = None
                self.model.ret.books = []
                self.model.ret.books_dict = {}
                raise ValueError(f'no action of {action}')
            return self.model
        

# @descriptions('Retrieve MT5 last N bars data in MetaTrader 5 terminal.',
#             # account='MT5Account object for login.',
#             # symbol='Financial instrument name (e.g., EURUSD).',
#             # timeframe='Timeframe from which the bars are requested. {M1, H1, ...}',
#             # # start_pos='Index of the first bar to retrieve.',
#             # count='Number of bars to retrieve.'
#             )
class MT5CopyLastRatesService:
    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            account: MT5Account = None
        
        class Args(BaseModel):
            symbol: str = "null"
            timeframe: str = "H1"
            count: int = 10
            debug: bool = False
            retry_times_on_error: int = 3

        class Return(BaseModel):
            symbol: str = "null"
            timeframe: str = "H1"
            count: int = 10
            rates: list = None
            digitsnum: int = 0
            error: tuple = None
            header: str='```{symbol} {count} Open, High, Low, Close (OHLC) data points for the {timeframe} timeframe\n{join_formatted_rates}\n```'

            def __str__(self):
                if self.rates is None:
                    return f"Error: {self.error}"

                if self.digitsnum > 0:
                    n = self.digitsnum
                    formatted_rates = [
                        f'{r[1]:.{n}f}\n{r[2]:.{n}f}\n{r[3]:.{n}f}\n{r[4]:.{n}f}\n'
                        for r in self.rates
                    ]
                else:
                    formatted_rates = [
                        f'{int(r[1])}\n{int(r[2])}\n{int(r[3])}\n{int(r[4])}\n'
                        for r in self.rates
                    ]

                # Join the formatted rates into a single string
                join_formatted_rates = '\n'.join(formatted_rates)

                # Use the customizable header format to return the final output
                return self.header.format(
                    symbol=self.symbol,
                    count=self.count,
                    timeframe=self.timeframe,
                    join_formatted_rates=join_formatted_rates
                )

        # Set default instances for Param, Args, and Return to enable easy initialization
        param: Param = Param()
        args: Args = Args()
        ret: Return = Return()

        @staticmethod
        def build(acc:MT5Account):
            if isinstance(acc, dict):
                acc = MT5Account(**acc)
            param = MT5CopyLastRatesService.Model.Param(account=acc)
            return MT5CopyLastRatesService.Model(param=param)

    class Action(MT5Action, ServiceOrientedArchitecture.Action):
        _start_pos = 0
        _digitsnum = {
            'AUDJPY': 3, 'CADJPY': 3, 'CHFJPY': 3, 'CNHJPY': 3, 'EURJPY': 3,
            'GBPJPY': 3, 'USDJPY': 3, 'NZDJPY': 3, 'XAUJPY': 0, 'JPN225': 1, 'US500': 1
        }

        def __init__(self, model=None):
            # Remove None values from the model if it's a dictionary
            if isinstance(model, dict):
                model = {k: v for k, v in model.items() if v is not None}
                model = MT5CopyLastRatesService.Model(**model)
            self.model: MT5CopyLastRatesService.Model = model
            account = self.model.param.account
            super().__init__(account)

        def _update_args(self, symbol: str = None, timeframe: str = None, count: int = None, debug: bool = None):
            # Update model args only if provided (fall back to existing ones otherwise)
            self.model.args.symbol = symbol if symbol is not None else self.model.args.symbol
            self.model.args.timeframe = timeframe if timeframe is not None else self.model.args.timeframe
            self.model.args.count = count if count is not None else self.model.args.count
            self.model.args.debug = debug if debug is not None else self.model.args.debug

        def __call__(self, symbol: str, timeframe: str, count: int, debug: bool = False):
            super().__call__()
            self._update_args(symbol, timeframe, count, debug)
            # Perform the MT5 action
            res: MT5CopyLastRatesService.Model = MT5Manager().get_singleton().do(self)
            self.model.ret.symbol = symbol
            self.model.ret.timeframe = timeframe
            self.model.ret.count = count
            return res

        def run(self, symbol: str = None, timeframe: str = None, count: int = None, debug: bool = None):
            self._update_args(symbol, timeframe, count, debug)

            if self.model.args.debug:
                # For debugging, return simple mock values
                self.model.ret.rates = None
                self.model.ret.digitsnum = 3  # Mock value for digits
                return self.model

            # Simplified timeframe mapping using getattr with a fallback
            tf = getattr(mt5, f"TIMEFRAME_{self.model.args.timeframe}", mt5.TIMEFRAME_H1)

            # Get symbol's digit info with default value of 3
            digitsnum = self._digitsnum.get(self.model.args.symbol, 3)

            # Retrieve rates using MT5 API
            rates = mt5.copy_rates_from_pos(self.model.args.symbol, tf, self._start_pos, self.model.args.count)

            if rates is None:
                error_code, error_msg = mt5.last_error()
                raise ValueError(f"Failed to retrieve rates: {error_msg} (Error code: {error_code})")

            # Populate the return model with results
            self.model.ret.rates = rates.tolist()
            self.model.ret.digitsnum = digitsnum
            self.model.ret.error = None

            return self.model


# Example usage:
# model_dict = {
#     "param": {"account": {...}, "retry_times_on_error": 3},
# }
# action = MT5CopyLastRatesService.Action(model=model_dict)
# result = action(symbol="USDJPY", timeframe="H4", count=10)
# print(result)
