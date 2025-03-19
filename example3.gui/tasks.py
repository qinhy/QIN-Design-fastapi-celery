import datetime
import os
import sys
sys.path.append("..")

import threading
import time
from typing import Optional
import cv2
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from fastapi import FastAPI, HTTPException, Query
from pydantic import Field
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from Task.Basic import AppInterface, CommonStreamIO, RabbitmqMongoApp, RedisApp, ServiceOrientedArchitecture
from Task.BasicAPIs import BasicCeleryTask
from Vision.BasicModel import NumpyUInt8SharedMemoryStreamIO, VideoStreamReader


class CvCameraSharedMemoryService(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):        
        class Param(ServiceOrientedArchitecture.Model.Param):
            _stream_reader:CommonStreamIO.StreamReader=None
            _stream_writer:CommonStreamIO.StreamWriter=None
            stream_key: str = Field(default='camera:0', description="The name of the stream")
            array_shape: tuple = Field(default=(480, 640), description="Shape of the NumPy array to store in shared memory")
            mode:str='write'
            _writer:NumpyUInt8SharedMemoryStreamIO.Writer=None
            _reader:NumpyUInt8SharedMemoryStreamIO.Reader=None
            _video_reader:NumpyUInt8SharedMemoryStreamIO.Reader=None
            
            def is_write(self):
                return self.mode=='write'
            
            def video_reader(self,video_src):
                if self._video_reader is None:
                    self._video_reader = VideoStreamReader.reader(
                        video_src=video_src).init()
                return self._video_reader
            
            def writer(self):
                if self._writer is None:
                    self._writer = NumpyUInt8SharedMemoryStreamIO.writer(
                        self.stream_key,self.array_shape)
                return self._writer

            def reader(self):
                if self._reader is None:
                    self._reader = NumpyUInt8SharedMemoryStreamIO.reader(
                        self.stream_key,self.array_shape)
                return self._reader

        class Args(ServiceOrientedArchitecture.Model.Args):
            camera:int = 0

        param:Param = Param()
        args:Args = Args()
        ret:str = 'NULL'
        
        def set_param(self, stream_key="camera_shm", array_shape=(480, 640), mode = 'write'):
            self.param = CvCameraSharedMemoryService.Model.Param(
                            mode=mode,stream_key=stream_key,array_shape=array_shape)
            return self

        def set_args(self, camera=0):
            self.args = CvCameraSharedMemoryService.Model.Args(camera=camera)
            return self
        
    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level='ERROR'):
            super().__init__(model, BasicApp, level)
            self.model: CvCameraSharedMemoryService.Model = self.model
            

        def run(self,frame_processor,stop_flag:threading.Event):
            stream_reader:ServiceOrientedArchitectureObjects.CommonStreamIO.StreamReader = self.model.param._stream_reader
            stream_writer:ServiceOrientedArchitectureObjects.CommonStreamIO.StreamWriter = self.model.param._stream_writer
            if stream_reader is None:raise ValueError('stream_reader is None')
            if stream_writer is None:raise ValueError('stream_writer is None')
            res = {'msg':''}
            try:
                for frame_count,(image,frame_metadata) in enumerate(stream_reader):
                    if stop_flag.is_set(): break
                    if frame_count%100==0:
                        start_time = time.time()
                    else:
                        elapsed_time = time.time() - start_time + 1e-5
                        frame_metadata['fps'] = fps = (frame_count%100) / elapsed_time
                        
                    image,frame_processor_metadata = frame_processor(frame_count,image,frame_metadata)
                    frame_metadata.update(frame_processor_metadata)
                    stream_writer.write(image,frame_metadata)

                    if frame_count%1000==100:
                        steam_info = stream_writer.get_steam_info()
                        steam_info['fps'] = fps
                        stream_writer.set_steam_info(steam_info)
                        msg = f"id:{steam_info['id']},fps:{fps:.2f},stream_key:{steam_info['stream_key']},array_shape:{steam_info['array_shape']}"
                        self.logger.info(msg)
                        self.send_data_to_task({'msg':msg})

            except Exception as e:
                    res['error'] = str(e)
                    print(res)
            finally:
                stream_reader.close()
                stream_writer.close()
                return res   

                
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                
                if self.model.param.is_write():                    
                    self.model.param._stream_reader = self.model.param.video_reader(self.model.args.camera)
                    self.model.param._stream_writer = writer = self.model.param.writer()
                    def frame_processor(i,frame,frame_metadata):
                        # print(i, frame.shape, 'fps', frame_metadata.get('fps',0),end='\r')
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        frame = cv2.resize(frame, (writer.array_shape[1], writer.array_shape[0]))
                        return frame,frame_metadata
                    self.run(frame_processor,stop_flag)

                else:
                    # reading
                    reader = self.model.param.reader()
                    title = f'Shared Memory Reader Frame:{reader.id}'
                    self.logger.info("reading")
                    while not stop_flag.is_set():
                        # Read the frame from shared memory
                        frame,_ = reader.read()
                        if frame is None:
                            self.logger.info("No frame read from shared memory.")
                            continue

                        # Display the frame
                        cv2.imshow(title, frame)

                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break

                    cv2.destroyWindow(title)
                
                return self.model

