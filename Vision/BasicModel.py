import datetime
import json
from multiprocessing import shared_memory
from typing import Any
from zoneinfo import ZoneInfo
import cv2
import numpy as np
import threading
import uuid
import os
import shutil
from pydantic import BaseModel, ConfigDict, Field

try:
    from ..Task.Basic import CommonStreamIO, NumpyUInt8SharedMemoryIO
except Exception as e:
    from Task.Basic import CommonStreamIO, NumpyUInt8SharedMemoryIO


class VideoStreamReader:

    @staticmethod
    def isFile(p): return not str(p).isdecimal()

    @staticmethod
    def isBitFlowCamera(p): return 'bitflow' in str(p).lower()
    
    class Base(CommonStreamIO.StreamReader):
        id: str= Field(default_factory=lambda:f"VideoStreamReader.Base:{uuid.uuid4()}")
        video_src:int=0
        stream_key: str = 'VideoStream'
        fps:float=30.0
        width:int=800
        height:int=600
        shape:tuple=(600,800)
        _cam:Any = None # cv2.VideoCapture
        _is_init:bool = False

        def init(self):
            self.stream_key += f':{self.video_src}'
            self._cam:cv2.VideoCapture = cv2.VideoCapture(self.video_src)
            self._cam.set(cv2.CAP_PROP_FPS, self.fps)
            self._cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            self.fps = self._cam.get(cv2.CAP_PROP_FPS)
            self.width = self._cam.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.height = self._cam.get(cv2.CAP_PROP_FRAME_HEIGHT)
            ret_val, image = self._cam.read()
            self.shape = image.shape
            self.width = self.shape[1]
            self.height = self.shape[0]
            self._is_init = True
            return self

        def read(self):
            if not self._is_init:
                self.init()

            ret_val, img = self._cam.read()
            if not ret_val:
                raise StopIteration()
            return img, {}

        def close(self):
            del self._cam

    class Camera(Base):
        id: str= Field(default_factory=lambda:f"VideoStreamReader.Camera:{uuid.uuid4()}")
        stream_key: str = 'CameraStream'
        def read(self):
            image, _ = super().read()
            return cv2.flip(image, 1), {}

    class File(Base):
        id: str= Field(default_factory=lambda:f"VideoStreamReader.File:{uuid.uuid4()}")
        stream_key: str = 'FileStream'
        def read(self):
            return super().read(), {}

    try:
        import BFModule.BufferAcquisition as Buf
        class BitFlowCamera(Base):
            id: str= Field(default_factory=lambda:f"VideoStreamReader.BitFlowCamera:{uuid.uuid4()}")
            stream_key: str = 'BitFlowCameraStream'
            
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
                channel = 0
                numBuffers = 10
                self.CirAq = Buf.clsCircularAcquisition(Buf.ErrorMode.ErIgnore)

                if '-' in str(self.video_src):
                    channel = int(str(self.video_src).split('-')[1])

                self.CirAq.Open(channel)
                self.BufArray = self.CirAq.BufferSetup(numBuffers)
                self.CirAq.AqSetup(Buf.SetupOptions.setupDefault)
                self.CirAq.AqControl(Buf.AcqCommands.Start, Buf.AcqControlOptions.Wait)

            def bayer2bgr(self,bayer_image):    
                return cv2.cvtColor(bayer_image.astype(np.uint8), cv2.COLOR_BayerBG2BGR)
            
            def auto_white_balance(self):

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

    except Exception as e:
        print('not BitFlow Camera support')

    @staticmethod
    def reader(video_src=0, fps=30.0, width=800, height=600):
        if not VideoStreamReader.isFile(video_src):
            return VideoStreamReader.Camera(video_src=int(video_src), fps=fps,
                                            width=width, height=height)
        if VideoStreamReader.isBitFlowCamera(video_src):
            return VideoStreamReader.BitFlowCamera(video_src, fps, width, height)
        return VideoStreamReader.File(video_src, fps, width, height)

