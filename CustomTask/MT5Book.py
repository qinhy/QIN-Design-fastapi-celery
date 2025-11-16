import math
from typing import Literal
from pydantic import Field
import uuid
from CustomTask.MT5Manager import Book, MT5Account, MT5Action, MT5Manager
from Task.Basic import AppInterface, ServiceOrientedArchitecture
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(e)

from pydantic import BaseModel    
        
class BookServiceActionTypes:
    send:str = 'send'
    close:str = 'close'
    changeP:str = 'changeP'
    changeTS:str = 'changeTS'
    getBooks:str = 'getBooks'
    account_info:str = 'account_info'

######## test account_info
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

######## test send
# {
#     "param": {
#         "account": {
#             "account_id": xxxxxx,
#             "password": "xxxxxx",
#             "account_server": "xxxxxxx"
#         },
#         "action": "send",
#         "book": {
#             "symbol": '',
#             "sl": 0.0,
#             "tp": 0.0,
#             "price_open": -1.0,
#             "volume": -1.0
#         }
#     }
# }
class BookCloseService(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):
            
        class Parameter(MT5Account):
            pass

        class Arguments(BaseModel):
            ticket: int = -1
            
        class Returness(BaseModel):
            ok:bool=False

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass
        
        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Returness = Returness()
        logger:Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action, MT5Action):
        
        def __init__(self, model,BasicApp:AppInterface,level=None):            
            super().__init__(model,BasicApp,level)
            MT5Action.__init__(self,self.model.para)
            self.model:BookCloseService.Model = self.model
            
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            return MT5Manager().get_singleton().do(self)

        def run(self):
            bs = Book().getBooks()
            for b in bs:
                if self.model.args.ticket==b.ticket:
                    try:
                        b.close()
                        self.model.rets.ok=True
                    except:
                        self.model.rets.ok=False
            
            self.model.para = MT5Account()
            return self.model


class BookSendService(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):
            
        class Parameter(MT5Account):
            pass

        class Arguments(BaseModel):
            symbol: str = 'USDJPY'
            volume:  float = -1
            price_open:  float = -1
            tp: float = -1
            sl: float = -1
            
        class Returness(BaseModel):
            ok:bool=False

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass
        
        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Returness = Returness()
        logger:Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action, MT5Action):
        
        def __init__(self, model,BasicApp:AppInterface,level=None):            
            super().__init__(model,BasicApp,level)
            MT5Action.__init__(self,self.model.para)
            self.model:BookSendService.Model = self.model
            
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            return MT5Manager().get_singleton().do(self)

        def run(self):
            bs = Book(symbol=self.model.args.symbol,
                      volume=self.model.args.volume,
                      price_open=self.model.args.price_open,
                      tp=self.model.args.tp,
                      sl=self.model.args.sl).as_plan()
            try:
                bs.send()
                self.model.rets.ok=True
            except:
                self.model.rets.ok=False

            self.model.para = MT5Account()
            self.model.para = MT5Account()
            return self.model
       

class MT5AccountInfo(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):
            
        class Parameter(MT5Account):
            pass

        class Arguments(BaseModel):
            pass
            
        class Returness(BaseModel):
            info: dict = Field(default_factory=dict)

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass
        
        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Returness = Returness()
        logger:Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action, MT5Action):
        
        def __init__(self, model,BasicApp:AppInterface,level=None):            
            super().__init__(model,BasicApp,level)
            MT5Action.__init__(self,self.model.para)
            self.model:MT5AccountInfo.Model = self.model
            
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            return MT5Manager().get_singleton().do(self)

        def run(self):
            self.model.rets.info = Book().account_info()
            self.model.para = MT5Account()
            return self.model
 
