# Standard library imports
import time
import datetime
from typing import Literal, Optional

# Third-party imports
import celery
import pytz
from celery.app import task as Task
from celery.signals import task_received

# FastAPI imports
from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

# Application imports
from Task.Basic import AppInterface, ServiceOrientedArchitecture, TaskModel

class BasicCeleryTask:
    def __init__(self,
                 BasicApp:AppInterface,
                 celery_app,
                 root_fast_app:FastAPI,
                 ACTION_REGISTRY = {}):
        
        self.BasicApp = BasicApp
        self.celery_app = celery_app
        self.ACTION_REGISTRY:dict[str, ServiceOrientedArchitecture] = ACTION_REGISTRY
        self.pipelines = {}

        self.root_fast_app = root_fast_app

        self.router = APIRouter()
        self.router.get("/tasks/")(
                                    self.api_list_tasks)
        self.router.get("/tasks/meta/{task_id}")(
                                    self.api_task_meta)
        self.router.get("/tasks/stop/{task_id}")(
                                    self.api_task_stop)
        self.router.get("/tasks/sub/{task_id}")(
                                    self.api_listen_data_of_task)
        self.router.get("/workers/")(
                                    self.api_get_workers)
        self.router.get("/action/list")(
                                    self.api_perform_action_list)
        self.router.post("/action/{name}")(
                                    self.api_perform_action)
        self.router.post("/action/{name}/schedule/")(
                                    self.api_schedule_perform_action)        
        
        self.router.get("/pipeline/list")(self.api_list_pipelines)
        # self.router.post("/pipeline/add")(self.api_add_pipeline)
        self.router.get("/pipeline/refresh")(self.api_refresh_pipeline)
        self.router.delete("/pipeline/delete")(self.api_delete_pipeline)        
        
        # Register the Celery task
        @self.celery_app.task(bind=True)
        def perform_action(t: Task, name: str, data: dict,
                           previous_name:str=None, BasicApp=BasicApp) -> int:
            """Generic Celery task to execute any registered action."""
            action_name, action_data = name, data
            if action_name not in self.ACTION_REGISTRY:
                raise ValueError(f"Action '{action_name}' is not registered.")

            # Initialize the action model and action handler
            class_space = self.ACTION_REGISTRY[action_name]
            previous_class_space= self.ACTION_REGISTRY.get(previous_name,None)
            if previous_class_space is not None:
                previous_model_instance = previous_class_space.Model(**action_data)
                model_instance = previous_model_instance.to(class_space)
            else:
                model_instance = class_space.Model(**action_data)

            model_instance.task_id=t.request.id
            model_instance = class_space.Action(model_instance,BasicApp=BasicApp)()
            model_dump = model_instance.model_dump_json()
            return model_dump
            # return self.is_json_serializable(model_instance.model_dump())

        @task_received.connect
        def on_task_received(*args, **kwags):
            request =  kwags.get('request')
            if request is None:return
            headers =  request.__dict__['_message'].headers
            BasicApp.set_task_status(headers['id'],
                            headers['argsrepr'],'RECEIVED')
            
        self.perform_action = perform_action
        self.on_task_received = on_task_received

        # Auto-generate endpoints for each action
        for action_name, action_class in ACTION_REGISTRY.items():
            self.add_web_api(
                self._make_api_action_handler(action_name, action_class),
                'post',f"/{action_name.lower()}/")
            self.add_web_api(
                self._make_api_schedule_handler(action_name, action_class),
                'post',f"/{action_name.lower()}/schedule/")
    
    
    ########################### essential function            

    def _make_api_action_handler(self, action_name, action_class):
        examples = action_class.Model.examples() if hasattr(action_class.Model,'examples') else None
        eta_example: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
        if examples:
            def handler(task_model: action_class.Model=Body(..., examples=examples),eta: Optional[int]=eta_example):
                return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        else:
            def handler(task_model: action_class.Model,eta: Optional[int]=eta_example):
                return self.api_perform_action(action_name, task_model.model_dump(), eta=eta)
        return handler

    def _make_api_schedule_handler(self, action_name, action_class):
        examples = action_class.Model.examples() if hasattr(action_class.Model,'examples') else None
        execution_time_example = Query(
                            datetime.datetime.now(datetime.timezone.utc).isoformat().split('.')[0],
                            description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS")
        timezone_Literal = Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
                                        "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"]
        timezone_Literal_example = Query("Asia/Tokyo", description="Choose a timezone from the list")
        if examples:
            def handler(task_model: action_class.Model=Body(..., examples=examples),
                        execution_time: str = execution_time_example,
                        timezone: timezone_Literal = timezone_Literal_example):
                        return self.api_schedule_perform_action(action_name, task_model.model_dump(), execution_time, timezone)
        else:
            def handler(task_model: action_class.Model,
                        execution_time: str = execution_time_example,
                        timezone: timezone_Literal = timezone_Literal_example):
                        return self.api_schedule_perform_action(action_name, task_model.model_dump(), execution_time, timezone)
        return handler
    
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
    
    def _reload_routes(self, root_fast_app:FastAPI):            
        router_route_names = {route.name for route in self.router.routes}
        root_fast_app.router.routes = [
            route for route in root_fast_app.router.routes
            if not (isinstance(route, APIRoute) and route.name in router_route_names)
        ]

        # refresh docs
        root_fast_app.openapi_schema = None
        root_fast_app.openapi = lambda: get_openapi(
            title=root_fast_app.title,
            version=root_fast_app.version,
            routes=root_fast_app.routes,
        )
        

    def reload_routes(self):
        self._reload_routes(self.root_fast_app)
        self.root_fast_app.include_router(self.router, prefix="", tags=["Tasks"])
        
    def api_refresh_pipeline(self):
        """Refresh existing pipelines"""
        self.refresh_pipeline()
        self.reload_routes()
        return {"status": "refreshed"}
    
    def api_delete_pipeline(self, name: str):
        """Delete an existing pipeline"""
        self.delete_pipeline(name)    
        self.reload_routes()
        return {"status": "deleted", "pipeline": name}
        
    def add_web_api(self, func, method: str = 'post', endpoint: str = '/'):
        method = method.lower().strip()
        allowed_methods = {
            'get':    self.router.get,
            'post':   self.router.post,
            'put':    self.router.put,
            'delete': self.router.delete,
            'patch':  self.router.patch,
            'options':self.router.options,
            'head':   self.router.head,
        }

        if method not in allowed_methods:
            raise ValueError(
                f"Method '{method}' is not allowed. "
                f"Supported methods: {', '.join(allowed_methods)}")

        allowed_methods[method](endpoint)(func)
        return self
    
    def api_list_pipelines(self,):
        self.api_ok()
        pipelines = self.BasicApp.store().get('pipelines')
        if pipelines is None:
            self.BasicApp.store().set('pipelines',{})
            pipelines = {}
        return pipelines
    
    def delete_pipeline(self, name: str):
        self.api_ok()

        # Remove the route from the router
        self.router.routes = [route for route in self.router.routes if route.name != name]
        
        # Remove from pipelines dictionary
        if name in self.pipelines:
            del self.pipelines[name]
            
        # Update the stored pipelines
        self.BasicApp.store().set('pipelines', self.pipelines)
        
        return {"status": "deleted", "pipeline": name}

    def refresh_pipeline(self):
        # get from redis
        server_pipelines = self.api_list_pipelines()        
        # add and delete
        add_pipelines = {i for i in server_pipelines if i not in self.pipelines}
        delete_pipelines = {i for i in self.pipelines if i not in server_pipelines}

        print(add_pipelines,delete_pipelines)
        
        # Delete pipelines that are no longer in server
        for name in delete_pipelines:
            self.delete_pipeline(name)
        
        # Add new pipelines from server
        for name in add_pipelines:
            pipeline_info = server_pipelines[name]
            self.api_add_pipeline(
                name=name,
                pipeline=pipeline_info,
            )
        # Update local pipelines dictionary
        self.pipelines = server_pipelines

    def api_list_tasks(self,):
        self.api_ok()
        return self.BasicApp.get_tasks_list()

    def api_task_meta(self,task_id: str):
        self.api_ok()
        res = self.BasicApp.get_task_meta(task_id)
        if res is None:raise HTTPException(status_code=404, detail="task not found")
        return res

    def api_task_stop(self,task_id: str):
        self.api_ok()
        self.BasicApp.send_data_to_task(task_id,{'status': 'REVOKED'})
        self.BasicApp.set_task_status(task_id,'','REVOKED')

    def api_listen_data_of_task(self, task_id: str,
                                      request: Request):
        self.api_ok()
        meta = self.BasicApp.get_task_meta(task_id)
        if meta is None:raise HTTPException(status_code=404, detail="task not found")

        async def stream_task_messages(task_id: str, request: Request, BasicApp:AppInterface=None):
            yield_queue = []

            def handle_msg(msg: str):
                yield_queue.append(msg)

            # Start listener
            listener_id = BasicApp.listen_data_of_task(task_id, handle_msg,True)
            
            try:
                while True:
                    # Break if client disconnected
                    if await request.is_disconnected():
                        print(f"[Info] Client disconnected from task {task_id}")
                        break

                    while yield_queue:
                        msg = yield_queue.pop(0)
                        yield f"data: {msg}\n\n"
                        time.sleep(0.1)  # prevent tight loop
                    else:
                        time.sleep(0.1)  # prevent tight loop
            finally:
                BasicApp.unsubscribe(listener_id)

        return StreamingResponse(
            stream_task_messages(task_id,request,self.BasicApp),
            media_type="text/event-stream")
    def api_get_workers(self,):
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
    )->TaskModel:
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
        return TaskModel(task_id=task.id,
                        scheduled_for_utc=execution_time
                        ).model_dump(exclude_none=True)
    
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
        local_dt,execution_time = self.convert_to_utc(execution_time,timezone)
        
        # Schedule the task
        task = self.perform_action.apply_async(args=[name, data], eta=execution_time)

        return TaskModel(
            task_id=task.id,
            scheduled_for_the_timezone=local_dt,
            scheduled_for_utc=execution_time,
            timezone=timezone
        ).model_dump(exclude_none=True)


    # def api_perform_pipeline(self,
    #     names: list[str], 
    #     data: dict,
    #     eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    # )->TaskModel:
    #     """API endpoint to execute a generic action asynchronously with optional delay."""
    #     self.api_ok()

    #     actions = []
    #     for name in names:
    #         # Validate that the requested action exists
    #         if name not in self.ACTION_REGISTRY:
    #             return {"error": f"Action '{name}' is not available."}
    #         actions.append(self.perform_action.s(args=[name, data]))
        
    #     # Calculate execution time (eta)
    #     now_t = datetime.datetime.now(datetime.timezone.utc)
    #     execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None

    #     # Schedule the task
    #     action_chain = celery.chain(*actions)
    #     task = action_chain.apply_async(eta=execution_time)
    #     return TaskModel(task_id=task.id,
    #                     scheduled_for_utc=execution_time
    #                     ).model_dump(exclude_none=True)


    # def api_schedule_perform_pipeline(self,
    #     names: list[str], 
    #     data: dict,
    #     execution_time: str = Query(datetime.datetime.now(datetime.timezone.utc
    #       ).isoformat().split('.')[0], description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS"),
    #     timezone: Literal["UTC", "Asia/Tokyo", "America/New_York", "Europe/London", "Europe/Paris",
    #                     "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"] = Query("Asia/Tokyo", 
    #                     description="Choose a timezone from the list")
    # ):
    #     """API to execute Fibonacci task at a specific date and time, with timezone support."""
    #     # Convert to UTC for Celery
    #     local_dt,execution_time = self.convert_to_utc(execution_time,timezone)
        
    #     actions = []
    #     for name in names:
    #         # Validate that the requested action exists
    #         if name not in self.ACTION_REGISTRY:
    #             return {"error": f"Action '{name}' is not available."}
    #         actions.append(self.perform_action.s(args=[name, data]))
        
    #     # Schedule the task
    #     action_chain = celery.chain(*actions)
    #     task = action_chain.apply_async(args=[name, data], eta=execution_time)

    #     return TaskModel(
    #         task_id=task.id,
    #         scheduled_for_the_timezone=local_dt,
    #         scheduled_for_utc=execution_time,
    #         timezone=timezone
    #     ).model_dump(exclude_none=True)






    