from typing import Dict
from basic import BasicApp
from customs import CvCameraSharedMemoryService, Fibonacci, ServiceOrientedArchitecture

######################################### Celery connect to local rabbitmq and mongo backend
import os
os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')
from fastapi import FastAPI, HTTPException
from celery.app import task as Task

celery_app = BasicApp.get_celery_app()
def api_ok():
    if not BasicApp.check_services():
        raise HTTPException(status_code=503, detail={'error':'service not healthy'})
        
class CeleryTask:
    api = FastAPI()

    ########################### essential function
    @staticmethod
    def is_json_serializable(value) -> bool:
        res = isinstance(value, (int, float, bool, str,
                                  list, dict, set, tuple)) or value is None
        if not res : raise ValueError("Result is not JSON serializable")
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
    def fibonacci(t:Task, fib_task_model_dump: dict) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        fib_task_model_dump['task_id']=t.request.id
        model = Fibonacci.Model(**fib_task_model_dump)
        model = Fibonacci.Action(model)()
        res:Fibonacci.Model.Return = model.ret
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
        action_name,action_data = name,data
        ACTION_REGISTRY:Dict[str,ServiceOrientedArchitecture] = {
            'Fibonacci':Fibonacci,
            'CvCameraSharedMemoryService':CvCameraSharedMemoryService,
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
    def api_perform_action(action: dict=dict(
                                    name='Fibonacci', data=dict(args=dict(n=10)))):
        api_ok()
        task = CeleryTask.perform_action.delay(action['name'],action['data'])
        return {'task_id': task.id}

    ############################# general function specific api

    @api.post("/actions/fibonacci")
    def api_actions_fibonacci(data: Fibonacci.Model):
        api_ok()
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""  
        act = dict(name='Fibonacci', data=data.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    CCModel = CvCameraSharedMemoryService.Model

    @api.post("/actions/camera/write")
    def api_actions_camera_write(data:dict=dict(param=dict(
                                    shm_name="camera_0", array_shape=(480, 640)),
                                args=dict(camera=0))):
        api_ok()
        data['param']['create']=True
        data['param']['mode']='write'
        act = dict(name='CvCameraSharedMemoryService', data=data)
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}
    
    @api.post("/actions/camera/read")
    def api_actions_camera_read(data:dict=dict(param=dict(
                                    shm_name="camera_0", array_shape=(480, 640)),
                                args=dict(camera=0))):
        api_ok()
        data['param']['create']=False
        data['param']['mode']='read'
        act = dict(name='CvCameraSharedMemoryService', data=data)
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}