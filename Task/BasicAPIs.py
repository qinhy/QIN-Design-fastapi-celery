import datetime
import sys
from typing import Literal, Optional

import pytz
sys.path.append("..")

from celery.app import task as Task
from fastapi import APIRouter, HTTPException, Query

from Task.Basic import AppInterface, ServiceOrientedArchitecture
from celery.signals import task_received

class BasicCeleryTask:
    def __init__(self,
                 BasicApp:AppInterface,
                 celery_app,
                 ACTION_REGISTRY = {}):
        
        self.BasicApp = BasicApp
        self.celery_app = celery_app
        self.ACTION_REGISTRY:dict[str, ServiceOrientedArchitecture] = ACTION_REGISTRY

        self.router = APIRouter()
        self.router.get("/tasks/")(
                                    self.api_list_tasks)
        self.router.get("/tasks/meta/{task_id}")(
                                    self.api_task_meta)
        self.router.get("/tasks/stop/{task_id}")(
                                    self.api_task_stop)
        self.router.get("/workers/")(
                                    self.get_workers)
        self.router.get("/action/list")(
                                    self.api_perform_action_list)
        self.router.post("/action/{name}")(
                                    self.api_perform_action)
        self.router.post("/action/{name}/schedule/")(
                                    self.api_schedule_perform_action)
        
        # Register the Celery task
        @self.celery_app.task(bind=True)
        def perform_action(t: Task, name: str, data: dict) -> int:
            """Generic Celery task to execute any registered action."""
            action_name, action_data = name, data
            if action_name not in self.ACTION_REGISTRY:
                raise ValueError(f"Action '{action_name}' is not registered.")

            # Initialize the action model and action handler
            class_space = self.ACTION_REGISTRY[action_name]
            model_instance = class_space.Model(**action_data)
            model_instance.task_id=t.request.id
            model_instance = class_space.Action(model_instance,BasicApp=BasicApp)()
            return self.is_json_serializable(model_instance.model_dump())

        @task_received.connect
        def on_task_received(*args, **kwags):
            request =  kwags.get('request')
            if request is None:return
            message =  request.__dict__['_message'].__dict__
            BasicApp.set_task_status(message['_raw']['headers']['id'],
                                    message['_raw']['headers']['argsrepr'],'RECEIVED')
            
        self.perform_action = perform_action

    
    ########################### essential function        
    def api_ok(self):
        if not self.BasicApp.check_services():
            raise HTTPException(status_code=503, detail={
                                'error': 'service not healthy'})

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

    def api_list_tasks(self,):
        self.api_ok()
        return self.BasicApp.get_tasks_list()

    def api_task_meta(self,task_id: str):
        self.api_ok()
        return self.BasicApp.get_task_meta(task_id)

    def api_task_stop(self,task_id: str):
        self.api_ok()
        self.BasicApp.send_data_to_task(task_id,{'status': 'REVOKED'})
        # return self.BasicApp.set_task_revoked(task_id)

    def get_workers(self,):
        # current_user: UserModels.User = Depends(AuthService.get_current_root_user)):
        self.api_ok()
        inspector = self.celery_app.control.inspect()
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
    def api_perform_action_list(self,):
        """Returns a list of all available actions that can be performed."""
        self.api_ok()
        available_actions = []
        for k,v in self.ACTION_REGISTRY.items():
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

    def api_perform_action(self,
        name: str, 
        data: dict,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        """API endpoint to execute a generic action asynchronously with optional delay."""
        self.api_ok()

        # Validate that the requested action exists
        if name not in self.ACTION_REGISTRY:
            return {"error": f"Action '{name}' is not available."}

        # Calculate execution time (eta)
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

        # Schedule the task
        task = self.perform_action.apply_async(args=[name, data], eta=execution_time)
        res = {'task_id': task.id}
        if execution_time: res['scheduled_for'] = execution_time
        return res
    
    def api_schedule_perform_action(self,
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
        local_dt,execution_time_utc = self.convert_to_utc(execution_time,timezone)
        
        # Schedule the task
        task = self.perform_action.apply_async(args=[name, data], eta=execution_time_utc)

        return {
            "task_id": task.id,
            f"scheduled_for_{timezone}": local_dt.isoformat(),
            "scheduled_for_utc": execution_time_utc.isoformat(),
            "timezone": timezone
        }












    