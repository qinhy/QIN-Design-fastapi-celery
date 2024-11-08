
from multiprocessing import shared_memory
import time
from typing import Any
import requests
import celery
import celery.states
import numpy as np
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Constants
rabbitmq_URL = 'localhost:15672'
mongo_URL = 'mongodb://localhost:27017'
mongo_DB = 'tasks'
celery_META = 'celery_taskmeta'
celery_broker = 'amqp://localhost'

def check_rabbitmq_health(url=rabbitmq_URL, user='guest', password='guest') -> bool:
    url = f'http://{rabbitmq_URL}/api/health/checks/alarms'
    try:
        response = requests.get(url, auth=(user, password), timeout=5)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.exceptions.RequestException as e:
        return False

def check_mongodb_health(url=mongo_URL) -> bool:
    try:
        client = MongoClient(url, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        return True
    except ConnectionFailure as e:
        return False

def check_services(rabbitmq_URL=rabbitmq_URL,mongo_URL=mongo_URL) -> bool:
    rabbitmq_health = check_rabbitmq_health(rabbitmq_URL)
    mongodb_health = check_mongodb_health(mongo_URL)
    if rabbitmq_health and mongodb_health:
        return True
    else:
        return False
    
# Function to get a document by task_id
def get_tasks_collection():
    # Reusable MongoDB client setup
    client = MongoClient(mongo_URL)
    db = client.get_database(mongo_DB)
    collection = db.get_collection(celery_META)
    return collection#.find_one({'_id': task_id})

def set_task_started(task_id):
    collection = get_tasks_collection()
    return collection.update_one({'_id': task_id},
                {'$set': {'status': celery.states.STARTED}},upsert=True)

def set_task_revoked(task_id):
    collection = get_tasks_collection()
    # Update the status of the task to 'REVOKED'
    update_result = collection.update_one({'_id': task_id}, {'$set': {'status': 'REVOKED'}})
    if update_result.matched_count > 0:
        res = collection.find_one({'_id': task_id})
    else:
        res = {'error': 'Task not found'}    
    return res


class ServiceOrientedArchitecture:
    class Model(BaseModel):
        task_id:str = 'NO_NEED_INPUT'
        class Param(BaseModel):
            pass
        class Args(BaseModel):
            pass
        class Return(BaseModel):
            pass

        param:Param = Param()
        args:Args = Args()
        ret:Return = Return()
    class Action:
        def __init__(self, model):
            if isinstance(model, dict):
                nones = [k for k,v in model.items() if v is None]
                for i in nones:del model[i]
                model = ServiceOrientedArchitecture.Model(**model)
            self.model: ServiceOrientedArchitecture.Model = model

        def __call__(self, *args, **kwargs):
            set_task_started(self.model.task_id)            
            return self.model

##################### IO 
class CommonIO:
    class Base(BaseModel):            
        def write(self,data):
            raise ValueError("[CommonIO.Reader]: This is Reader can not write")
        def read(self):
            raise ValueError("[CommonIO.Writer]: This is Writer can not read") 
        def close(self):
            raise ValueError("[CommonIO.Base]: 'close' not implemented")
    class Reader(Base):
        def read(self)->Any:
            raise ValueError("[CommonIO.Reader]: 'read' not implemented")
    class Writer(Base):
        def write(self,data):
            raise ValueError("[CommonIO.Writer]: 'write' not implemented")

class GeneralSharedMemoryIO(CommonIO):
    class Base(CommonIO.Base):
        shm_name: str = Field(..., description="The name of the shared memory segment")
        create: bool = Field(default=False, description="Flag indicating whether to create or attach to shared memory")
        shm_size: int = Field(..., description="The size of the shared memory segment in bytes")
        
        _shm:shared_memory.SharedMemory
        _buffer:memoryview

        def __init__(self, **kwargs):
            # Initialize Pydantic BaseModel to validate and set fields
            super().__init__(**kwargs)
            
            # Initialize shared memory with the validated size and sanitized name
            self._shm = shared_memory.SharedMemory(name=self.shm_name, create=self.create, size=self.shm_size)
            self._buffer = memoryview(self._shm.buf)  # View into the shared memory buffer
                
        def close(self):
            """Detach from the shared memory."""
            # Release the memoryview before closing the shared memory
            if hasattr(self,'_buffer') and self._buffer is not None:
                self._buffer.release()
                del self._buffer
            if hasattr(self,'_shm'):
                self._shm.close()  # Detach from shared memory

        def __del__(self):
            self.close()

    class Reader(CommonIO.Reader, Base):
        def read(self, size: int = None) -> bytes:
            """Read binary data from shared memory."""
            if size is None or size > self.shm_size:
                size = self.shm_size  # Read the whole buffer by default
            return bytes(self._buffer[:size])  # Convert memoryview to bytes
  
    class Writer(CommonIO.Writer, Base):
        def write(self, data: bytes):
            """Write binary data to shared memory."""
            if len(data) > self.shm_size:
                raise ValueError(f"Data size exceeds shared memory size ({len(data)} > {self.shm_size})")
            
            # Write the binary data to shared memory
            self._buffer[:len(data)] = data
        
        def close(self):
            super().close()
            if hasattr(self,'_shm'):
                self._shm.unlink()  # Unlink (remove) the shared memory segment after writing
    
    @staticmethod
    def reader(shm_name: str, shm_size: int):
        return GeneralSharedMemoryIO.Reader(shm_name=shm_name, create=False, shm_size=shm_size)
    
    @staticmethod
    def writer(shm_name: str, shm_size: int):
        return GeneralSharedMemoryIO.Writer(shm_name=shm_name, create=True, shm_size=shm_size)
             
class NumpyUInt8SharedMemoryIO(GeneralSharedMemoryIO):
    class Base(GeneralSharedMemoryIO.Base):
        array_shape: tuple = Field(..., description="Shape of the NumPy array to store in shared memory")        
        _dtype: np.dtype = np.uint8        
        def __init__(self, **kwargs):
            kwargs['shm_size'] = np.prod(kwargs['array_shape']) * np.dtype(np.uint8).itemsize
            super().__init__(**kwargs)
        
    class Reader(GeneralSharedMemoryIO.Reader, Base):
        def read(self) -> np.ndarray:
            binary_data = super().read(size=self.shm_size)
            return np.frombuffer(binary_data, dtype=self._dtype).reshape(self.array_shape)
    
    class Writer(GeneralSharedMemoryIO.Writer, Base):
        def write(self, data: np.ndarray):
            if data.shape != self.array_shape:
                raise ValueError(f"Data shape {data.shape} does not match expected shape {self.array_shape}.")
            if data.dtype != self._dtype:
                raise ValueError(f"Data type {data.dtype} does not match expected type {self._dtype}.")
            super().write(data.tobytes())

    @staticmethod
    def reader(shm_name: str, array_shape: tuple):
        return NumpyUInt8SharedMemoryIO.Reader(shm_name=shm_name, create=False, array_shape=array_shape,shm_size=1)
    
    @staticmethod
    def writer(shm_name: str, array_shape: tuple):
        return NumpyUInt8SharedMemoryIO.Writer(shm_name=shm_name, create=True, array_shape=array_shape,shm_size=1)

##################### stream IO 
class CommonStreamIO(CommonIO):
    class Base(CommonIO.Base):
        stream_key: str = 'NULL'
        is_close: bool = False

        def write(self, data, metadata={}):
            raise ValueError("[CommonStreamIO.Reader]: This is Reader can not write")
        
        def read(self):
            raise ValueError("[CommonStreamIO.Writer]: This is Writer can not read") 
        
        def close(self):
            raise ValueError("[StreamWriter]: 'close' not implemented")
        
        def get_steam_info(self)->dict:
            raise ValueError("[StreamWriter]: 'get_steam_info' not implemented")
            
        def set_steam_info(self,data):
            raise ValueError("[StreamWriter]: 'set_steam_info' not implemented")
    class StreamReader(CommonIO.Reader, Base):
        def read(self)->tuple[Any,dict]:
            return super().read(),{}
        
        def __iter__(self):
            return self

        def __next__(self):
            return self.read()        
        
    class StreamWriter(CommonIO.Writer, Base):
        def write(self, data, metadata={}):
            raise ValueError("[StreamWriter]: 'write' not implemented")

class NumpyUInt8SharedMemoryStreamIO(NumpyUInt8SharedMemoryIO,CommonStreamIO):
    class Base(NumpyUInt8SharedMemoryIO.Base,CommonStreamIO.Base):
        def get_steam_info(self)->dict:
            return self.model_dump()            
        def set_steam_info(self,data):
            pass        
    class StreamReader(NumpyUInt8SharedMemoryIO.Reader, CommonStreamIO.StreamReader, Base):
        def read(self)->tuple[Any,dict]:
            return super().read(),{}
    class StreamWriter(NumpyUInt8SharedMemoryIO.Writer, CommonStreamIO.StreamWriter, Base):        
        def write(self, data: np.ndarray, metadata={}):
            return super().write(data),{}
        
    @staticmethod
    def reader(shm_name: str, array_shape: tuple):
        return NumpyUInt8SharedMemoryStreamIO.StreamReader(shm_name=shm_name, create=False, array_shape=array_shape,shm_size=1)
    
    @staticmethod
    def writer(shm_name: str, array_shape: tuple):
        return NumpyUInt8SharedMemoryStreamIO.StreamWriter(shm_name=shm_name, create=True, array_shape=array_shape,shm_size=1)

class BidirectionalStream:
    class Bidirectional:
        def __init__(self, frame_processor=lambda i,frame,frame_metadata:(frame,frame_metadata),
                        stream_reader:CommonStreamIO.StreamReader=None,stream_writer:CommonStreamIO.StreamWriter=None):
            
            self.frame_processor = frame_processor
            self.stream_writer = stream_writer
            self.stream_reader = stream_reader
            self.streams:list[CommonStreamIO.Base] = [self.stream_reader, self.stream_writer]
            
        def run(self):
            for s in self.streams:
                if s is None:raise ValueError('stream is None')
                
            res = {'msg':''}
            try:
                for frame_count,(image,frame_metadata) in enumerate(self.stream_reader):
                    if frame_count%100==0:
                        start_time = time.time()
                    else:
                        elapsed_time = time.time() - start_time + 1e-5
                        frame_metadata['fps'] = fps = (frame_count%100) / elapsed_time
                    

                    image,frame_processor_metadata = self.frame_processor(frame_count,image,frame_metadata)
                    frame_metadata.update(frame_processor_metadata)
                    self.stream_writer.write(image,frame_metadata)

                    if frame_count%1000==100:
                        metadata = self.stream_writer.get_steam_info()
                        if metadata.get('is_close',False):
                            for s in self.streams:
                                s.close()
                            break
                        metadata['fps'] = fps
                        self.stream_writer.set_steam_info(metadata)

            except Exception as e:
                    res['error'] = str(e)
                    print(res)
            finally:
                for s in self.streams:
                    s.close()
                return res

    class WriteOnly(Bidirectional):
        def __init__(self, frame_processor=lambda i,frame,frame_metadata:(frame,frame_metadata),
                    stream_writer:CommonStreamIO.StreamWriter=None):
            self.frame_processor = frame_processor
            self.stream_writer = stream_writer
            self.streams:list[CommonStreamIO.Base] = [self.stream_writer]
            
            def mock_stream():
                while True: yield None,{}
            self.stream_reader = mock_stream()

    class ReadOnly(Bidirectional):
        def __init__(self, frame_processor=lambda i,frame,frame_metadata:(frame,frame_metadata),
                    stream_reader:CommonStreamIO.StreamReader=None):
            
            self.frame_processor = frame_processor
            self.stream_reader = stream_reader

        def run(self):
            if self.stream_reader is None:raise ValueError('stream_reader is None')
            res = {'msg':''}
            try:
                for frame_count,(image,frame_metadata) in enumerate(self.stream_reader):
                    if frame_count%100==0:
                        start_time = time.time()
                    else:
                        elapsed_time = time.time() - start_time + 1e-5
                        frame_metadata['fps'] = fps = (frame_count%100) / elapsed_time

                    image,frame_metadata = self.frame_processor(frame_count,image,frame_metadata)

                    if frame_count%1000==100:
                        if self.stream_reader.get_steam_info().get('is_close',False):
                            self.stream_reader.close()
                            break
                        
            except Exception as e:
                    res['error'] = str(e)
                    print(res)
            finally:
                self.stream_reader.close()
                res['msg'] += f'\nstream {self.stream_reader.stream_key} reader.close()'
                return res

    @staticmethod
    def bidirectional(frame_processor,stream_reader:CommonStreamIO.Reader,stream_writer:CommonStreamIO.Writer):
        return BidirectionalStream.Bidirectional(frame_processor,stream_reader,stream_writer)

    @staticmethod
    def readOnly(frame_processor,stream_reader:CommonStreamIO.Reader):
        return BidirectionalStream.ReadOnly(frame_processor,stream_reader)

    @staticmethod
    def writeOnly(frame_processor,stream_writer:CommonStreamIO.Writer):
        return BidirectionalStream.WriteOnly(frame_processor,stream_writer)



try:
    import redis   

    class RedisIO(CommonIO):
        class Base(CommonIO.Base):
            key: str

            redis_host: str = Field(default='localhost', description="The Redis server hostname")
            redis_port: int = Field(default=6379, description="The Redis server port")
            redis_db: int = Field(default=0, description="The Redis database index")
            _redis_client:redis.Redis = None
            
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._redis_client = redis.Redis(host=self.redis_host, port=self.redis_port, db=self.redis_db)
            
            def close(self):
                del self._redis_client
                
        class Reader(CommonIO.Reader, Base):            
            def read(self):
                data = self._redis_client.get(self.key)
                if data is None:
                    raise ValueError(f"No data found for key: {self.key}")
                return data  # Returning the raw binary data stored under the key
        
        class Writer(CommonIO.Writer, Base):
            def write(self, data: bytes):
                if not isinstance(data, bytes):
                    raise ValueError("Data must be in binary format (bytes)")
                self._redis_client.set(self.key, data)  # Store binary data under the given key

        @staticmethod
        def reader(key: str, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0):
            return RedisIO.Reader(key=key, redis_host=redis_host, redis_port=redis_port, redis_db=redis_db)

        @staticmethod
        def writer(key: str, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 0):
            return RedisIO.Writer(key=key, redis_host=redis_host, redis_port=redis_port, redis_db=redis_db)

except Exception as e:
    print('No redis support')
except Exception as e:
    print('No redis support')

########################## test 
def test_NumpyUInt8SharedMemoryIO():
    # Initialize the mock shared memory IO
    shm_io = NumpyUInt8SharedMemoryIO()

    # Create a writer for a specific shared memory segment
    writer = shm_io.writer(shm_name="numpy_uint8_shm", array_shape=(10, 10))    
    print(writer.model_dump())

    # Create some sample data to write
    data = np.random.randint(0, 256, size=(10, 10), dtype=np.uint8)

    # Write the NumPy int8 array to shared memory
    writer.write(data)

    # Now create a reader for the same shared memory segment
    reader = shm_io.reader(shm_name="numpy_uint8_shm", array_shape=(10, 10))

    # Read the data back from shared memory
    data_read = reader.read()

    print(data_read)

    # Validate that the data matches
    assert np.array_equal(data, data_read), "The data read from shared memory does not match the written data"
    
    # Close the reader
    reader.close()
    writer.close()

    return "Test passed!"

def test_redisIO():
    # Initialize RedisIO for writing
    redis_io = RedisIO()

    # Create a writer for a specific Redis key
    writer = redis_io.writer(key="binary_data_key")
    print(writer.model_dump())
    # Create a reader for the same Redis key
    reader = redis_io.reader(key="binary_data_key")

    # Write binary data to Redis
    data = b"Hello, this is a binary message stored in Redis!"
    writer.write(data)

    # Read the binary data from Redis
    data_read = reader.read()
    print(data_read)  # Outputs: b"Hello, this is a binary message stored in Redis!"

    # Close the reader (not necessary for Redis, but to maintain CommonIO consistency)
    reader.close()
    writer.close()

def test_BidirectionalStream():
    shm_io = NumpyUInt8SharedMemoryStreamIO()
    writer = shm_io.writer(shm_name="numpy_uint8_shm", array_shape=(10, 10))
    
    bwriter = BidirectionalStream.WriteOnly(
        lambda  i,frame,frame_metadata:(np.random.randint(0, 256, size=(10, 10), dtype=np.uint8),{'No':print(i)}),
        writer)    
    bwriter.run()

test_NumpyUInt8SharedMemoryIO()
test_redisIO()
test_BidirectionalStream()