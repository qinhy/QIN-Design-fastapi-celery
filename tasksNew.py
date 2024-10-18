from fastapi import FastAPI
from celery import Celery
import inspect

# Configure Celery
celery_app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

# Create a FastAPI instance
api = FastAPI()

# Define a custom decorator to combine Celery task and FastAPI route
def celery_fastapi_task(route: str, methods: list = ["GET", "POST"]):
    def decorator(func):
        # Register as a Celery task
        celery_task = celery_app.task(bind=True)(func)

        # Extract the function's argument names dynamically using the inspect module
        func_args = inspect.signature(func).parameters.keys()

        # Define a generic FastAPI handler that calls the Celery task
        async def fastapi_handler(**kwargs):
            # Extract only the arguments needed by the task
            task_args = [kwargs[arg] for arg in func_args]
            # Call the Celery task with the extracted arguments
            task = celery_task.delay(*task_args)
            return {'message': 'Task is being processed.', 'task_id': task.id}

        # Register the generic handler as a FastAPI route
        for method in methods:
            api.api_route(route, methods=[method])(fastapi_handler)

        return celery_task
    return decorator

# Use the combined decorator for a simple addition task
@celery_fastapi_task("/tasks/add", methods=["GET"])
def add(self, a: int, b: int):
    """Celery task to add two numbers."""
    return a + b

# Another example: Multiply task
@celery_fastapi_task("/tasks/multiply", methods=["GET"])
def multiply(self, a: int, b: int):
    """Celery task to multiply two numbers."""
    return a * b
