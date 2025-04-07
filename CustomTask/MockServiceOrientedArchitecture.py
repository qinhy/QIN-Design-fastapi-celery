import io
import logging
import threading
from typing import Optional, Any
from pydantic import BaseModel, Field, PrivateAttr
from contextlib import contextmanager
import celery.states

class ServiceOrientedArchitecture:
    BasicApp:Any = None

    class Model(BaseModel):
        task_id:Optional[str] = Field('AUTO_SET_BUT_NULL_NOW', description="task uuid")

        class Version(BaseModel):
            class_name: str = Field(default='NULL', description="class name")
            major: str = Field(default="1", description="Major version number")
            minor: str = Field(default="0", description="Minor version number")
            patch: str = Field(default="0", description="Patch version number")

            @classmethod
            def get_class_name(cls):
                return cls.__qualname__.split('.')[0]

            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                if self.class_name == 'NULL':
                    self.class_name = self.get_class_name()

            def __repr__(self):
                return self.__str__()
            def __str__(self):
                return f'_v{self.major}{self.minor}{self.patch}_'

        class Param(BaseModel):
            pass
        class Args(BaseModel):
            pass
        class Return(BaseModel):
            pass

        class Logger(BaseModel):
            class Levels:
                ERROR:str='ERROR'
                WARNING:str='WARNING'
                INFO:str='INFO'
                DEBUG:str='DEBUG'
                
            name: str  = "service" # Logger name
            level: str = "INFO"  # Default log level
            logs:str = ''

            _log_buffer: io.StringIO = PrivateAttr()
            _logger: logging.Logger = PrivateAttr()

            def init(self,name:str=None,
                     action_obj:'ServiceOrientedArchitecture.Action'=None):
                if name is None:
                    name = self.name
                # Create a StringIO buffer for in-memory logging
                self._log_buffer = io.StringIO()

                # Configure logging
                self._logger = logging.getLogger(name)
                self._logger.setLevel(
                    getattr(logging, self.level.upper(), logging.INFO))

                # Formatter for log messages
                formatter = logging.Formatter(
                    '%(asctime)s [%(name)s:%(levelname)s] %(message)s')

                # In-Memory Handler
                memory_handler = logging.StreamHandler(self._log_buffer)
                memory_handler.setFormatter(formatter)
                self._logger.addHandler(memory_handler)

                # Console Handler (Optional, remove if not needed)
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                self._logger.addHandler(console_handler)
                return self

            def log(self, level: str, message: str):
                """Logs a message at the specified level."""
                log_method = getattr(self._logger, level.lower(), None)
                if callable(log_method):
                    log_method(message)
                    self.save_logs()
                else:
                    self._logger.error(f"Invalid log level: {level}")

            def info(self, message: str):
                self.log("INFO", message)

            def warning(self, message: str):
                self.log("WARNING", message)

            def error(self, message: str):
                self.log("ERROR", message)

            def debug(self, message: str):
                self.log("DEBUG", message)

            def get_logs(self) -> str:
                """Returns all logged messages stored in memory."""
                return self._log_buffer.getvalue()

            def save_logs(self) -> str:
                """Saves logs to the `logs` attribute."""
                self.logs = self.get_logs()
                return self.logs

            def clear_logs(self):
                """Clears the in-memory log buffer and resets the logger state."""
                self._log_buffer.truncate(0)
                self._log_buffer.seek(0)
                self.logs = ""
                
                # Remove handlers to prevent duplicate logs
                for handler in self._logger.handlers[:]:
                    self._logger.removeHandler(handler)

                
        version:Version = Version()
        param:Param = Param()
        args:Args = Args()
        ret:Optional[Return] = Return()
        logger: Logger = Logger()

        @classmethod
        def examples(cls): return []

    class Action:
        def __init__(self, model, BasicApp:Any=None, level=None):
            outer_class_name:ServiceOrientedArchitecture = self.__class__.__qualname__.split('.')[0]
            if isinstance(model, dict):
                nones = [k for k,v in model.items() if v is None]
                for i in nones:del model[i]
                model = outer_class_name.Model(**model)
            self.model = model
            self.logger = self.model.logger
            if level is None:level=ServiceOrientedArchitecture.Model.Logger.Levels.INFO
            self.logger.level = level
            self.logger.init(
                name=f"{model.version.class_name}:{self.model.task_id}",action_obj=self)
            self.listen_data_of_task_uuids = []

        def send_data_to_task(self, msg_dict={}):
            pass

        def listen_data_of_task(self, msg_lambda=lambda msg={}:None, eternal=False):
            return "mock-id"

        def set_task_status(self, status):
            pass

        def get_task_status(self):
            return "UNKNOWN"

        def stop_service(self):
            pass

        def dispose(self):
            pass
            
        def __del__(self):
            self.dispose()

        @contextmanager
        def listen_stop_flag(self):            
            # A shared flag to communicate between threads
            stop_flag = threading.Event()

            status = self.get_task_status()
            if status == celery.states.REVOKED:
                stop_flag.set()
                yield stop_flag
            else:
                self.set_task_status(celery.states.STARTED)
                # Function to check if the task should be stopped, running in a separate thread
                def check_task_status(data:dict):
                    if data.get('status',None) == celery.states.REVOKED:
                        self.set_task_status(celery.states.REVOKED)
                        stop_flag.set()
                self.listen_data_of_task(check_task_status,True)
                
                try:
                    yield stop_flag  # Provide the stop_flag to the `with` block
                finally:
                    self.send_data_to_task({})
            return stop_flag

        def __call__(self, *args, **kwargs):
            return self.model
        

if __name__ == '__main__':
    print(ServiceOrientedArchitecture.Model().version.class_name)

