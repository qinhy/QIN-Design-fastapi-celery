import os
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    from MockMetaTrader5 import MetaTrader5
    mt5 = MetaTrader5()

import numpy as np
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
except ImportError:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class MT5RatesDownloader(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            data_path: str = Field("./", description="Directory path where downloaded data files will be saved")
            
        class Args(BaseModel):
            pair: str = Field("EURUSD", description="Currency pair symbol (e.g. EURUSD, GBPJPY) to download rates for")
            time_frame: str = Field("H1", description="MT5 timeframe identifier (e.g. M1, H1, D1) representing the bar interval")
            bar_count: int = Field(1000, description="Number of historical bars to retrieve, starting from most recent")

        class Return(BaseModel):
            data_file: Optional[str] = Field(None, description="Path to downloaded data file")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{"args": {"pair": "EURJPY", "time_frame": "M1", "bar_count": 1000}}]

        version: Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = None
        logger: Logger = Logger(name=Version().class_name)
    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self._mt5_initialized = False

        def _initialize_mt5(self) -> bool:
            """Initialize MT5 connection if not already initialized"""
            if not self._mt5_initialized:
                if not mt5.initialize():
                    self.log_and_send("Failed to initialize MT5", MT5RatesDownloader.Levels.ERROR)
                    return False
                self._mt5_initialized = True
            return True

        def _get_mt5_timeframe(self, time_frame: str) -> Optional[int]:
            """Convert string timeframe to MT5 timeframe constant"""
            mt5_timeframe = getattr(mt5, f"TIMEFRAME_{time_frame.upper()}", None)
            if mt5_timeframe is None:
                self.log_and_send(f"Invalid timeframe: {time_frame}", MT5RatesDownloader.Levels.ERROR)
            return mt5_timeframe

        def _download_data(self, pair: str, time_frame: str, bar_count: int) -> Optional[np.ndarray]:
            """Download historical price data from MT5"""
            mt5_timeframe = self._get_mt5_timeframe(time_frame)
            if mt5_timeframe is None:
                return None
                
            rates = mt5.copy_rates_from_pos(pair, mt5_timeframe, 0, bar_count)
            if rates is None or len(rates) == 0:
                self.log_and_send(f"No data for {pair} {time_frame}", MT5RatesDownloader.Levels.WARNING)
            return rates

        def _save_data(self, rates: np.ndarray, pair: str, time_frame: str) -> str:
            """Save downloaded data to file and return filename"""
            data_path = self.model.param.data_path
            os.makedirs(data_path, exist_ok=True)
            filename = os.path.join(data_path, f'{pair}_{time_frame}.npy')
            np.save(filename, rates)
            return filename

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                try:
                    if not self._initialize_mt5():
                        self.model.ret = None
                        return self.model
                        
                    pair = self.model.args.pair
                    time_frame = self.model.args.time_frame
                    bar_count = self.model.args.bar_count

                    rates = self._download_data(pair, time_frame, bar_count)
                    if rates is not None and len(rates) > 0:
                        filename = self._save_data(rates, pair, time_frame)
                        self.model.ret = self.model.Return(data_file=filename)
                        self.log_and_send(f"Saved {filename} with {len(rates)} bars")
                    else:
                        self.model.ret = None
                finally:
                    if self._mt5_initialized:
                        # mt5.shutdown()
                        self._mt5_initialized = False

            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, aborting download.", MT5RatesDownloader.Levels.WARNING)
            self.model.ret = None
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


# Tests for MT5RatesDownloader
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

class TestMT5RatesDownloader(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test data
        self.test_dir = tempfile.mkdtemp()
        
        # Create a mock BasicApp
        self.mock_basic_app = MagicMock()
        
        # Create model instance with test parameters
        self.model = MT5RatesDownloader.Model()
        self.model.param.data_path = self.test_dir
        
        # Create action instance
        self.action = MT5RatesDownloader.Action(self.model, self.mock_basic_app)
    
    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_initialize_mt5_success(self):
        # Test successful MT5 initialization
        result = self.action._initialize_mt5()
        self.assertTrue(result)
        self.assertTrue(self.action._mt5_initialized)
    
    def test_get_mt5_timeframe_valid(self):
        # Test valid timeframe conversion
        result = self.action._get_mt5_timeframe("M1")
        self.assertEqual(result, mt5.TIMEFRAME_M1)
        
        result = self.action._get_mt5_timeframe("H1")
        self.assertEqual(result, mt5.TIMEFRAME_H1)
    
    def test_get_mt5_timeframe_invalid(self):
        # Test invalid timeframe conversion
        result = self.action._get_mt5_timeframe("INVALID")
        self.assertIsNone(result)
    
    def test_download_data_success(self):
        # Test successful data download
        rates = self.action._download_data("EURUSD", "M1", 100)
        self.assertIsNotNone(rates)
        self.assertEqual(len(rates), 100)
    
    def test_download_data_invalid_symbol(self):
        # Test download with invalid symbol
        rates = self.action._download_data("INVALID", "M1", 100)
        self.assertIsNone(rates)
    
    def test_download_data_invalid_timeframe(self):
        # Test download with invalid timeframe
        rates = self.action._download_data("EURUSD", "INVALID", 100)
        self.assertIsNone(rates)
    
    def test_save_data(self):
        # Test saving data to file
        # Create sample data
        dtype = [('time', '<i8'), ('open', '<f8'), ('high', '<f8'), 
                ('low', '<f8'), ('close', '<f8'), ('tick_volume', '<u8'), 
                ('spread', '<i4'), ('real_volume', '<u8')]
        sample_data = np.array([(1600000000, 1.1, 1.2, 1.0, 1.15, 100, 2, 100)], dtype=dtype)
        
        filename = self.action._save_data(sample_data, "EURUSD", "M1")
        
        # Check if file exists and contains correct data
        self.assertTrue(os.path.exists(filename))
        loaded_data = np.load(filename)
        self.assertEqual(len(loaded_data), 1)
    
    def test_full_download_success(self):
        # Test full download process
        self.model.args.pair = "EURUSD"
        self.model.args.time_frame = "M1"
        self.model.args.bar_count = 100
        
        result = self.action()
        
        self.assertIsNotNone(result.ret)
        self.assertIsNotNone(result.ret.data_file)
        self.assertTrue(os.path.exists(result.ret.data_file))
    
    def test_full_download_invalid_symbol(self):
        # Test full download with invalid symbol
        self.model.args.pair = "INVALID"
        self.model.args.time_frame = "M1"
        self.model.args.bar_count = 100
        
        result = self.action()
        
        self.assertIsNone(result.ret)
    
    def test_full_download_invalid_timeframe(self):
        # Test full download with invalid timeframe
        self.model.args.pair = "EURUSD"
        self.model.args.time_frame = "INVALID"
        self.model.args.bar_count = 100
        
        result = self.action()
        
        self.assertIsNone(result.ret)
    
    def test_full_download_mt5_init_failure(self):
        # Test full download with MT5 initialization failure
        with patch.object(mt5, 'initialize', return_value=False):
            self.action._mt5_initialized = False
            self.model.args.pair = "EURUSD"
            self.model.args.time_frame = "M1"
            self.model.args.bar_count = 100
            
            result = self.action()
            
            self.assertIsNone(result.ret)

if __name__ == "__main__":
    unittest.main()
