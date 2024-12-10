from typing import Any
import cv2
import numpy as np
import threading
import uuid
import os
import shutil
from pydantic import BaseModel, Field

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
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryStreamIO.StreamReader:{uuid.uuid4()}")
        def read(self,copy=True)->tuple[Any,dict]:
            return super().read(copy),{}
    class StreamWriter(NumpyUInt8SharedMemoryIO.Writer, CommonStreamIO.StreamWriter, Base):
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryStreamIO.StreamWriter:{uuid.uuid4()}")
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

class NumpyDualBufferDiskBackedQueue(BaseModel):
    image_shape: tuple[int, ...]
    buffer_capacity: int
    dtype: str = 'uint8'
    is_init:bool = False
    base_dirs: list[str] = Field(default_factory=lambda: ["D:/data","C:/data"])

    active_buffer:str = 'A'  # start writing to buffer A
    write_index:int = 0
    total_images_written:int = 0
    total_images_read:int = 0
    next_buffer_id_to_save:int = 0  # increments every time we save a full buffer
    next_buffer_id_to_overwrite:int = 0  # track how many buffers have been overwritten
    storage_dirs:list = []
    remaining_space:list = []  # in bytes
    current_storage_index:int = 0  # Start with the first storage directory
    buffers_to_save:list = []

    _stop_event: threading.Event = None
    _save_thread: threading.Thread = None
    _lock: threading.Lock = None
    _buffer_full_condition: threading.Condition = None
    _buffer_a:Any = None
    _buffer_b:Any = None

    def init(self):
        dtype = np.__dict__[self.dtype]

        # Pre-allocate the two buffers
        self._buffer_a = np.zeros((self.buffer_capacity,) + self.image_shape, dtype=dtype)
        self._buffer_b = np.zeros((self.buffer_capacity,) + self.image_shape, dtype=dtype)

        # State variables
        self.active_buffer = 'A'  # start writing to buffer A
        self.write_index = 0
        self.total_images_written = 0
        self.total_images_read = 0
        self.next_buffer_id_to_save = 0  # increments every time we save a full buffer
        self.next_buffer_id_to_overwrite = 0  # track how many buffers have been overwritten

        # Locks and conditions
        self._lock = threading.Lock()
        self._buffer_full_condition = threading.Condition(self._lock)

        # Setup directories and capacities
        self.storage_dirs = []
        self.remaining_space = []  # in bytes

        for base_dir in self.base_dirs:
            uuid_dir = os.path.join(base_dir, str(uuid.uuid4()))
            os.makedirs(uuid_dir, exist_ok=True)
            self.storage_dirs.append(uuid_dir)
            self.remaining_space.append(self._calculate_free_space(uuid_dir))

        self.current_storage_index = 0  # Start with the first storage directory

        # Buffers pending save
        self.buffers_to_save = []

        # Event for stopping the thread
        self._stop_event = threading.Event()

        self._save_thread = threading.Thread(target=self.disk_saver_thread, daemon=True)
        self._save_thread.start()
        self.is_init = True
        return self

    def push(self, image: np.ndarray):
        if not self.is_init:
            raise ValueError("Class not init.")
        with self._lock:
            if image.shape != self.image_shape:
                raise ValueError("Image shape does not match the buffer's image shape.")

            # Check if both buffers are full and not saved
            if len(self.buffers_to_save) >= 2:
                raise RuntimeError("Both buffers are full and not yet saved. Cannot push more data.")

            # Write to the active buffer
            if self.active_buffer == 'A':
                self._buffer_a[self.write_index] = image
            else:
                self._buffer_b[self.write_index] = image

            self.write_index += 1
            self.total_images_written += 1

            # Check if the active buffer is now full
            if self.write_index == self.buffer_capacity:
                full_buffer = self.active_buffer

                # Switch active buffer
                if self.active_buffer == 'A':
                    self.active_buffer = 'B'
                else:
                    self.active_buffer = 'A'
                self.write_index = 0

                # Queue buffer for saving
                self.buffers_to_save.append((full_buffer, self.next_buffer_id_to_save))
                self.next_buffer_id_to_save += 1
                self._buffer_full_condition.notify()

    def _calculate_free_space(self, path):
        """Calculate free space at the specified path in bytes."""
        usage = shutil.disk_usage(path)
        return usage.free  # Returns the free space in bytes

    def disk_saver_thread(self):
        while not self._stop_event.is_set():
            with self._buffer_full_condition:
                while not self.buffers_to_save and not self._stop_event.is_set():
                    self._buffer_full_condition.wait()

                if not self.buffers_to_save:
                    # Stop event was set, and there are no buffers to save
                    break

                buffer_to_save, buffer_id = self.buffers_to_save.pop(0)

            # Copy the buffer out (not holding lock to avoid blocking)
            if buffer_to_save == 'A':
                buffer_data = self._buffer_a.copy()
                self._buffer_a[:] = 0
            else:
                buffer_data = self._buffer_b.copy()
                self._buffer_b[:] = 0

            while True:
                # Check the remaining space in the current storage directory
                current_dir = self.storage_dirs[self.current_storage_index]
                required_space = buffer_data.nbytes

                if self.remaining_space[self.current_storage_index] >= required_space:
                    # Save the buffer to the current directory
                    filename = os.path.join(current_dir, f"buffer_{buffer_id}.npy")
                    np.save(filename, buffer_data)

                    # Update remaining space
                    self.remaining_space[self.current_storage_index] -= required_space
                    break
                else:
                    # Switch to the next storage directory
                    self.current_storage_index += 1
                    if self.current_storage_index >= len(self.storage_dirs):
                        raise RuntimeError("All storage directories are full. Cannot save more data.")

    def pop(self):
        with self._lock:
            if self.total_images_read >= self.total_images_written:
                # No images available
                return None

            global_read_index = self.total_images_read
            self.total_images_read += 1

        buffer_id = global_read_index // self.buffer_capacity
        index_in_buffer = global_read_index % self.buffer_capacity

        with self._lock:
            current_buffer_id = (self.next_buffer_id_to_save - 1)

            if buffer_id == self.next_buffer_id_to_save: 
                if self.active_buffer == 'A':
                    img = self._buffer_a[index_in_buffer].copy()
                else:
                    img = self._buffer_b[index_in_buffer].copy()
                return img
            
        pwd = self.storage_dirs[self.current_storage_index]
        if index_in_buffer==0 and os.path.exists(os.path.join(pwd, f"buffer_{buffer_id-1}.npy")):
            os.remove(os.path.join(pwd, f"buffer_{buffer_id-1}.npy"))

        filename = os.path.join(pwd, f"buffer_{buffer_id}.npy")
        buffer_data = np.load(filename, mmap_mode='r')
        img = buffer_data[index_in_buffer].copy()
        return img

    def close(self):
        # Signal the thread to stop
        self._stop_event.set()
        with self._buffer_full_condition:
            self._buffer_full_condition.notify_all()
        self._save_thread.join()

    def __del__(self):
        self.close()
        for dir_path in self.storage_dirs:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