class NumpyUInt8SharedMemoryStreamIO(NumpyUInt8SharedMemoryIO,CommonStreamIO):
    class Base(NumpyUInt8SharedMemoryIO.Base,CommonStreamIO.Base):
        def get_steam_info(self)->dict:
            return self.model_dump()
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
    array_shape: tuple[int, ...]
    buffer_capacity: int
    dtype: str = 'uint8'
    is_init:bool = False
    base_dirs: list[str] = Field(default_factory=lambda: ["D:/data","C:/data"])

    active_buffer:str = True
    write_index:int = 0
    total_arrays_written:int = 0
    total_arrays_popped:int = 0
    next_buffer_id_to_save:int = 0
    next_buffer_id_to_overwrite:int = 0
    storage_dirs:list = []
    remaining_space:list = []
    current_storage_index:int = 0
    buffers_to_save:list = []

    _stop_event: threading.Event = None
    _save_thread: threading.Thread = None
    _saving_lock: threading.Lock = None
    _buffer_lock: threading.Lock = None
    _buffer_full_condition: threading.Condition = None
    _buffers:dict[Any] = None

    def init(self):
        dtype = np.__dict__[self.dtype]
        
        # Pre-allocate the two buffers
        size = (self.buffer_capacity,) + self.array_shape
        self._buffers = {True:np.zeros(size, dtype=dtype),
                        False:np.zeros(size, dtype=dtype)}
        # State variables
        self.active_buffer = True  # start writing to buffer A
        self.write_index = 0
        self.total_arrays_written = 0
        self.total_arrays_popped = 0
        self.next_buffer_id_to_save = 0  # increments every time we save a full buffer
        # track how many buffers have been overwritten
        self.next_buffer_id_to_overwrite = 0

        # Locks and conditions
        self._saving_lock = threading.Lock()
        self._buffer_lock = threading.Lock()
        self._buffer_full_condition = threading.Condition(self._buffer_lock)

        # Setup directories and capacities
        self.storage_dirs = []
        self.remaining_space = []  # in bytes

        for base_dir in self.base_dirs:
            uuid_dir = os.path.join(base_dir, str(uuid.uuid4()))
            os.makedirs(uuid_dir, exist_ok=True)
            self.storage_dirs.append(uuid_dir)
            self.remaining_space.append(shutil.disk_usage(uuid_dir).free)
        # Start with the first storage directory
        self.current_storage_index = 0 
        # Buffers pending save
        self.buffers_to_save = []
        # Event for stopping the thread
        self._stop_event = threading.Event()

        self._save_thread = threading.Thread(target=self.disk_saver_thread, daemon=True)
        self._save_thread.start()
        self.is_init = True
        return self

    def push(self, in_arr: np.ndarray):
        if not self.is_init:
            raise ValueError("Class not init.")
        with self._buffer_lock:
            if in_arr.shape != self.array_shape:
                raise ValueError("input shape not match buffer shape.")

            # Check if both buffers are full and not saved
            if len(self.buffers_to_save) >= 2:
                raise RuntimeError("buffers are full cannot push data.")

            # Write to the active buffer
            self._buffers[self.active_buffer][self.write_index] = in_arr

            self.write_index += 1
            self.total_arrays_written += 1

            # Check if the active buffer is now full
            if self.write_index == self.buffer_capacity:
                full_buffer = self.active_buffer

                # Switch active buffer
                self.active_buffer = not self.active_buffer
                self.write_index = 0

                # Queue buffer for saving
                self.buffers_to_save.append((full_buffer, self.next_buffer_id_to_save))
                self.next_buffer_id_to_save += 1
                self._buffer_full_condition.notify()

    def disk_saver_thread(self):
        while not self._stop_event.is_set():
            with self._buffer_full_condition:
                while not self.buffers_to_save and not self._stop_event.is_set():
                    self._buffer_full_condition.wait()

                if not self.buffers_to_save: break

                buffer_to_save, buffer_id = self.buffers_to_save.pop(0)

            # Copy the buffer out
            with self._saving_lock:

                buffer_data = self._buffers[buffer_to_save].copy()
                self._buffers[buffer_to_save][:] = 0

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
                            raise RuntimeError("All storage are full. Cannot save more data.")

    def pop(self):
        if self.total_arrays_popped >= self.total_arrays_written:return None

        buffer_id = self.total_arrays_popped // self.buffer_capacity
        index_in_buffer = self.total_arrays_popped % self.buffer_capacity

        if buffer_id == self.next_buffer_id_to_save:
            with self._buffer_lock:
                img = self._buffers[self.active_buffer][index_in_buffer].copy()
                
                self.total_arrays_popped += 1
                return img

        pwd = self.storage_dirs[self.current_storage_index]
        if index_in_buffer == 0 and os.path.exists(os.path.join(pwd, f"buffer_{buffer_id-1}.npy")):
            os.remove(os.path.join(pwd, f"buffer_{buffer_id-1}.npy"))

        with self._saving_lock:
            buffer_data = np.load(os.path.join(pwd, f"buffer_{buffer_id}.npy"), mmap_mode='r')
            img = buffer_data[index_in_buffer].copy()

        self.total_arrays_popped += 1
        return img

    def close(self):
        self._stop_event.set()
        with self._buffer_full_condition:
            self._buffer_full_condition.notify_all()
        self._save_thread.join()

    def __del__(self):
        self.close()
        for dir_path in self.storage_dirs:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)

