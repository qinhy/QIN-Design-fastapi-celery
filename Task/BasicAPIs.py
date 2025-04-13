# Standard library imports
import base64
import json
import re
import time
import datetime
from typing import Literal, Optional
import zlib
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
from fastapi import Query

# Common execution time parameter for API endpoints
EXECUTION_TIME_PARAM = Query(
    'NOW',
    description=(
        "Execution time in one of the following formats:\n"
        "- 'NOW' → immediate execution\n"
        "- '60' → delay of 60 seconds from now\n"
        "- '2025-04-03T06:00:30' → execute at this absolute datetime\n"
        "- 'NOW@every 10 s', '2025-04-03T06:00:30@every 1 d' → recurring schedule"
    )
)

# Valid timezones for scheduling
VALID_TIMEZONES = Literal[
    "UTC", "Asia/Tokyo", "America/New_York", "Europe/London",
    "Europe/Paris", "America/Los_Angeles", "Australia/Sydney", "Asia/Singapore"
]

# Common timezone parameter for API endpoints
TIMEZONE_PARAM = Query(
    "Asia/Tokyo",
    description="Timezone for scheduled execution time"
)

class BasicCeleryTask:
    
    ########################### Essential Constants
    EXECUTION_TIME_PARAM = EXECUTION_TIME_PARAM
    VALID_TIMEZONES = VALID_TIMEZONES
    TIMEZONE_PARAM = TIMEZONE_PARAM

    ########################### Initialization
    def __init__(self,
                 BasicApp: AppInterface,
                 celery_app,
                 root_fast_app: FastAPI,
                 ACTION_REGISTRY = {}):
        
        self.BasicApp = BasicApp
        self.celery_app = celery_app
        self.ACTION_REGISTRY: dict[str, ServiceOrientedArchitecture] = ACTION_REGISTRY
        self.pipelines = {}
        self.root_fast_app = root_fast_app
        self.load_code_snippet()

        # Initialize API router
        self.router = APIRouter()
        
        # Register API endpoints
        self._register_api_endpoints()
        
        # Setup Celery tasks and handlers
        self._setup_celery_tasks()
        
        # Auto-generate endpoints for each action
        self._register_action_endpoints()
    
    def _register_api_endpoints(self):
        """Register all API endpoints"""
        self.router.get("/tasks/")(self.api_list_tasks)
        self.router.get("/tasks/meta/{task_id}")(self.api_task_meta)
        self.router.get("/tasks/meta/delete/{task_id}")(self.api_task_meta_delete)
        self.router.get("/tasks/stop/{task_id}")(self.api_task_stop)
        self.router.get("/tasks/sub/{task_id}")(self.api_listen_data_of_task)
        self.router.get("/workers/")(self.api_get_workers)
        self.router.get("/action/list")(self.api_perform_action_list)
        self.router.post("/action/{name}")(self.api_perform_action)
        
        # Pipeline management endpoints
        self.router.get("/pipeline/list")(self.api_list_pipelines)
        # self.router.post("/pipeline/add")(self.api_add_pipeline)
        self.router.get("/pipeline/refresh")(self.api_refresh_pipeline)
        self.router.delete("/pipeline/delete")(self.api_delete_pipeline)
    
    def _register_action_endpoints(self):
        """Auto-generate endpoints for each action"""
        for action_name, action_class in self.ACTION_REGISTRY.items():
            self.add_web_api(
                self._make_api_action_handler(action_name, action_class),
                'post', f"/{action_name.lower()}/")
            
    def _setup_celery_tasks(self):
        """Setup Celery tasks and handlers"""
        # Register task received handler
        @task_received.connect
        def on_task_received(*args, **kwags):
            """Handle task received event"""
            request = kwags.get('request')
            if request is None:
                return
            headers = request.__dict__['_message'].headers
            self.BasicApp.set_task_status(headers['id'],
                            headers['argsrepr'], 'RECEIVED')
        
        self.on_task_received = on_task_received
        self.celery_perform_simple_action = self._create_celery_perform_simple_action()
        self.celery_perform_translate_action = self._create_celery_perform_translate_action()
        
    def _compress_result(self, content: str) -> str:
        "Compress a string using zlib and encode it as base64."
        if not content:
            return ""
        compressed_bytes = zlib.compress(content.encode('utf-8'))
        return base64.b64encode(compressed_bytes).decode('utf-8')

    def _decompress_result(self, compressed_b64: str) -> str:
        "Decompress a base64-encoded zlib-compressed string."
        if not compressed_b64:
            return ""
        try:
            compressed_bytes = base64.b64decode(compressed_b64)
            return zlib.decompress(compressed_bytes).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to decompress data: {str(e)}")
        
    def perform_simple_action(
        self,
        task_id: str,
        data: dict, 
        prior_data: dict = None,
        compress: bool = True,
    ) -> ServiceOrientedArchitecture.Model:
        """Execute a simple action with the given data"""
            
        model_instance, _, class_type = self._prepare_action(data)
        if prior_data:
            model_instance.update_model_data(prior_data)
        model_instance.task_id = task_id
        model_instance = class_type.Action(model_instance, BasicApp=self.BasicApp)()
        res = model_instance.model_dump_json()        
        res = self._compress_result(res) if compress else res
        return res
    
    def perform_translate_action(
        self,
        task_id: str,
        action_name: str,
        previous_data: dict,
        previous_to_current_map: dict = None,
        prior_data: dict = None,
    ) -> ServiceOrientedArchitecture.Model:
        """Execute an action with data translated from a previous action""" 
        
        if action_name not in self.ACTION_REGISTRY:
            raise ValueError(f"Action '{action_name}' is not registered.")            
        # Get the action class
        class_type: type[ServiceOrientedArchitecture] = self.ACTION_REGISTRY[action_name]            
        # Handle model creation based on pipeline context
        model_instance = class_type.Model(**class_type.Model.examples().pop(0))  

        previous_model_instance, previous_name, _ = self._prepare_action(previous_data)
        previous_data = previous_model_instance.model_dump()
        
        if previous_to_current_map:
            action_data = self._map_fields_between_models(
                previous_data, previous_to_current_map)
            
            # Create model with example data and update args
            model_instance.args = model_instance.args.model_copy(update=action_data)
        
        elif not previous_to_current_map:
            # Use smart conversion between models
            model_instance = self._convert_between_models(
                self.ACTION_REGISTRY[previous_name],
                class_type,
                previous_data
            )

        return self.perform_simple_action(task_id, model_instance.model_dump(), prior_data)
    
    def _create_celery_perform_simple_action(self):
        """Create the celery_perform_simple_action task"""
        @self.celery_app.task(bind=True)
        def celery_perform_simple_action(
            t: Task,
            data: dict, 
            prior_data: dict = None,
        ) -> ServiceOrientedArchitecture.Model:
            """Celery task wrapper for perform_simple_action"""
            return self.perform_simple_action(t.request.id, data, prior_data)
        
        return celery_perform_simple_action
    
    def _create_celery_perform_translate_action(self):
        """Create the celery_perform_translate_action task"""
        @self.celery_app.task(bind=True)
        def celery_perform_translate_action(
            t: Task,
            previous_data: dict,
            action_name: str,
            previous_to_current_map: dict = None,
            prior_data: dict = None,
        ) -> ServiceOrientedArchitecture.Model:
            """Celery task wrapper for perform_translate_action"""
            return self.perform_translate_action(t.request.id, action_name, previous_data, previous_to_current_map, prior_data)        
        return celery_perform_translate_action
    
    def _create_task_received_handler(self):
        """Create the task received event handler"""
        @task_received.connect
        def on_task_received(*args, **kwags):
            """Handle task received event"""
            request = kwags.get('request')
            if request is None:
                return
            headers = request.__dict__['_message'].headers
            self.BasicApp.set_task_status(headers['id'],
                            headers['argsrepr'], 'RECEIVED')
        
        return on_task_received
    
    def _prepare_action(self, json_data: dict | str):
        """Prepare and validate action data"""
        # Validate input
        if json_data is None:
            raise ValueError("json_data cannot be None")
            
        action_data = json_data
        
        # Parse JSON string if needed
        if isinstance(action_data, str):
            try:
                action_data = json.loads(action_data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {str(e)}") from e
        
        # Validate data structure
        if not isinstance(action_data, dict):
            raise TypeError(f"Expected dict or JSON string, got {type(action_data).__name__}")
            
        if 'version' not in action_data:
            raise KeyError("Missing required 'version' field in action data")
            
        if 'class_name' not in action_data.get('version', {}):
            raise KeyError("Missing required 'class_name' field in version data")

        action_name = action_data['version']['class_name']

        # Validate action exists
        if action_name not in self.ACTION_REGISTRY:
            available_actions = ", ".join(self.ACTION_REGISTRY.keys())
            raise ValueError(f"Action '{action_name}' is not registered. Available actions: {available_actions}")
        
        # Get the action class
        class_type: type[ServiceOrientedArchitecture] = self.ACTION_REGISTRY[action_name]
        model_instance = class_type.Model(**action_data)            
        return model_instance, action_name, class_type
    
    def _map_fields_between_models(self, action_data, previous_to_current_map):
        """Map specific fields from previous return to current args"""
        previous_ret_data = action_data['ret']
        current_args_data = {}
        for k, v in previous_to_current_map.items():
            current_args_data[k] = previous_ret_data[v]
        
        return current_args_data
    
    def _convert_between_models(
        self,
        pre_class_type: type[ServiceOrientedArchitecture],
        class_type: type[ServiceOrientedArchitecture],
        action_data: dict,
        smart_converter: SmartModelConverter = SmartModelConverter()
    ):
        """Convert data between different model types using smart conversion"""
        # Create model instances
        previous_model_instance = pre_class_type.Model(**action_data)
        model_instance = class_type.Model.examples().pop(0)
        model_instance = class_type.Model(**model_instance)
        
        # Get function name for conversion
        function_name = smart_converter.get_function_name(pre_class_type, class_type)
        code_snippet = self.get_code_snippet(function_name)
        
        if code_snippet is None:
            code_snippet, _ = smart_converter.build(pre_class_type, class_type)
            self.save_code_snippet(code_snippet, function_name)          

        conversion_func = smart_converter.get_func_from_code(code_snippet, function_name)

        model_instance, _ = smart_converter.convert_by_function(
            conversion_func, previous_model_instance, model_instance)
        return model_instance

    ########################### Time and Scheduling Methods
    @staticmethod
    def wait_until(execution_time_str, timezone_str='Asia/Tokyo', offset_seconds=-1):
        """
        Wait until the specified execution time.
        
        Args:
            execution_time_str: Execution time string in ISO format
            timezone_str: Timezone string
            offset_seconds: Offset in seconds to add to the execution time
        """
        # Split the datetime and the interval part (e.g., '2025-04-07T15:08:58@every 10 s')
        datetime_str, _ = execution_time_str.split('@')
        
        # Parse the next scheduled time
        tz = pytz.timezone(timezone_str)
        scheduled_time = datetime.fromisoformat(datetime_str)
        scheduled_time = tz.localize(scheduled_time)

        # Add the offset
        target_time = scheduled_time + datetime.timedelta(seconds=offset_seconds)

        # Wait until target time
        now = datetime.now(tz)
        sleep_seconds = (target_time - now).total_seconds()
        if sleep_seconds > 0:
            print(f"Waiting for {sleep_seconds:.2f} seconds...")
            time.sleep(sleep_seconds)
        else:
            print("Target time is in the past. Skipping wait.")

    @staticmethod
    def parse_execution_time(execution_time_str, timezone_str):
        """
        Parses the execution_time_str and returns:
        - utc_execution_time (datetime in UTC)
        - local_time (datetime in specified timezone)
        - next_execution_time_str (formatted in specified timezone)

        Recurrence must be at least every 10 seconds.
        Supports formats:
        - 'NOW'
        - '60' (delay in seconds)
        - 'YYYY-MM-DDTHH:MM:SS'
        - 'NOW@every 1 d', '2025-04-07T12:00:00@every 10 s', etc.
        """
        print('parse_execution_time: get', execution_time_str, timezone_str)

        utc_now = datetime.datetime.now(datetime.timezone.utc)
        tz = pytz.timezone(timezone_str)
        local_now = utc_now.astimezone(tz)

        utc_execution_time = None
        local_time = None
        next_execution_time_str = execution_time_str  # default

        try:
            # Match recurrence pattern: "<base>@every <num> <unit>"
            recur_match = re.match(r"^(.+?)@every\s+(\d+)\s*([smhd])$", execution_time_str.strip(), re.IGNORECASE)
            if recur_match:
                base_time_str, num_str, unit = recur_match.groups()
                unit = unit.lower()
                interval_seconds = {
                    's': int(num_str),
                    'm': int(num_str) * 60,
                    'h': int(num_str) * 3600,
                    'd': int(num_str) * 86400,
                }[unit]

                if interval_seconds < 10:
                    raise ValueError("Recurrence interval must be at least every 10 seconds.")

                # Resolve base time
                if base_time_str.upper() == "NOW":
                    base_local_time = local_now
                else:
                    base_local_time = datetime.datetime.strptime(base_time_str, "%Y-%m-%dT%H:%M:%S")
                    base_local_time = tz.localize(base_local_time)

                local_time = base_local_time + datetime.timedelta(seconds=interval_seconds)
                utc_execution_time = local_time.astimezone(pytz.UTC)

                formatted_base = (local_time + datetime.timedelta(seconds=interval_seconds)).strftime("%Y-%m-%dT%H:%M:%S")
                next_execution_time_str = f"{formatted_base}@every {num_str} {unit}"
            # Handle "NOW"
            elif execution_time_str.upper() == "NOW":
                utc_execution_time = utc_now
                local_time = local_now
                next_execution_time_str = None
            # Handle delay in seconds
            elif execution_time_str.isdigit():
                delay_seconds = int(execution_time_str)
                utc_execution_time = utc_now + datetime.timedelta(seconds=delay_seconds)
                local_time = utc_execution_time.astimezone(tz)
                next_execution_time_str = None
            else:
                # Handle absolute datetime
                local_time = datetime.datetime.strptime(execution_time_str, "%Y-%m-%dT%H:%M:%S")
                local_time = tz.localize(local_time)
                utc_execution_time = local_time.astimezone(pytz.UTC)
                next_execution_time_str = None

            print('parse_execution_time: return', utc_execution_time, '|', local_time, '|', (next_execution_time_str, timezone_str))    
            return utc_execution_time, local_time, (next_execution_time_str, timezone_str)

        except Exception as e:
            raise ValueError(f"Invalid execution_time format: {execution_time_str}. Error: {str(e)}")

    ########################### Code Snippet Management
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
            execution_time: str = self.EXECUTION_TIME_PARAM,
            timezone: self.VALID_TIMEZONES = self.TIMEZONE_PARAM
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

        r = res['result']
        try:
            r = json.loads(r)
        except Exception as e:
            r = self._decompress_result(r)

        res['result'] = r
        return res

    def api_task_meta_delete(self,task_id: str):
        self.api_ok()
        self.BasicApp.delete_task_meta(task_id)
        return {"status": "deleted", "task": task_id}

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
        execution_time: str = EXECUTION_TIME_PARAM,
        timezone: VALID_TIMEZONES = TIMEZONE_PARAM,
    ):
        
        """API endpoint to execute a generic action asynchronously with optional delay."""
        self.api_ok()

        # Validate that the requested action exists
        if name not in self.ACTION_REGISTRY:
            return {"error": f"Action '{name}' is not available."}      
        
        utc_execution_time, local_time, (next_execution_time_str,timezone_str) = self.parse_execution_time(execution_time, timezone)
        
        # Schedule the task
        task = self.celery_perform_simple_action.apply_async(
            # args=[data, prior_data,],
            args=[data, None,],
            eta=utc_execution_time)
        
        self.BasicApp.set_task_status(task.task_id,status='SENDED')
        if next_execution_time_str:
            return TaskModel.create_task_response(
                task, utc_execution_time, local_time, timezone,
                (next_execution_time_str,timezone_str))
        else:
            return TaskModel.create_task_response(
                task, utc_execution_time, local_time, timezone, None)
    
