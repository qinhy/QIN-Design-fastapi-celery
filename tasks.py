from typing import Dict
from basic import get_tasks_collection, set_task_revoked, check_services
from customs import CvCameraSharedMemoryService, Fibonacci, ServiceOrientedArchitecture

######################################### Celery connect to local rabbitmq and mongo backend
import os
os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')
from fastapi import FastAPI, HTTPException
from celery import Celery
from celery.app import task as Task

rabbitmq_URL = 'localhost:15672'
mongo_URL = 'mongodb://localhost:27017'
mongo_DB = 'tasks'
celery_broker = 'amqp://localhost'
celery_app = Celery('tasks', broker = celery_broker, backend = f'{mongo_URL}/{mongo_DB}')

def api_ok():
    if not check_services(rabbitmq_URL,mongo_URL):
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
    
    @staticmethod
    @api.get("/tasks/status/{task_id}")
    def api_task_status(task_id: str):
        api_ok()
        """Endpoint to check the status of a task."""
        collection = get_tasks_collection()
        res = collection.find_one({'_id': task_id})
        if res: del res['_id']
        return res
    
    @api.get("/tasks/stop/{task_id}")
    def api_task_stop(task_id: str):        
        api_ok()
        return set_task_revoked(task_id)
        
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