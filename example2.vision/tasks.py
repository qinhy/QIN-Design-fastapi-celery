
import datetime
import sys
from typing import Optional

from fastapi.responses import HTMLResponse, RedirectResponse
sys.path.append("..")

from fastapi import HTTPException
from fastapi import Query

from basic_tasks import BasicApp, BasicCeleryTask, celery_app, api, api_ok

from Task.Basic import ServiceOrientedArchitecture
from Vision import Service as VisonService

BasicCeleryTask.ACTION_REGISTRY = {
    'CvCameraSharedMemoryService': VisonService.CvCameraSharedMemoryService,
}

class CeleryTask(BasicCeleryTask):
    api = api
    
    @staticmethod
    @api.get("/", response_class=HTMLResponse)
    async def get_doc_page():
        return RedirectResponse("/docs")
    
    ############################# general function specific api
    @api.get("/streams/write")
    # 3840, 2160  480,640
    def api_actions_camera_write(stream_key: str = 'camera:0', h: int = 600, w: int = 800,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        api_ok()
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None
        
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))

        task = CeleryTask.perform_action.apply_async(
            args=['CvCameraSharedMemoryService', data_model.model_dump()], eta=execution_time)
        
        return {'task_id': task.id}


    @api.get("/streams/read")
    def api_actions_camera_read(stream_key: str = 'camera:0',
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        api_ok()
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None
        
        info = BasicApp.store().get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = VisonService.CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='read', stream_key=stream_key, array_shape=info['array_shape']))
        
        task = CeleryTask.perform_action.apply_async(
            args=['CvCameraSharedMemoryService', data_model.model_dump()], eta=execution_time)
        
        return {'task_id': task.id}
