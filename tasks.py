import os
import random
import time
from fastapi.responses import FileResponse, HTMLResponse

from User.UserAPIs import AuthService, UserModels, router as users_router
from Task.Basic import BasicApp
from Task.Customs import CvCameraSharedMemoryService, Fibonacci, ServiceOrientedArchitecture

from celery.app import task as Task
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException

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
    
    ########################### original function
    @staticmethod
    @celery_app.task(bind=True)
    def add_terminal(t:Task, broker: str, path: str):
        return MT5Manager().get_singleton().add_terminal(broker,path)    
    @staticmethod
    @api.post("/terminals/add")
    def api_add_terminal(broker: str, path: str):
        api_ok()
        """Endpoint to add a terminal to MT5."""
        task = CeleryTask.add_terminal.delay(broker, path)
        return {'task_id': task.id}
        
    @staticmethod
    @celery_app.task(bind=True)
    def get_terminal(t:Task):
        print(MT5Manager().get_singleton().terminals)
        return { k:[i.exe_path for i in v] for k,v in MT5Manager().get_singleton().terminals.items()}
    @staticmethod
    @api.get("/terminals/")
    def api_get_terminal():
        api_ok()
        task = CeleryTask.get_terminal.delay()
        return {'task_id': task.id}
    
    @staticmethod
    @celery_app.task(bind=True)
    def perform_action(t: Task, name: str, data: dict) -> int:
        """Generic Celery task to execute any registered action."""
        action_name, action_data = name, data
        ACTION_REGISTRY: Dict[str, ServiceOrientedArchitecture] = {
            'Fibonacci': Fibonacci,
            'CvCameraSharedMemoryService': CvCameraSharedMemoryService,
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
        """Endpoint to fetch account information."""
        task = CeleryTask.book_action.delay(acc.model_dump(), Book().model_dump(), action='account_info')
        return {'task_id': task.id}

    @staticmethod
    @api.get("/books/")
    def api_get_books(acc: MT5Account):
        api_ok()
        """Endpoint to get books for a given MT5 account."""
        task = CeleryTask.book_action.delay(acc.model_dump(), Book().model_dump(), action='getBooks')
        return {'task_id': task.id}

    @api.get("/streams/write")
    # 3840, 2160  480,640
    def api_actions_camera_write(stream_key: str = 'camera:0', h: int = 2160*2*2, w: int = 3840*2*2):
        api_ok()
        info = BasicApp.store.get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}


    @staticmethod
    @api.post("/books/close")
    def api_book_close(acc: MT5Account, book: Book):
        api_ok()
        info = BasicApp.store.get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='read', stream_key=stream_key, array_shape=info['array_shape']))
        act = dict(name='CvCameraSharedMemoryService',
                   data=data_model.model_dump())
        task = CeleryTask.perform_action.delay(**act)
        return {'task_id': task.id}


    @staticmethod
    @api.post("/books/change/price")
    def api_book_change_price(acc: MT5Account, book: Book, p: float):
        api_ok()
        """Endpoint to change the price of a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='changeP', p=p)
        return {'task_id': task.id}


    @staticmethod
    @api.post("/books/change/tpsl")
    def api_book_change_tp_sl(acc: MT5Account, book: Book, tp: float, sl: float):
        api_ok()
        """Endpoint to change tp sl values of a book."""
        task = CeleryTask.book_action.delay(acc.model_dump(), book.model_dump(), action='changeTS', tp=tp, sl=sl)
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
        # #   "task_id": "NO_NEED_INPUT",
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

