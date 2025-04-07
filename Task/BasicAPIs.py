# Standard library imports
import json
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
from Task.Basic import AppInterface, ServiceOrientedArchitecture, SmartModelConverter, TaskModel

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
        self.load_code_snippet()

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
        
        self.router.get("/pipeline/list")(self.api_list_pipelines)
        # self.router.post("/pipeline/add")(self.api_add_pipeline)
        self.router.get("/pipeline/refresh")(self.api_refresh_pipeline)
        self.router.delete("/pipeline/delete")(self.api_delete_pipeline)    
        
        def _convert_between_models(
            pre_class_type:type[ServiceOrientedArchitecture],
            class_type:type[ServiceOrientedArchitecture],
            action_data:dict,
            smart_converter:SmartModelConverter=SmartModelConverter()
        ):
            # Create model instances
            previous_model_instance = pre_class_type.Model(**action_data)
            model_instance = class_type.Model.examples().pop(0)
            model_instance = class_type.Model(**model_instance)
            
            # Get function name for conversion
            function_name = smart_converter.get_function_name(pre_class_type, class_type)
            code_snippet = self.get_code_snippet(function_name)
            
            if code_snippet is None:
                code_snippet,_ = smart_converter.build(pre_class_type, class_type)
                self.save_code_snippet(code_snippet, function_name)          

            conversion_func = smart_converter.get_func_from_code(code_snippet, function_name)

            model_instance,_ = smart_converter.convert_by_function(
                conversion_func, previous_model_instance, model_instance)
            return model_instance
        
        def _map_fields_between_models(action_data, previous_to_current_map,class_type):
            # Map specific fields from previous return to current args
            previous_ret_data = action_data['ret']
            current_args_data = {}
            for k, v in previous_to_current_map.items():
                current_args_data[k] = previous_ret_data[v]
            
            # Create model with example data and update args
            model_instance = class_type.Model(**class_type.Model.examples().pop(0))
            model_instance.args = model_instance.args.model_copy(update=current_args_data)
            return model_instance
        
        # Register the Celery task
        @self.celery_app.task(bind=True)
        def perform_action(
            t: Task, 
            data: dict, 
            name: str = 'NULL',
            prior_model_data: dict = None,
            previous_name: str = None,
            previous_to_current_map: dict = None,
            BasicApp = BasicApp
        ) -> int:
            """Generic Celery task to execute any registered action."""
            # Prepare action data
            action_name, action_data = name, data
            if isinstance(action_data, str):
                action_data = json.loads(action_data)

            # Validate action exists
            if action_name not in self.ACTION_REGISTRY:
                raise ValueError(f"Action '{action_name}' is not registered.")

            # Get the action class
            class_type: type[ServiceOrientedArchitecture] = self.ACTION_REGISTRY[action_name]
            
            # Handle model creation based on pipeline context
            model_instance = None
            
            # Case 1: No previous action in pipeline
            if not previous_name:
                # Create model directly from input data
                model_instance = class_type.Model(**action_data)
                
            # Case 2: Previous action with mapping provided
            elif previous_name and previous_to_current_map:
                model_instance = _map_fields_between_models(
                    action_data, previous_to_current_map, class_type)
                
            # Case 3: Previous action without mapping
            elif previous_name and not previous_to_current_map:
                # Use smart conversion between models
                model_instance = _convert_between_models(
                    self.ACTION_REGISTRY[previous_name],
                    class_type,
                    action_data
                )

            # Apply prior model configuration if provided
            model_instance = model_instance.update_model_data(prior_model_data)

            model_instance.task_id=t.request.id
            model_instance = class_type.Action(model_instance,BasicApp=BasicApp)()
            model_dump = model_instance.model_dump_json()
            return model_dump

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
    
    
    ########################### essential function
    
    def save_code_snippet(self, code_snippet: str, function_name: str):
        code_snippets = self.BasicApp.store().get('code_snippets')
        if code_snippets is None:
            code_snippets = {}
        code_snippets[function_name] = code_snippet
        self.BasicApp.store().set('code_snippets', code_snippets)
        with open(f'code_snippets.json', 'w') as f:
            json.dump(code_snippets, f)
            
    def load_code_snippet(self):
        try:
            code_snippets = self.BasicApp.store().get('code_snippets')
        except Exception as e:
            code_snippets = {}
        if code_snippets is None:
            code_snippets = {}
        try:
            with open(f'code_snippets.json', 'r') as f:
                code_snippets = json.load(f)
        except Exception as e:
            print(e)

        code_snippets.update(code_snippets)

        try:
            self.BasicApp.store().set('code_snippets', code_snippets)
        except Exception as e:
            print(e)
    
    def get_code_snippet(self, function_name: str):
        code_snippets = self.BasicApp.store().get('code_snippets')
        if code_snippets is None:
            return None
        return code_snippets.get(function_name, None)
    
    def _make_api_action_handler(self, action_name, action_class):
        examples = action_class.Model.examples() if hasattr(action_class.Model,'examples') else None
        
        def handler(
            task_model: action_class.Model = Body(..., examples=examples),                    
            execution_time: str = Query(
                'NOW',
                description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS (2025-04-03T06:00:30), NOW: no use"
            ),
            timezone: Literal[
                "UTC", "Asia/Tokyo", "America/New_York", "Europe/London",
                "Europe/Paris", "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
            ] = Query(
                "Asia/Tokyo",
                description="Choose a timezone from the list, if execution_time is not NOW"
            )
        ):
                            
            return self.api_perform_action(action_name, task_model.model_dump(),
                                            execution_time=execution_time,
                                            timezone=timezone)
        return handler
    
    def api_ok(self):
        if not self.BasicApp.check_services():
            raise HTTPException(status_code=503, detail={
                                'error': 'service not healthy'})
        
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
        execution_time: str = Query(
            'NOW',
            description="Datetime for execution in format YYYY-MM-DDTHH:MM:SS (2025-04-03T06:00:30), NOW: no use"
        ),
        timezone: Literal[
            "UTC", "Asia/Tokyo", "America/New_York", "Europe/London",
            "Europe/Paris", "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
        ] = Query(
            "Asia/Tokyo",
            description="Choose a timezone from the list, if execution_time is not NOW"
        )
    ):
        
        """API endpoint to execute a generic action asynchronously with optional delay."""
        self.api_ok()

        # Validate that the requested action exists
        if name not in self.ACTION_REGISTRY:
            return {"error": f"Action '{name}' is not available."}      
        
        utc_execution_time = None
        local_time = None

        try:
            if execution_time.upper() == "NOW":
                utc_execution_time = datetime.datetime.now(datetime.timezone.utc)
            elif execution_time.isdigit():
                delay_seconds = int(execution_time)
                utc_execution_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay_seconds)
            else:
                # Parse the datetime string
                local_time = datetime.datetime.strptime(execution_time, "%Y-%m-%dT%H:%M:%S")
                # Localize it to the given timezone
                tz = pytz.timezone(timezone)
                local_time = tz.localize(local_time)
                # Convert to UTC
                utc_execution_time = local_time.astimezone(pytz.UTC)
        except Exception as e:
            raise ValueError(f"Invalid execution_time format: {execution_time}. Error: {str(e)}")
        # Schedule the task
        task = self.perform_action.apply_async(
            # args=[data, name, prior_model_data, previous_name,previous_to_current_map],
            args=[data, name, None, None, None],
            eta=utc_execution_time)

        return TaskModel(task_id=task.task_id,
                        scheduled_for_the_timezone=local_time,
                        timezone=timezone if local_time is not None else None,
                        scheduled_for_utc=utc_execution_time,
                    ).model_dump(exclude_none=True)

    
