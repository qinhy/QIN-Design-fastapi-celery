import os
import sys
sys.path.append("..")
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
        
    os.environ['APP_BACK_END'] = str(APP_BACK_END)
    os.environ['APP_INVITE_CODE'] = str(APP_INVITE_CODE)
    os.environ['APP_SECRET_KEY'] = str(APP_SECRET_KEY)
    os.environ['ALGORITHM'] = str(ALGORITHM)
    os.environ['ACCESS_TOKEN_EXPIRE_MINUTES'] = str(ACCESS_TOKEN_EXPIRE_MINUTES)
    os.environ['SESSION_DURATION'] = str(SESSION_DURATION)
    os.environ['UVICORN_PORT'] = str(UVICORN_PORT)
    os.environ['FLOWER_PORT'] = str(FLOWER_PORT)
    os.environ['RABBITMQ_URL'] = str(RABBITMQ_URL)
    os.environ['RABBITMQ_USER'] = str(RABBITMQ_USER)
    os.environ['RABBITMQ_PASSWORD'] = str(RABBITMQ_PASSWORD)
    os.environ['MONGO_URL'] = str(MONGO_URL)
    os.environ['MONGO_DB'] = str(MONGO_DB)
    os.environ['CELERY_META'] = str(CELERY_META)
    os.environ['CELERY_RABBITMQ_BROKER'] = str(CELERY_RABBITMQ_BROKER)
    os.environ['REDIS_URL'] = str(REDIS_URL)
    os.environ['EX_IP'] = str(EX_IP)

    return (APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,
            ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,
            FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,
            MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP)
APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP = config()
from celery.app import task as Task
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi import Depends, FastAPI, HTTPException

from Task.Customs import Fibonacci, ServiceOrientedArchitecture
from Task.Basic import AppInterface,RedisApp,RabbitmqMongoApp
from Vision import Service as VisonService

from User.UserAPIs import AuthService, UserModels, router as users_router

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
    if not BasicApp.check_services():
        raise HTTPException(status_code=503, detail={
                            'error': 'service not healthy'})

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
    
    api.include_router(users_router, prefix="", tags=["users"])

    @staticmethod
    @api.get("/", response_class=HTMLResponse)
    async def get_register_page():
        return FileResponse(os.path.join(os.path.dirname(__file__), "gui.html"))
    ########################### essential function
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
        ACTION_REGISTRY: dict[str, ServiceOrientedArchitecture] = {
            'CvCameraSharedMemoryService': VisonService.CvCameraSharedMemoryService,
        }
        if action_name not in ACTION_REGISTRY:
            raise ValueError(f"Action '{action_name}' is not registered.")

        # Initialize the action model and action handler
        class_space = ACTION_REGISTRY[action_name]
        model_instance = class_space.Model(**action_data)
        model_instance.task_id = t.request.id
        action_instance = class_space.Action(model_instance)
        res = action_instance().model_dump()
        return CeleryTask.is_json_serializable(res)

    @api.post("/action/perform")
    def api_perform_action(action: dict = dict(
            name='CvCameraSharedMemoryService', data=dict())):
        api_ok()
        task = CeleryTask.perform_action.delay(action['name'], action['data'])
        return {'task_id': task.id}

    ############################# general function specific api

    @api.get("/streams/write")
    # 3840, 2160  480,640
    def api_actions_camera_write(stream_key: str = 'camera:0', h: int = 600, w: int = 800):
        api_ok()
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    @api.get("/streams/read")
    def api_actions_camera_read(stream_key: str = 'camera:0'):
        api_ok()
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='read', stream_key=stream_key, array_shape=info['array_shape']))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    ########################### basic function with auth
    @staticmethod
    @celery_app.task(bind=True,)
    def fibonacci(t: Task, fib_task_model_dump: dict,) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        fib_task_model_dump['task_id'] = t.request.id
        model = Fibonacci.Model(**fib_task_model_dump)
        model = Fibonacci.Action(model)()
        res: Fibonacci.Model.Return = model.ret
        # make sure that res is dict or other primitive objects for json serialization
        return CeleryTask.is_json_serializable(res.model_dump())

    @api.post("/auth/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model,
                      current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}
    
    
    @api.post("/auth/local/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model,
                      current_payload: UserModels.User = Depends(AuthService.get_current_payload_if_not_local)):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}