# ##################### IO 
# def now_utc():
#     return datetime.datetime.now().replace(tzinfo=ZoneInfo("UTC"))

# class AbstractObj(Model4Basic.AbstractObj):
#     auto_del: bool = True # auto delete when removed from memory 
   
# class CommonIO:
#     class Base(AbstractObj):            
#         def write(self,data):
#             raise ValueError("[CommonIO.Reader]: This is Reader can not write")
#         def read(self):
#             raise ValueError("[CommonIO.Writer]: This is Writer can not read") 
#         def close(self):
#             raise ValueError("[CommonIO.Base]: 'close' not implemented")
#     class Reader(Base):
#         def read(self)->Any:
#             raise ValueError("[CommonIO.Reader]: 'read' not implemented")
#     class Writer(Base):
#         def write(self,data):
#             raise ValueError("[CommonIO.Writer]: 'write' not implemented")

# class GeneralSharedMemoryIO(CommonIO):
#     class Base(CommonIO.Base):
#         shm_name: str = Field(..., description="The name of the shared memory segment")
#         create: bool = Field(default=False, description="Flag indicating whether to create or attach to shared memory")
#         shm_size: int = Field(..., description="The size of the shared memory segment in bytes")

#         _shm:shared_memory.SharedMemory
#         _buffer:memoryview

#         def build_buffer(self):
#             # Initialize shared memory with the validated size and sanitized name
#             self._shm = shared_memory.SharedMemory(name=self.shm_name, create=self.create, size=self.shm_size)
#             self._buffer = memoryview(self._shm.buf)  # View into the shared memory buffer
#             return self
                
#         def close(self):
#             """Detach from the shared memory."""
#             # Release the memoryview before closing the shared memory
#             if hasattr(self,'_buffer') and self._buffer is not None:
#                 self._buffer.release()
#                 del self._buffer
#             if hasattr(self,'_shm'):
#                 self._shm.close()  # Detach from shared memory

#         def __del__(self):            
#             self.__obj_del__()
#             self.close()

#     class Reader(CommonIO.Reader, Base):
#         id: str= Field(default_factory=lambda:f"GeneralSharedMemoryIO.Reader:{uuid.uuid4()}")
#         def read(self, size: int = None) -> bytes:
#             """Read binary data from shared memory."""
#             if size is None or size > self.shm_size:
#                 size = self.shm_size  # Read the whole buffer by default
#             return bytes(self._buffer[:size])  # Convert memoryview to bytes
  
