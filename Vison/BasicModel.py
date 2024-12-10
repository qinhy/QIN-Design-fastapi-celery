

from typing import Any
from uuid import uuid4
import cv2
import numpy as np
from pydantic import Field

try:
    from ..Task.Basic import CommonStreamIO, NumpyUInt8SharedMemoryIO
except Exception as e:
    from Task.Basic import CommonStreamIO, NumpyUInt8SharedMemoryIO


class VideoStreamReader(CommonStreamIO.StreamReader):

    @staticmethod
    def isFile(p): return not str(p).isdecimal()

    @staticmethod
    def isBitFlowCamera(p): return 'bitflow' in str(p).lower()
    
    class Base(CommonStreamIO.Base):
        def __init__(self, video_src=0, fps=30.0, width=800, height=600):
            self.video_src = video_src
            self.cam = cv2.VideoCapture(self.video_src)
            self.cam.set(cv2.CAP_PROP_FPS, fps)
            self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            self.fps = self.cam.get(cv2.CAP_PROP_FPS)
            self.width = self.cam.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.height = self.cam.get(cv2.CAP_PROP_FRAME_HEIGHT)
            image, _ = self.read()
            self.shape = image.shape

        def read(self):
            ret_val, img = self.cam.read()
            if not ret_val:
                raise StopIteration()
            return img, {}

        def close(self):
            del self.cam

    class Camera(Base):
        def read(self):
            image, _ = super().read()
            return cv2.flip(image, 1), {}

    class File(Base):
        def read(self):
            return super().read(), {}

    class BitFlowCamera(Base):
        
        def __init__(self, video_src='bitflow-0', fps=30.0, width=800, height=600):
            self.video_src = video_src
            self.fps = fps
            self.width = width # TODO: width
            self.height = height # TODO: height
                        
            import platform
            if(platform.system() == 'Windows'):
                import sys
                import msvcrt
                if (sys.version_info.major >= 3 and sys.version_info.minor >= 8):
                    import os
                    #Following lines specifying, the location of DLLs, are required for Python Versions 3.8 and greater
                    os.add_dll_directory("C:\BitFlow SDK 6.6\Bin64")
                    os.add_dll_directory("C:\Program Files\CameraLink\Serial")

            import BFModule.BufferAcquisition as Buf
            self.Buf = Buf
            self.CirAq = None

            numBuffers = 10
            self.CirAq = Buf.clsCircularAcquisition(Buf.ErrorMode.ErIgnore)

            if '-' in str(self.video_src):
                channel = int(str(self.video_src).split('-')[1])
            else:
                channel = 0

            self.CirAq.Open(channel)

            self.BufArray = self.CirAq.BufferSetup(numBuffers)
            
            self.CirAq.AqSetup(Buf.SetupOptions.setupDefault)
            
            self.CirAq.AqControl(Buf.AcqCommands.Start, Buf.AcqControlOptions.Wait)

        def fast_bayer_to_bgr(self,image):
            h, w = image.shape
            bgr = np.zeros((h, w, 3), dtype=image.dtype)

            # Extract channels (simple bilinear interpolation)
            bgr[1::2, 0::2, 0] = image[1::2, 0::2]  # Blue
            bgr[0::2, 1::2, 2] = image[0::2, 1::2]  # Red
            bgr[::2, ::2, 1] = image[::2, ::2]  # Green on even rows
            bgr[1::2, 1::2, 1] = image[1::2, 1::2]  # Green on odd rows

            # Optional: Simple smoothing for edges (optional for better quality)
            # bgr[:, :, 1] = cv2.blur(bgr[:, :, 1], (3, 3))  # Smooth green
            return bgr

        def bayer2bgr(self,bayer_image):    
            bgr_image = cv2.cvtColor(bayer_image.astype(np.uint8), cv2.COLOR_BayerBG2BGR)

            avg_r = np.mean(bgr_image[:, :, 2])
            avg_g = np.mean(bgr_image[:, :, 1])
            avg_b = np.mean(bgr_image[:, :, 0])

            bgr_image[:, :, 2] = np.clip(bgr_image[:, :, 2] * (avg_g / avg_r), 0, 255)
            bgr_image[:, :, 0] = np.clip(bgr_image[:, :, 0] * (avg_g / avg_b), 0, 255)

            bgr_image = bgr_image.astype(np.uint8)
            return bgr_image
        
        def to8bit(self,frame):
            frame = (frame >> 2).astype(np.uint8)
            return frame
            # frame = self.bayer2bgr(frame)

        def read(self):
            if(self.CirAq.GetAcqStatus().Start == True):
                curBuf = self.CirAq.WaitForFrame(100)
                frame = self.BufArray[curBuf.BufferNumber]
                return frame, {}
            return None, {}

        def close(self):
            self.CirAq.AqCleanup()
            self.CirAq.BufferCleanup()
            self.CirAq.Close()


    @staticmethod
    def reader(video_src=0, fps=30.0, width=800, height=600):
        if not VideoStreamReader.isFile(video_src):
            return VideoStreamReader.Camera(int(video_src), fps, width, height)
        if VideoStreamReader.isBitFlowCamera(video_src):
            return VideoStreamReader.BitFlowCamera(video_src, fps, width, height)
        return VideoStreamReader.File(video_src, fps, width, height)

class NumpyUInt8SharedMemoryStreamIO(NumpyUInt8SharedMemoryIO,CommonStreamIO):
    class Base(NumpyUInt8SharedMemoryIO.Base,CommonStreamIO.Base):
        def get_steam_info(self)->dict:
            return self.model_dump()            
        def set_steam_info(self,data):
            pass        
    class StreamReader(NumpyUInt8SharedMemoryIO.Reader, CommonStreamIO.StreamReader, Base):
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryStreamIO.StreamReader:{uuid4()}")
        def read(self,copy=True)->tuple[Any,dict]:
            return super().read(copy),{}
    class StreamWriter(NumpyUInt8SharedMemoryIO.Writer, CommonStreamIO.StreamWriter, Base):
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryStreamIO.StreamWriter:{uuid4()}")
        def write(self, data: np.ndarray, metadata={}):
            return super().write(data),{}
        
    @staticmethod
    def reader(stream_key: str, array_shape: tuple):
        shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
        shm_name = stream_key.replace(':','_')
        return NumpyUInt8SharedMemoryStreamIO.StreamReader(
            shm_name=shm_name, create=False, stream_key=stream_key,
            array_shape=array_shape,shm_size=shm_size).build_buffer()
    
    @staticmethod
    def writer(stream_key: str, array_shape: tuple):
        shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
        shm_name = stream_key.replace(':','_')
        return NumpyUInt8SharedMemoryStreamIO.StreamWriter(
            shm_name=shm_name, create=True, stream_key=stream_key,
            array_shape=array_shape,shm_size=shm_size).build_buffer()
