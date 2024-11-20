from User.UserAPIs import AuthService, UserModels, router as users_router
from celery.app import task as Task
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException
import secrets
from typing import Dict
from Task.Basic import BasicApp
from Task.Customs import CvCameraSharedMemoryService, Fibonacci, ServiceOrientedArchitecture

# Celery connect to local rabbitmq and mongo backend
import os
os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')


celery_app = BasicApp.get_celery_app()


def api_ok():
    if not BasicApp.check_services():
        raise HTTPException(status_code=503, detail={
                            'error': 'service not healthy'})


class CeleryTask:

    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    SECRET_KEY = secrets.token_urlsafe(32)
    SESSION_DURATION = ACCESS_TOKEN_EXPIRE_MINUTES * 60

    api = FastAPI()

    api.add_middleware(
        CORSMiddleware,
        allow_origins=['*',],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.add_middleware(SessionMiddleware,
                       secret_key=SECRET_KEY, max_age=SESSION_DURATION)

    api.include_router(users_router, prefix="", tags=["users"])

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

    @api.get("/tasks/status/{task_id}")
    def api_task_status(task_id: str):
        api_ok()
        return BasicApp.get_task_status()

    @api.get("/tasks/stop/{task_id}")
    def api_task_stop(task_id: str):
        api_ok()
        return BasicApp.set_task_revoked(task_id)

    @api.get("/workers/")
    def get_workers():
        api_ok()
        """Retrieve the status of all Celery workers."""
        inspector = celery_app.control.inspect()
        active_workers = inspector.active() or {}
        stats = inspector.stats() or {}

        workers = []
        for worker_name, data in stats.items():
            workers.append({
                "worker_name": worker_name,
                "status": "online" if worker_name in active_workers else "offline",
                "active_tasks": len(active_workers.get(worker_name, [])),
                "total_tasks": data.get('total', 0)
            })
        return workers

    ########################### basic function
    @staticmethod
    @celery_app.task(bind=True)
    def fibonacci(t: Task, fib_task_model_dump: dict) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        fib_task_model_dump['task_id'] = t.request.id
        model = Fibonacci.Model(**fib_task_model_dump)
        model = Fibonacci.Action(model)()
        res: Fibonacci.Model.Return = model.ret
        # make sure that res is dict or other primitive objects for json serialization
        return CeleryTask.is_json_serializable(res.model_dump())

    @api.post("/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}
    
    ############################# general function
    @celery_app.task(bind=True)
    def perform_action(t: Task, name: str, data: dict) -> int:
        """Generic Celery task to execute any registered action."""
        action_name, action_data = name, data
        ACTION_REGISTRY: Dict[str, ServiceOrientedArchitecture] = {
            'Fibonacci': Fibonacci,
            'CvCameraSharedMemoryService': CvCameraSharedMemoryService,
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
            name='Fibonacci', data=dict(args=dict(n=10)))):
        api_ok()
        task = CeleryTask.perform_action.delay(action['name'], action['data'])
        return {'task_id': task.id}

    ############################# general function specific api

    @api.post("/actions/fibonacci")
    def api_actions_fibonacci(data: Fibonacci.Model):
        api_ok()
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""
        act = dict(name='Fibonacci', data=data.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    @api.get("/streams/write")
    # 3840, 2160  480,640
    def api_actions_camera_write(stream_key: str = 'camera:0', h: int = 2160*2*2, w: int = 3840*2*2):
        api_ok()
        info = BasicApp.store.get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    @api.get("/streams/read")
    def api_actions_camera_read(stream_key: str = 'camera:0'):
        api_ok()
        info = BasicApp.store.get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = CvCameraSharedMemoryService.Model
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
                      current_user: UserModels.User = Depends(AuthService.get_current_user)):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}