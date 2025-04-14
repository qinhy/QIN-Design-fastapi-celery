class MetaTrader5:
    # Timeframe constants
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440
    TIMEFRAME_W1 = 10080
    TIMEFRAME_MN1 = 43200

    def __init__(self):
        print("[warning]: MockMT5 initialized")

    @staticmethod
    def initialize():
        return True

    @staticmethod
    def shutdown():
        return True

    @staticmethod
    def copy_rates_from_pos(symbol, timeframe, start_pos, count):
        """
        Simulates fetching rate data for a symbol.
        Returns a list of dictionaries containing the rate information.
        """
        if symbol == "INVALID":
            return None

        rates = []
        for i in range(count):
            time_val = 1600000000 + i * 60  # Increment timestamps by 60 seconds
            open_val = 1.1000 + (i * 0.0001)
            rate = {
                "time": time_val,
                "open": open_val,
                "high": open_val + 0.0010,
                "low": open_val - 0.0010,
                "close": open_val + 0.0005,
                "tick_volume": 100,
                "spread": 2,
                "real_volume": 100
            }
            rates.append(rate)
        return rates

    @staticmethod
    def symbol_info(symbol):
        """
        Returns simulated information about a symbol.
        Returns None if the symbol is invalid.
        """
        if symbol == "INVALID":
            return None
        info = {
            "name": symbol,
            "bid": 1.1000,
            "ask": 1.1002,
            "spread": 2,
            "last": 1.1001
        }
        return info

    @staticmethod
    def symbol_select(symbol, select=True):
        """
        Simulates selecting a symbol.
        Returns False if the symbol is invalid.
        """
        if symbol == "INVALID":
            return False
        return True

    @staticmethod
    def order_send(request):
        """
        Simulates sending an order.
        Expects 'request' to be a dictionary with at least a 'symbol' key.
        If the symbol is invalid, returns an error code.
        """
        if request.get("symbol") == "INVALID":
            return {"retcode": 1, "comment": "Invalid symbol"}
        # For simulation, assign a constant order id.
        order_id = 1001
        return {"order": order_id, "retcode": 0, "comment": "Order placed successfully"}

    @staticmethod
    def order_close(order_id, price, volume):
        """
        Simulates closing an order based on order_id.
        Returns an error if the provided order_id doesn't match the simulated one.
        """
        if order_id != 1001:
            return {"retcode": 2, "comment": "Order not found"}
        return {"order": order_id, "retcode": 0, "comment": "Order closed successfully"}

    @staticmethod
    def orders_total():
        """
        Returns a simulated total number of orders.
        """
        return 1

    @staticmethod
    def orders_get():
        """
        Returns a simulated list of active orders.
        """
        order = {"order": 1001, "symbol": "EURUSD", "volume": 1.0, "price": 1.1000}
        return [order]

    @staticmethod
    def positions_get():
        """
        Returns a simulated list of open positions (empty for now).
        """
        return []

    @staticmethod
    def account_info():
        """
        Returns simulated account information.
        """
        return {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin": 0.0,
            "free_margin": 10000.0,
            "leverage": 100
        }

    @staticmethod
    def terminal_info():
        """
        Returns simulated terminal information.
        """
        return {
            "name": "Mock Terminal",
            "version": "1.0",
            "build": 1001
        }

    @staticmethod
    def copy_ticks_from(symbol, start_time, count, flags):
        """
        Simulates fetching tick data for a symbol from a given start time.
        Returns a list of dictionaries containing tick information.
        """
        if symbol == "INVALID":
            return None

        ticks = []
        for i in range(count):
            bid = 1.1000 + i * 0.0001
            ask = bid + 0.0002
            tick = {
                "time": start_time + i,  # Increment time for each tick
                "bid": bid,
                "ask": ask,
                "last": (bid + ask) / 2
            }
            ticks.append(tick)
        return ticks