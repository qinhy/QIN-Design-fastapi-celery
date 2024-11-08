from multiprocessing import Process
import threading
import time
from typing import Any
import celery
import celery.states
import cv2
import numpy as np
from pydantic import BaseModel
from basic import NumpyUInt8SharedMemoryIO, NumpyUInt8SharedMemoryStreamIO, ServiceOrientedArchitecture, get_tasks_collection


class Fibonacci(ServiceOrientedArchitecture):

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: str = 'fast'
            def is_fast(self):
                return self.mode=='fast'
        class Args(BaseModel):
            n: int = 1
        class Return(BaseModel):
            n: int = -1

        param:Param = Param()
        args:Args
        ret:Return = Return()

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model):
            # Ensure model is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)            
            self.model: Fibonacci.Model = model

        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            return self.calculate()

        def calculate(self):
            n = self.model.args.n
            if n <= 1:
                self.model.ret.n = n
            else:
                if self.model.param.is_fast():
                    a, b = 0, 1
                    for _ in range(2, n + 1):
                        a, b = b, a + b
                    res = b
                else:
                    def fib_r(n):
                        return(fib_r(n-1) + fib_r(n-2))                    
                    res = fib_r(n)
                self.model.ret.n = res
            return self.model

class CvCameraSharedMemoryService:
    class Model(ServiceOrientedArchitecture.Model):        
        class Param(NumpyUInt8SharedMemoryIO.Writer):
            mode:str='write'

            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                if not self.is_write():
                    self.close()
            
            def is_write(self):
                return self.mode=='write'

        class Args(BaseModel):
            camera:int = 0

        class Return(NumpyUInt8SharedMemoryStreamIO.StreamReader):
            def __init__(self, **kwargs):
                kwargs['create'] = False
                super().__init__(**kwargs)

        param:Param = None
        args:Args = Args()
        ret:Return = None
        

        def set_param(self, shm_name="camera_shm", create=True, array_shape=(480, 640), mode = 'write'):
            self.param = CvCameraSharedMemoryService.Model.Param(
                            mode=mode,shm_name=shm_name, create=create, array_shape=array_shape)
            return self

        def set_args(self, camera=0):
            self.args = CvCameraSharedMemoryService.Model.Args(camera=camera)
            return self
        
        @staticmethod
        def build_ret(camera_service_model):
            return CvCameraSharedMemoryService.Model.Return(
                **camera_service_model['param'])
    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model):
            if isinstance(model, dict):
                nones = [k for k,v in model.items() if v is None]
                for i in nones:del model[i]
                model = CvCameraSharedMemoryService.Model(**model)
            self.model: CvCameraSharedMemoryService.Model = model
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            # A shared flag to communicate between threads
            stop_flag = threading.Event()

            # Function to check if the task should be stopped, running in a separate thread
            def check_task_status(task_id):
                collection = get_tasks_collection()
                
                while True:
                    task = collection.find_one({'_id': task_id})
                    if task:
                        break
                    time.sleep(1)

                while not stop_flag.is_set():
                    task = collection.find_one({'_id': task_id})
                    if task['status'] == celery.states.REVOKED:
                        print(f"Task marked as {celery.states.REVOKED}, setting stop flag.")
                        stop_flag.set()
                        break
                    time.sleep(1)  # Delay between checks to reduce load on MongoDB

            # Start the status-checking thread
            status_thread = threading.Thread(target=check_task_status, args=(self.model.task_id,))
            status_thread.start()


            if self.model.param.is_write():
                # Open the camera using OpenCV
                cap = cv2.VideoCapture(self.model.args.camera)
                if not cap.isOpened():
                    raise ValueError(f"Unable to open camera {self.model.args.camera}")
                
                writer = self.model.param  # Shared memory writer
                print("writing")
                while not stop_flag.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        print("Failed to grab frame")
                        continue

                    # Convert the frame to grayscale and resize to match shared memory size
                    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    resized_frame = cv2.resize(gray_frame, (writer.array_shape[1], writer.array_shape[0]))

                    # Write the frame to shared memory
                    writer.write(resized_frame)

                    # Display the frame (optional, for debugging)
                #     cv2.imshow('Shared Memory Camera Frame', resized_frame)
                #     if cv2.waitKey(1) & 0xFF == ord('q'):
                #         break
                    
                # cap.release()
                # cv2.destroyAllWindows()

            else:
                # reading
                reader = self.model.build_ret(self.model.model_dump())
                print("reading")
                while not stop_flag.is_set():
                    # Read the frame from shared memory
                    frame,_ = reader.read()
                    if frame is None:
                        print("No frame read from shared memory.")
                        continue

                    # Display the frame
                    cv2.imshow('Shared Memory Reader Frame', frame)

                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                cv2.destroyAllWindows()
            
            return self.model

if __name__ == "__main__":
    camera_service_model = CvCameraSharedMemoryService.Model(
        ).set_param(shm_name="camera_shm", create=True, array_shape=(480, 640)
        ).set_args(camera=0).model_dump()
    
    print(camera_service_model)    
    # Start the writer process in a separate process

    def camera_writer_process(camera_service_model):
        action = CvCameraSharedMemoryService.Action(camera_service_model)
        action()  # Start capturing and writing to shared memory

    writer_process = Process(target=camera_writer_process,args=(camera_service_model,))
    writer_process.start()

    # Allow the writer some time to initialize and start capturing frames
    time.sleep(2)

    # Start the reader process
    camera_service_model = CvCameraSharedMemoryService.Model(
        ).set_param(mode='read',shm_name="camera_shm", create=False, array_shape=(480, 640)
        ).set_args(camera=0).model_dump()
    action = CvCameraSharedMemoryService.Action(camera_service_model)
    action()

    # Wait for the writer process to finish (if needed)
    writer_process.join()
