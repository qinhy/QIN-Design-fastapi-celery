import os
from fastapi.responses import FileResponse, HTMLResponse

from User.UserAPIs import AuthService, UserModels, router as users_router
from Task.Customs import Fibonacci, ServiceOrientedArchitecture

from Task.Basic import AppInterface,RedisApp,RabbitmqMongoApp

from Config import APP_BACK_END, SESSION_DURATION, APP_SECRET_KEY, RABBITMQ_URL, MONGO_URL, MONGO_DB, CELERY_META, CELERY_RABBITMQ_BROKER, RABBITMQ_USER, RABBITMQ_PASSWORD, REDIS_URL
if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp(REDIS_URL)
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,
                                             MONGO_URL,MONGO_DB,CELERY_META,
                                             CELERY_RABBITMQ_BROKER)
else:
    raise ValueError(f'no back end of {APP_BACK_END}')
ServiceOrientedArchitecture.BasicApp  = BasicApp

from Vision import Service as VisonService
from celery.app import task as Task
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException
from typing import Dict

celery_app = BasicApp.get_celery_app()

def api_ok():
    if not BasicApp.check_services():
        raise HTTPException(status_code=503, detail={
                            'error': 'service not healthy'})

class CeleryTask:

    api = FastAPI()

    api.add_middleware(
        CORSMiddleware,
        allow_origins=['*',],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.add_middleware(SessionMiddleware,
                       secret_key=APP_SECRET_KEY, max_age=SESSION_DURATION)

    api.include_router(users_router, prefix="", tags=["users"])

    @staticmethod
    @api.get("/", response_class=HTMLResponse)
    async def get_register_page():
        return FileResponse(os.path.join(os.path.dirname(__file__), "vue-gui.html"))
    ########################### essential function
    @staticmethod
    def is_json_serializable(value) -> bool:
        res = isinstance(value, (int, float, bool, str,
                                 list, dict, set, tuple)) or value is None
        if not res:
            raise ValueError("Result is not JSON serializable")
        return value

    @api.get("/tasks/")
    def api_list_tasks():
        api_ok()
        return BasicApp.get_tasks_list()

    @api.get("/tasks/meta/{task_id}")
    def api_task_meta(task_id: str):
        api_ok()
        return BasicApp.get_task_meta(task_id)

    @api.get("/tasks/stop/{task_id}")
    def api_task_stop(task_id: str):
        api_ok()
        BasicApp.send_data_to_task(task_id,{'status': 'REVOKED'})
        # return BasicApp.set_task_revoked(task_id)

    @api.get("/workers/")
    def get_workers():
        # current_user: UserModels.User = Depends(AuthService.get_current_root_user)):
        api_ok()
        inspector = celery_app.control.inspect()
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

    ########################### basic function
    @staticmethod
    @celery_app.task(bind=True)
    def fibonacci(t: Task, fib_task_model_dump: dict) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        fib_task_model_dump['task_id'] = t.request.id
        model = Fibonacci.Model(**fib_task_model_dump)
        model = Fibonacci.Action(model)()
        res: Fibonacci.Model.Return = model.ret
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
        action_name, action_data = name, data
        ACTION_REGISTRY: Dict[str, ServiceOrientedArchitecture] = {
            'Fibonacci': Fibonacci,
            'CvCameraSharedMemoryService': VisonService.CvCameraSharedMemoryService,
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
    def api_perform_action(action: dict = dict(
            name='Fibonacci', data=dict(args=dict(n=10)))):
        api_ok()
        task = CeleryTask.perform_action.delay(action['name'], action['data'])
        return {'task_id': task.id}

    ############################# general function specific api

    @api.post("/actions/fibonacci")
    def api_actions_fibonacci(data: Fibonacci.Model):
        api_ok()
        """Endpoint to calculate Fibonacci number asynchronously using Celery."""
        act = dict(name='Fibonacci', data=data.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    @api.get("/streams/write")
    # 3840, 2160  480,640
    def api_actions_camera_write(stream_key: str = 'camera:0', h: int = 600, w: int = 800):
        api_ok()
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    @api.get("/streams/read")
    def api_actions_camera_read(stream_key: str = 'camera:0'):
        api_ok()
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='read', stream_key=stream_key, array_shape=info['array_shape']))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}

    ########################### basic function with auth
    @staticmethod
    @celery_app.task(bind=True,)
    def fibonacci(t: Task, fib_task_model_dump: dict,) -> int:
        """Celery task to calculate the nth Fibonacci number."""
        fib_task_model_dump['task_id'] = t.request.id
        model = Fibonacci.Model(**fib_task_model_dump)
        model = Fibonacci.Action(model)()
        res: Fibonacci.Model.Return = model.ret
        # make sure that res is dict or other primitive objects for json serialization
        return CeleryTask.is_json_serializable(res.model_dump())

    @api.post("/auth/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model,
                      current_payload: UserModels.User = Depends(AuthService.get_current_payload)):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}
    
    
    @api.post("/auth/local/fibonacci/")
    def api_fibonacci(fib_task: Fibonacci.Model,
                      current_payload: UserModels.User = Depends(AuthService.get_current_payload_if_not_local)):
        api_ok()
        task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        return {'task_id': task.id}
        # build GUI
        # I have a python api like following and need you to build primuevue GUI along the example.
        # ```python        
        # @api.post("/auth/local/fibonacci/")
        # def api_fibonacci(fib_task: Fibonacci.Model,
        #                 current_user: UserModels.User = Depends(AuthService.get_current_payload_if_not_local)):
        #     api_ok()
        #     task = CeleryTask.fibonacci.delay(fib_task.model_dump())
        #     return {'task_id': task.id}
        # # Request body
        # # Example Value
        # # Schema
        # # {
        # #   "task_id": "AUTO_SET_BUT_NULL_NOW",
        # #   "param": {
        # #     "mode": "fast"
        # #   },
        # #   "args": {
        # #     "n": 1
        # #   },
        # #   "ret": {
        # #     "n": -1
        # #   }
        # # }
        # ```


        # ```vue gui example
        # <p-tabpanel value="Profile">
        #     <div>
        #         <h2 class="text-xl font-bold mb-4">Edit User Info</h2>
        #         <form @submit.prevent="api.editUserInfo">
        #             <!-- UUID (Disabled) -->
        #             <p-inputtext v-model="editForm.uuid" disabled placeholder="UUID"
        #                 class="border p-2 rounded w-full mb-2"></p-inputtext>

        #             <!-- Email (Disabled) -->
        #             <p-inputtext v-model="editForm.email" disabled placeholder="Email"
        #                 class="border p-2 rounded w-full mb-2"></p-inputtext>

        #             <p-button severity="danger" class="border p-2 rounded w-full mb-2 top-1">Remove
        #                 Account</p-button>
        #         </form>
        #     </div>
        # </p-tabpanel>
        # ````

