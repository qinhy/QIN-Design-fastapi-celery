import datetime
import sys
from typing import Literal, Optional

import pytz
sys.path.append("..")

from celery.app import task as Task
from celery.signals import task_received
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import FastAPI, HTTPException, Query
    
from Task.Customs import ServiceOrientedArchitecture
from Task.Basic import AppInterface,RedisApp,RabbitmqMongoApp

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

         
celery_app = BasicApp.get_celery_app()

@task_received.connect
def on_task_received(*args, **kwags):
    request =  kwags.get('request')
    if request is None:return
    message =  request.__dict__['_message'].__dict__
    BasicApp.set_task_status(message['_raw']['headers']['id'],
                             message['_raw']['headers']['argsrepr'],'RECEIVED')
    
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

def api_ok():
    if not BasicApp.check_services():
        raise HTTPException(status_code=503, detail={
                            'error': 'service not healthy'})

class BasicCeleryTask:
    ACTION_REGISTRY: dict[str, ServiceOrientedArchitecture] = {}
    
    @staticmethod
    @api.get("/", response_class=HTMLResponse)
    async def get_doc_page():
        return RedirectResponse("/docs")
    ########################### essential function
    @staticmethod
    def convert_to_utc(execution_time: str, timezone: str):
        """
        Converts a given local datetime string to UTC.

        Args:
            execution_time (str): The datetime string in 'YYYY-MM-DDTHH:MM:SS' format.
            timezone (str): The timezone name (e.g., 'Asia/Tokyo').

        Returns:
            datetime.datetime: The UTC datetime for Celery.

        Raises:
            HTTPException: If the timezone is invalid, the datetime format is incorrect,
                        or if the execution time is in the past.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # Validate timezone
        if timezone not in pytz.all_timezones:
            raise HTTPException(status_code=400, detail="Invalid timezone. Use a valid timezone name.")

        # Parse the input datetime
        try:
            local_dt = datetime.datetime.strptime(execution_time, "%Y-%m-%dT%H:%M:%S")
            local_tz = pytz.timezone(timezone)
            local_dt = local_tz.localize(local_dt)  # Convert to timezone-aware datetime
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS")

        # Convert to UTC for Celery
        execution_time_utc = local_dt.astimezone(pytz.utc)

        # Ensure execution time is in the future
        if execution_time_utc <= now_utc:
            raise HTTPException(status_code=400, detail="Execution time must be in the future.")

        return local_dt,execution_time_utc
    
    @staticmethod
    def is_json_serializable(value) -> bool:
        res = isinstance(value, (int, float, bool, str,
                                 list, dict, set, tuple)) or value is None
        if not res:
            raise ValueError("Result is not JSON serializable")
        return value

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
        # return BasicApp.set_task_revoked(task_id)

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

    ############################# general function    
    @celery_app.task(bind=True)
    def perform_action(t: Task, name: str, data: dict) -> int:
        """Generic Celery task to execute any registered action."""
        action_name, action_data = name, data
        if action_name not in BasicCeleryTask.ACTION_REGISTRY:
            raise ValueError(f"Action '{action_name}' is not registered.")

        # Initialize the action model and action handler
        class_space = BasicCeleryTask.ACTION_REGISTRY[action_name]
        model_instance = class_space.Model(**action_data)
        model_instance.task_id=t.request.id
        model_instance = class_space.Action(model_instance)()
        return BasicCeleryTask.is_json_serializable(model_instance.model_dump())


    @api.get("/action/list")
    def api_perform_action_list():
        """Returns a list of all available actions that can be performed."""
        api_ok()
        available_actions = []
        for k,v in BasicCeleryTask.ACTION_REGISTRY.items():
            model_schema = {}
            for kk,vv in zip(['param','args','ret'],[v.Model.Param,v.Model.Args,v.Model.Return]):
                schema = vv.model_json_schema()
                model_schema.update({
                    kk: {
                        key: {
                            "type": value["type"],
                            "description": value.get("description", "")
                        }
                        for key, value in schema["properties"].items() if 'type' in value
                    },
                    f"{kk}_required": schema.get("required", [])
                })
            available_actions.append({k:model_schema})
        return {"available_actions": available_actions}

    @api.post("/action/{name}")
    def api_perform_action(
        name: str, 
        data: dict,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        """API endpoint to execute a generic action asynchronously with optional delay."""
        api_ok()

        # Validate that the requested action exists
        if name not in BasicCeleryTask.ACTION_REGISTRY:
            return {"error": f"Action '{name}' is not available."}

        # Calculate execution time (eta)
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

        # Schedule the task
        task = BasicCeleryTask.perform_action.apply_async(args=[name, data], eta=execution_time)
        res = {'task_id': task.id}
        if execution_time: res['scheduled_for'] = execution_time
        return res
    
    @api.post("/action/{name}/schedule/")
    def api_schedule_perform_action(
        name: str, 
        data: dict,
        execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
          ).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
        timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
                        description="Choose a timezone from the list")
    ):
        """API to execute Fibonacci task at a specific date and time, with timezone support."""
        # Convert to UTC for Celery
        local_dt,execution_time_utc = BasicCeleryTask.convert_to_utc(execution_time,timezone)
        
        # Schedule the task
        task = BasicCeleryTask.perform_action.apply_async(args=[name, data], eta=execution_time_utc)

        return {
            "task_id": task.id,
            f"scheduled_for_{timezone}": local_dt.isoformat(),
            "scheduled_for_utc": execution_time_utc.isoformat(),
            "timezone": timezone
        }












    