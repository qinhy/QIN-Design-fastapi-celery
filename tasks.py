from typing import Dict

from pydantic import BaseModel
from customs import Fibonacci,FibonacciAction

######################################### Celery connect to local rabbitmq and mongo backend
import os
os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')
from fastapi import Body, FastAPI
from pymongo import MongoClient
from celery import Celery
from celery.app import task as Task
mongo_URL = 'mongodb://localhost:27017'
mongo_DB = 'tasks'
celery_META = 'celery_taskmeta'
celery_broker = 'amqp://localhost'

celery_app = Celery('tasks', broker = celery_broker, backend = f'{mongo_URL}/{mongo_DB}')

class CeleryTask:

    @staticmethod
    @celery_app.task(bind=True)
    def revoke(t:Task, task_id: str):
        """Method to revoke a task."""
        return celery_app.control.revoke(task_id, terminate=True)

    @staticmethod
    @celery_app.task(bind=True)
    def fibonacci(t:Task, n: Fibonacci) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        return FibonacciAction(n)()
    
    @celery_app.task(bind=True)
    def perform_action(self: Task, action_name: str, action_data: dict) -> int:
        """Generic Celery task to execute any registered action."""
        ACTION_REGISTRY = {'FibonacciAction':(FibonacciAction,Fibonacci)}
        if action_name not in ACTION_REGISTRY:
            raise ValueError(f"Action '{action_name}' is not registered.")

        # Initialize the action model and action handler
        action_class,action_model = ACTION_REGISTRY[action_name]
        action_instance = action_class(action_model(**action_data))
        return action_instance()
    
######################################### Create FastAPI app instance
class PerformAction(BaseModel):
    name:str
    data:dict

class RESTapi:
    api = FastAPI()
    
    @api.get("/tasks/stop/{task_id}")
    def task_stop(task_id:str):
        task = CeleryTask.revoke.delay(task_id=task_id)
        return {'id':task.id}    

    @api.post("/fibonacci/")
    def fibonacci(fib_task: Fibonacci):
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""        
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}


    @api.post("/perform_action/")
    def perform_action(action: PerformAction=PerformAction(name='FibonacciAction', data=dict(n=10))):
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""        
        task = CeleryTask.perform_action.delay(action.name,action.data)
        return {'task_id': task.id}

    @staticmethod
    @api.get("/tasks/status/{task_id}")
    def task_status(task_id: str):
        """Endpoint to check the status of a task."""
        client = MongoClient(mongo_URL)
        db = client.get_database(f'{mongo_DB}')
        collection = db.get_collection(f'{celery_META}')
        res = collection.find_one({'_id': task_id})
        if res: del res['_id']
        return res