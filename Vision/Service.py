import cv2
from pydantic import Field

from Task.Customs import BidirectionalStreamService

from .BasicModel import NumpyUInt8SharedMemoryStreamIO, VideoStreamReader

try:
    from ..Task.Basic import ServiceOrientedArchitecture
except Exception as e:
    from Task.Basic import ServiceOrientedArchitecture

class CvCameraSharedMemoryService(BidirectionalStreamService):
    class Model(BidirectionalStreamService.Model):        
        class Param(BidirectionalStreamService.Model.Param):
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

        class Args(BidirectionalStreamService.Model.Args):
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
        def __init__(self, model):
            if isinstance(model, dict):
                nones = [k for k,v in model.items() if v is None]
                for i in nones:del model[i]
                model = CvCameraSharedMemoryService.Model(**model)
            self.model: CvCameraSharedMemoryService.Model = model
            self.logger = self.model.logger.init(name=f"CvCameraSharedMemoryService:{self.model.task_id}")


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
                    action = BidirectionalStreamService.Action(self.model,frame_processor)
                    action()

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


# def camera_writer_process(camera_service_model):
#     action = CvCameraSharedMemoryService.Action(camera_service_model)
#     action()  # Start capturing and writing to shared memory

# if __name__ == "__main__":
#     from multiprocessing import Process
#     camera_service_model = CvCameraSharedMemoryService.Model(
#         ).set_param(stream_key="camera:0", array_shape=(480, 640)
#         ).set_args(camera=0)
    
#     print(camera_service_model)    
#     # Start the writer process in a separate process

#     writer_process = Process(target=camera_writer_process,args=(camera_service_model.model_dump(),))
#     writer_process.start()

#     # Allow the writer some time to initialize and start capturing frames
#     time.sleep(5)

#     # Start the reader process
#     camera_service_model = CvCameraSharedMemoryService.Model(
#         ).set_param(mode='read',stream_key="camera:0", array_shape=(480, 640))
#     action = CvCameraSharedMemoryService.Action(camera_service_model)
#     action()

#     # Wait for the writer process to finish (if needed)
#     writer_process.join()