class CeleryTask(BasicCeleryTask):
    def __init__(self, BasicApp, celery_app,
                        ACTION_REGISTRY={'CvCameraSharedMemoryService': CvCameraSharedMemoryService,}):
        super().__init__(BasicApp, celery_app, ACTION_REGISTRY)
        self.router.get("/")(self.get_doc_page)
        self.router.get("/streams/write")(self.api_actions_camera_write)
        self.router.get("/streams/read")(self.api_actions_camera_read)
        

    async def get_doc_page(self):
        return FileResponse(os.path.join(os.path.dirname(__file__), "gui.html"))    
    
    ############################# general function specific api
    # 3840, 2160  480,640
    def api_actions_camera_write(self, stream_key: str = 'camera:0', h: int = 600, w: int = 800,
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        self.api_ok()
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None
        
        info = self.BasicApp.store().get(f'streams:{stream_key}')
        if info is not None:
            raise HTTPException(status_code=503, detail={
                                'error': f'stream of [streams:{stream_key}] has created'})

        CCModel = CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='write', stream_key=stream_key, array_shape=(h, w)))

        task = self.perform_action.apply_async(
            args=['CvCameraSharedMemoryService', data_model.model_dump()], eta=execution_time)
        
        return {'task_id': task.id}


    def api_actions_camera_read(self, stream_key: str = 'camera:0',
        eta: Optional[int] = Query(0, description="Time delay in seconds before execution (default: 0)")
    ):
        self.api_ok()
        now_t = datetime.datetime.now(datetime.timezone.utc)
        execution_time = now_t + datetime.timedelta(seconds=eta) if eta > 0 else None
        
        info = self.BasicApp.store().get(f'streams:{stream_key}')
        if info is None:
            raise HTTPException(status_code=503, detail={
                                'error': f'not such stream of [streams:{stream_key}]'})

        CCModel = CvCameraSharedMemoryService.Model
        data_model = CCModel(param=CCModel.Param(
            mode='read', stream_key=stream_key, array_shape=info['array_shape']))
        
        task = self.perform_action.apply_async(
            args=['CvCameraSharedMemoryService', data_model.model_dump()], eta=execution_time)
        
        return {'task_id': task.id}

########################################################
from config import *
if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp(REDIS_URL)
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,
                                             MONGO_URL,MONGO_DB,CELERY_META,
                                             CELERY_RABBITMQ_BROKER)
else:
    raise ValueError(f'no back end of {APP_BACK_END}')
ServiceOrientedArchitecture.BasicApp=BasicApp

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


celery_app = BasicApp.get_celery_app()
api.include_router(CeleryTask(BasicApp,celery_app).router, prefix="", tags=["fibonacci"])
    