#     class Writer(CommonIO.Writer, Base):
#         id: str= Field(default_factory=lambda:f"GeneralSharedMemoryIO.Writer:{uuid.uuid4()}")
#         def write(self, data: bytes):
#             """Write binary data to shared memory."""
#             if len(data) > self.shm_size:
#                 raise ValueError(f"Data size exceeds shared memory size ({len(data)} > {self.shm_size})")
            
#             # Write the binary data to shared memory
#             self._buffer[:len(data)] = data
        
#         def close(self):
#             super().close()
#             if hasattr(self,'_shm'):
#                 self._shm.unlink()  # Unlink (remove) the shared memory segment after writing
    
#     @staticmethod
#     def reader(shm_name: str, shm_size: int):
#         return GeneralSharedMemoryIO.Reader(shm_name=shm_name, create=False, shm_size=shm_size).build_buffer()
    
#     @staticmethod
#     def writer(shm_name: str, shm_size: int):
#         return GeneralSharedMemoryIO.Writer(shm_name=shm_name, create=True, shm_size=shm_size).build_buffer()
   
# class NumpyUInt8SharedMemoryIO(GeneralSharedMemoryIO):
#     class Base(GeneralSharedMemoryIO.Base):
#         array_shape: tuple = Field(..., description="Shape of the NumPy array to store in shared memory")
#         _dtype: np.dtype = np.uint8
#         _shared_array: np.ndarray
#         def __init__(self, **kwargs):
#             kwargs['shm_size'] = np.prod(kwargs['array_shape']) * np.dtype(np.uint8).itemsize
#             super().__init__(**kwargs)
            
#         def build_buffer(self):
#             super().build_buffer()
#             self._shared_array = np.ndarray(self.array_shape, dtype=self._dtype, buffer=self._buffer)
#             return self

#     class Reader(GeneralSharedMemoryIO.Reader, Base):
#         id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryIO.Reader:{uuid.uuid4()}")
#         def read(self,copy=True) -> np.ndarray:
#             return self._shared_array.copy() if copy else self._shared_array
#             # binary_data = super().read(size=self.shm_size)
#             # return np.frombuffer(binary_data, dtype=self._dtype).reshape(self.array_shape)
    
#     class Writer(GeneralSharedMemoryIO.Writer, Base):
#         id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryIO.Writer:{uuid.uuid4()}")
#         def write(self, data: np.ndarray):
#             if data.shape != self.array_shape:
#                 raise ValueError(f"Data shape {data.shape} does not match expected shape {self.array_shape}.")
#             if data.dtype != self._dtype:
#                 raise ValueError(f"Data type {data.dtype} does not match expected type {self._dtype}.")            
#             self._shared_array[:] = data[:]
#             # super().write(data.tobytes())

#     @staticmethod
#     def reader(shm_name: str, array_shape: tuple):
#         shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
#         return NumpyUInt8SharedMemoryIO.Reader(shm_size=shm_size,
#                                     shm_name=shm_name, create=False, array_shape=array_shape).build_buffer()
    
#     @staticmethod
#     def writer(shm_name: str, array_shape: tuple):
#         shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
#         return NumpyUInt8SharedMemoryIO.Writer(shm_size=shm_size,
#                                     shm_name=shm_name, create=True, array_shape=array_shape).build_buffer()

# class NumpyUInt8SharedMemoryQueue:
#     def __init__(self, shm_prefix: str, num_blocks: int, block_size: int, item_shape: tuple):
#         """
#         Create a queue using multiple shared memory blocks.
#         Args:
#             shm_prefix (str): Prefix for shared memory block names.
#             num_blocks (int): Number of blocks in the queue.
#             block_size (int): Maximum number of items per block.
#             item_shape (tuple): Shape of each item in the queue.
#         """
#         self.num_blocks = num_blocks
#         self.block_size = block_size
#         self.item_shape = item_shape
#         self.total_capacity = num_blocks * block_size