class BookSplitService(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):

        class Parameter(MT5Account):
            # minimum lot size to respect when splitting (you can set this from outside)
            min_lot: float = 0.01
            mode: Literal["symmetric", "up", "down"] = "symmetric"

        class Arguments(BaseModel):
            ticket: int = -1
            n_parts: int = 3
            price_range: int = 50  # the points range

        class Returness(BaseModel):
            ok: bool = False

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        version: Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Returness = Returness()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action, MT5Action):

        def __init__(self, model, BasicApp: AppInterface, level=None):
            super().__init__(model, BasicApp, level)
            self.model: BookSplitService.Model = model
            MT5Action.__init__(self, self.model.para)

        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            return MT5Manager().get_singleton().do(self)
        
        def split_integer(self, total, parts):
            base = total // parts          # minimum value for each part
            remainder = total % parts      # how many parts get +1
            return sorted([base + 1 if i < remainder else base for i in range(parts)])
            # print(split_integer(5, 3))   # [2, 2, 1]
            # print(split_integer(10, 4))  # [3, 3, 2, 2]
            # print(split_integer(7, 7))   # [1, 1, 1, 1, 1, 1, 1]

        def _compute_price_bounds_int(self, center: int, price_range: int, n_parts: int, mode: str,
        ) -> tuple[int, int]:
            if n_parts <= 1 or price_range == 0:
                return center, center

            if mode == "symmetric":
                low = center - int(math.ceil(price_range / 2.0))
                high = center + int(math.floor(price_range / 2.0))
            elif mode == "up":
                low = center
                high = center + price_range
            elif mode == "down":
                low = center - price_range
                high = center
            else:
                raise ValueError(f"Unknown mode: {mode}")

            return low, high

        def run(self):
            para = self.model.para
            args = self.model.args

            if args.n_parts <= 0 or args.price_range < 0:
                self.model.rets.ok = False
                return self.model

            ticket = args.ticket

            # Find the original order by ticket
            original = None
            for b in Book().getBooks():
                if b.ticket == ticket:
                    original = b
                    break

            if original is None:
                self.model.rets.ok = False
                return self.model

            symbol = original.symbol
            total_volume = original.volume
            order_price = original.price_open
            tp = original.tp
            sl = original.sl

            digits = int(mt5.symbol_info(original.symbol).digits)
            unit:int = 10**digits

            # Compute split prices
            n_parts = self.model.args.n_parts
            low, high = self._compute_price_bounds_int(
                center=int(order_price*unit),
                price_range=args.price_range,
                n_parts=n_parts,
                mode=para.mode,
            )
            # low, high = round(low*unit)/unit, round(high*unit)/unit

            # Generate legs
            ok = True
            min_lot = para.min_lot

            if n_parts == 1 or low == high:
                prices_int = [int(order_price*unit)]
                base_volumes_int = [int(total_volume/min_lot)]
            else:
                steps = self.split_integer(args.price_range, n_parts)
                if 0 in steps:
                    raise ValueError(f'price_range of {args.price_range} is too small to split into {n_parts} parts')
                prices_int = [low+i for i in steps]
                total_volume_int = int(total_volume/min_lot)
                base_volumes_int = self.split_integer(total_volume_int, n_parts)
                if 0 in base_volumes_int:
                    raise ValueError(f'total_volume of {total_volume} is too small to split into {n_parts} parts')

            # Send child orders
            for price, volume in zip(prices_int, base_volumes_int):
                try:
                    price, volume = price/unit, volume*min_lot
                    Book(
                        symbol=symbol,
                        volume=volume,
                        price_open=price,
                        tp=tp,
                        sl=sl,
                    ).as_plan().send()
                except Exception:
                    ok = False

            # Close the original order
            try:
                original.close()
            except Exception:
                self.model.rets.ok = False
                return self.model

            self.model.rets.ok = ok
            return self.model

#########################################
# {
#   "param": {
#         "account": {
#             "account_id": xxxxxx,
#             "password": "xxxxxx",
#             "account_server": "xxxxxxx"
#       }
#   },
  
#   "args": {
#         "symbol": "USDJPY",
#         "timeframe": "H4",
#         "count": 30,
#         "debug": false,
#         "retry_times_on_error": 3
#     }
# }
class MT5CopyLastRatesService(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):
        class Parameter(MT5Account):
            pass
        
        class Arguments(BaseModel):
            symbol: str = "USDJPY"
            timeframe: str = "H1"
            count: int = 10
            debug: bool = False
            retry_times_on_error: int = 3

        class Returness(BaseModel):
            symbol: str = "NULL"
            timeframe: str = "H1"
            count: int = 10
            rates: list = []
            digitsnum: int = 0
            error: str = ''
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

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass
        
        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Returness = Returness()
        logger:Logger = Logger(name=Version().class_name)
        
    class Action(ServiceOrientedArchitecture.Action, MT5Action):
        _start_pos = 0
        _digitsnum = {
            'AUDJPY': 3, 'CADJPY': 3, 'CHFJPY': 3, 'CNHJPY': 3, 'EURJPY': 3,
            'GBPJPY': 3, 'USDJPY': 3, 'NZDJPY': 3, 'XAUJPY': 0, 'JPN225': 1, 'US500': 1
        }

        def __init__(self, model,BasicApp:AppInterface,level=None):            
            super().__init__(model,BasicApp,level)
            self.model:MT5CopyLastRatesService.Model = self.model
            print(self.model)
            account = self.model.para
            self.uuid = uuid.uuid4()
            self._account: MT5Account = account
            self.retry_times_on_error = 3

        def _update_args(self, symbol: str = None, timeframe: str = None, count: int = None, debug: bool = None):
            # Update model args only if provided (fall back to existing ones otherwise)
            self.model.args.symbol = symbol if symbol is not None else self.model.args.symbol
            self.model.args.timeframe = timeframe if timeframe is not None else self.model.args.timeframe
            self.model.args.count = count if count is not None else self.model.args.count
            self.model.args.debug = debug if debug is not None else self.model.args.debug

        def __call__(self, *args, **kwargs):# symbol: str, timeframe: str, count: int, debug: bool = False):
            symbol = self.model.args.symbol
            timeframe = self.model.args.timeframe
            count = self.model.args.count
            debug = self.model.args.debug
            self._update_args(symbol, timeframe, count, debug)
            # Perform the MT5 action
            self.model: MT5CopyLastRatesService.Model = MT5Manager().get_singleton().do(self)
            self.model.rets.symbol = symbol
            self.model.rets.timeframe = timeframe
            self.model.rets.count = count
            self.model.para = MT5Account()
            return self.model

        def run(self, symbol: str = None, timeframe: str = None, count: int = None, debug: bool = None):
            self._update_args(symbol, timeframe, count, debug)

            if self.model.args.debug:
                # For debugging, return simple mock values
                self.model.rets.rates = None
                self.model.rets.digitsnum = 3  # Mock value for digits
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
            self.model.rets.rates = rates.tolist()
            self.model.rets.digitsnum = digitsnum
            self.model.rets.error = None

            return self.model


# Example usage:
# model_dict = {
#     "param": {"account": {...}, "retry_times_on_error": 3},
# }
# action = MT5CopyLastRatesService.Action(model=model_dict)
# result = action(symbol="USDJPY", timeframe="H4", count=10)
# print(result)
