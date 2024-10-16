from typing import Dict

from pydantic import BaseModel
from customs import Fibonacci,FibonacciAction, ServiceOrientedArchitecture

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

class PerformAction(BaseModel):
    name:str
    data:dict
    
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
        res:int = FibonacciAction(Fibonacci.Action(**fib_task_model_dump))()
        # make sure that res is dict or other primitive objects for json serialization
        return CeleryTask.is_json_serializable(res)
    
    @api.post("/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model):
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}
    
    ##########################################
    @celery_app.task(bind=True)
    def perform_action(self: Task, action_name: str, action_data: dict) -> int:
        """Generic Celery task to execute any registered action."""

        ACTION_REGISTRY:Dict[str,ServiceOrientedArchitecture] = {'Fibonacci':Fibonacci}
        if action_name not in ACTION_REGISTRY:
            raise ValueError(f"Action '{action_name}' is not registered.")

        # Initialize the action model and action handler
        class_space = ACTION_REGISTRY[action_name]
        action_instance = class_space.Action(class_space.Model(**action_data))
        res = action_instance().model_dump()      
        return CeleryTask.is_json_serializable(res)

    @api.post("/perform_action/")
    def api_perform_action(action: PerformAction=PerformAction(
                                    name='Fibonacci', data=dict(n=10))):
        task = CeleryTask.perform_action.delay(action.name,action.data)
        return {'task_id': task.id}

    @api.post("/actions/fibonacci")
    def api_actions_fibonacci(data: Fibonacci):
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""  
        task = CeleryTask.perform_action.delay(PerformAction(
                                        name='Fibonacci', data=data.model_dump()))
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