#         # Create NumpyUInt8SharedMemoryIO instances for each block
#         self.blocks = [
#             NumpyUInt8SharedMemoryIO.writer(
#                 shm_name=f"{shm_prefix}_block_{i}",
#                 array_shape=(block_size, *item_shape),
#             )
#             for i in range(num_blocks)
#         ]

#         # Metadata
#         self.head = 0  # Global index for dequeue
#         self.tail = 0  # Global index for enqueue

#     def enqueue(self, item: np.ndarray):
#         if item.shape != self.item_shape:
#             raise ValueError(f"Item shape {item.shape} does not match expected shape {self.item_shape}.")

#         # Determine the block and position within the block
#         block_idx = self.tail // self.block_size
#         pos_in_block = self.tail % self.block_size

#         # Write item to the block
#         self.blocks[block_idx]._shared_array[pos_in_block] = item

#         # Update the tail index
#         self.tail = (self.tail + 1) % self.total_capacity

#         # If the queue is full, move the head forward (overwrite old data)
#         if self.tail == self.head:
#             self.head = (self.head + 1) % self.total_capacity

#     def dequeue(self) -> np.ndarray:
#         if self.head == self.tail:
#             raise ValueError("Queue is empty.")

#         # Determine the block and position within the block
#         block_idx = self.head // self.block_size
#         pos_in_block = self.head % self.block_size

#         # Read item from the block
#         item = self.blocks[block_idx]._shared_array[pos_in_block].copy()

#         # Update the head index
#         self.head = (self.head + 1) % self.total_capacity

#         return item

#     def is_empty(self) -> bool:
#         return self.head == self.tail

#     def is_full(self) -> bool:
#         return (self.tail + 1) % self.total_capacity == self.head

#     def current_size(self) -> int:
#         """Returns the current number of items in the queue."""
#         if self.tail >= self.head:
#             return self.tail - self.head
#         return self.total_capacity - (self.head - self.tail)

# ##################### stream IO 
# class CommonStreamIO(CommonIO):
#     class Base(CommonIO.Base):
#         fps:float = 0
#         stream_key: str = 'NULL'
#         is_close: bool = False
        
#         def stream_id(self):
#             return f'streams:{self.stream_key}'

#         def write(self, data, metadata={}):
#             raise ValueError("[CommonStreamIO.Reader]: This is Reader can not write")
        
#         def read(self):
#             raise ValueError("[CommonStreamIO.Writer]: This is Writer can not read") 
        
#         def close(self):
#             raise ValueError("[StreamWriter]: 'close' not implemented")
        
#         def get_steam_info(self)->dict:
#             raise ValueError("[StreamWriter]: 'get_steam_info' not implemented")
            
#         def set_steam_info(self,data):
#             raise ValueError("[StreamWriter]: 'set_steam_info' not implemented")
        
#     class StreamReader(CommonIO.Reader, Base):
#         id: str= Field(default_factory=lambda:f"CommonStreamIO.StreamReader:{uuid.uuid4()}")
#         def read(self)->tuple[Any,dict]:
#             return super().read(),{}
        
#         def __iter__(self):
#             return self

#         def __next__(self):
#             return self.read()        
        
#     class StreamWriter(CommonIO.Writer, Base):
#         id: str= Field(default_factory=lambda:f"CommonStreamIO.StreamWriter:{uuid.uuid4()}")

#         def __init__(self, **kwargs):
#             super().__init__(**kwargs)
#             tmp = self.model_dump_json_dict()
#             tmp['id'] = self.stream_id()
#             ServiceOrientedArchitecture.BasicApp.store().set(self.stream_id(),tmp)
            
#         def write(self, data, metadata={}):
#             raise ValueError("[StreamWriter]: 'write' not implemented")
        
#         def __del__(self):
#             self.__obj_del__()
#             ServiceOrientedArchitecture.BasicApp.store().delete(self.stream_id())

                
                
                
                
                
                
                