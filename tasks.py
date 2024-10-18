from typing import Dict

import cv2
from pydantic import BaseModel
from customs import CvCameraSharedMemoryService, Fibonacci, ServiceOrientedArchitecture

######################################### Celery connect to local rabbitmq and mongo backend
import os
os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')
from fastapi import FastAPI
from pymongo import MongoClient
from celery import Celery
from celery.app import task as Task
mongo_URL = 'mongodb://localhost:27017'
mongo_DB = 'tasks'
celery_META = 'celery_taskmeta'
celery_broker = 'amqp://localhost'

celery_app = Celery('tasks', broker = celery_broker, backend = f'{mongo_URL}/{mongo_DB}')
    
class CeleryTask:
    api = FastAPI()

    @staticmethod
    def is_json_serializable(value) -> bool:
        res = isinstance(value, (int, float, bool, str,
                                  list, dict, set, tuple)) or value is None
        if not res : raise ValueError("Result is not JSON serializable")
        return value
    
    @staticmethod
    @celery_app.task(bind=True)
    def revoke(t:Task, task_id: str):
        return celery_app.control.revoke(task_id, terminate=True)

    @api.get("/tasks/stop/{task_id}")
    def api_task_stop(task_id:str):
        task = CeleryTask.revoke.delay(task_id=task_id)
        return {'id': task.id}
        
    ########################### basic function
    @staticmethod
    @celery_app.task(bind=True)
    def fibonacci(t:Task, fib_task_model_dump: dict) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        res:int = Fibonacci.Model(Fibonacci.Action(**fib_task_model_dump))()
        # make sure that res is dict or other primitive objects for json serialization
        return CeleryTask.is_json_serializable(res)
    
    @api.post("/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model):
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
        action_instance = class_space.Action(class_space.Model(**action_data))
        res = action_instance().model_dump()      
        return CeleryTask.is_json_serializable(res)

    @api.post("/action/perform")
    def api_perform_action(action: dict=dict(
                                    name='Fibonacci', data=dict(args=dict(n=10)))):
        task = CeleryTask.perform_action.delay(action['name'],action['data'])
        return {'task_id': task.id}

    @staticmethod
    @api.get("/tasks/status/{task_id}")
    def api_task_status(task_id: str):
        """Endpoint to check the status of a task."""
        client = MongoClient(mongo_URL)
        db = client.get_database(f'{mongo_DB}')
        collection = db.get_collection(f'{celery_META}')
        res = collection.find_one({'_id': task_id})
        if res: del res['_id']
        return res    

    ############################# general function specific api

    @api.post("/actions/fibonacci")
    def api_actions_fibonacci(data: Fibonacci.Model):
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""  
        act = dict(name='Fibonacci', data=data.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    CCModel = CvCameraSharedMemoryService.Model

    @api.post("/actions/camera/write")
    def api_actions_camera_write(data:dict=dict(param=dict(
                                    shm_name="camera_0", array_shape=(480, 640)),
                                args=dict(camera=0))):
        data['param']['create']=True
        data['param']['mode']='write'
        act = dict(name='CvCameraSharedMemoryService', data=data)
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}
    
    @api.post("/actions/camera/read")
    def api_actions_camera_read(data:dict=dict(param=dict(
                                    shm_name="camera_0", array_shape=(480, 640)),
                                args=dict(camera=0))):
        data['param']['create']=False
        data['param']['mode']='read'
        act = dict(name='CvCameraSharedMemoryService', data=data)
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}