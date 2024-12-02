
from contextlib import contextmanager
from Config import APP_BACK_END, RABBITMQ_URL, MONGO_URL, MONGO_DB, CELERY_META, CELERY_RABBITMQ_BROKER, RABBITMQ_USER, RABBITMQ_PASSWORD, REDIS_URL

from datetime import datetime
from multiprocessing import shared_memory
import threading
import time
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo
import requests
import celery
import celery.states
import numpy as np
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import redis
import json
import celery.states
import pika
import json
import threading

import celery
import requests
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

try:
    from ..Storages import SingletonKeyValueStorage
except Exception as e:
    from Storages import SingletonKeyValueStorage

class AppInterface:
    @staticmethod
    def check_services() -> bool: raise NotImplementedError('check_services')
    @staticmethod
    def send_data_to_task(task_id, data: dict): raise NotImplementedError('send_data_to_task')
    @staticmethod
    def listen_data_of_task(task_id, data_callback=lambda data: data, eternal=False): raise NotImplementedError('listen_data_of_task')
    @staticmethod
    def get_celery_app()->celery.Celery: raise NotImplementedError('get_celery_app')
    @staticmethod
    def check_rabbitmq_health(url=None, user='', password='') -> bool:('check_rabbitmq_health')
    @staticmethod
    def check_mongodb_health(url=None) -> bool:('check_mongodb_health')
    @staticmethod
    def get_tasks_collection(): raise NotImplementedError('get_tasks_collection')
    @staticmethod
    def get_tasks_list(): raise NotImplementedError('get_tasks_list')
    @staticmethod
    def get_task_meta(task_id: str): raise NotImplementedError('get_task_meta')
    @staticmethod
    def get_task_status(task_id: str): raise NotImplementedError('get_task_status')
    @staticmethod
    def set_task_started(task_model: 'ServiceOrientedArchitecture.Model'): raise NotImplementedError('set_task_started')
    @staticmethod
    def set_task_revoked(task_id): raise NotImplementedError('set_task_revoked')

class RabbitmqMongoApp(AppInterface):
    rabbitmq_URL = RABBITMQ_URL
    mongo_URL = MONGO_URL
    mongo_DB = MONGO_DB
    celery_META = CELERY_META
    CELERY_RABBITMQ_BROKER = CELERY_RABBITMQ_BROKER
    TASK_PUBSUB_NAME = 'task_updates'

    store = SingletonKeyValueStorage().mongo_backend(mongo_URL)

    @staticmethod
    def send_data_to_task(task_id, data: dict):
        h,p = RABBITMQ_URL.split(':')
        connection = pika.BlockingConnection(pika.ConnectionParameters(h))
        channel = connection.channel()
        channel.exchange_declare(exchange=RabbitmqMongoApp.TASK_PUBSUB_NAME,
                                 exchange_type='direct')

        message = json.dumps({'task_id': task_id, 'data': data})
        channel.basic_publish(exchange=RabbitmqMongoApp.TASK_PUBSUB_NAME,
                                 routing_key=task_id, body=message)
        # print(f" [x] Sent data to task {task_id}: {data}")
        connection.close()

    @staticmethod
    def listen_data_of_task(task_id, data_callback=lambda data: data, eternal=False):
        h,p = RABBITMQ_URL.split(':')
        connection = pika.BlockingConnection(pika.ConnectionParameters(h))
        channel = connection.channel()
        channel.exchange_declare(exchange=RabbitmqMongoApp.TASK_PUBSUB_NAME,
                                 exchange_type='direct')

        # Create a unique, exclusive queue for this task
        result = channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue
        channel.queue_bind(exchange=RabbitmqMongoApp.TASK_PUBSUB_NAME,
                                 queue=queue_name, routing_key=task_id)

        def listen():
            def callback(ch, method, properties, body):
                if RabbitmqMongoApp.get_task_status(task_id) in celery.states.READY_STATES:
                        channel.stop_consuming()
                        connection.close()
                        return
                
                message = json.loads(body)
                if message['task_id'] == task_id:
                    # print(f" [x] Received data for task {task_id}: {message['data']}")
                    data_callback(message['data'])
                    if not eternal:
                        channel.stop_consuming()
                        connection.close()
                        return
                
                if RabbitmqMongoApp.get_task_status(task_id) in celery.states.READY_STATES:
                        channel.stop_consuming()
                        connection.close()
                        return

            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
            # print(f" [*] {'eternal'if eternal else ''} Listening for data on task {task_id}...")
            channel.start_consuming()

        listener_thread = threading.Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()

    @staticmethod
    def get_celery_app():
        return celery.Celery(RabbitmqMongoApp.mongo_DB, broker=RabbitmqMongoApp.CELERY_RABBITMQ_BROKER,
                             backend=f'{RabbitmqMongoApp.mongo_URL}/{RabbitmqMongoApp.mongo_DB}')
    
    @staticmethod
    def check_rabbitmq_health(url=None, user=RABBITMQ_USER, password=RABBITMQ_PASSWORD) -> bool:
        if url is None:
            url = f'http://{RabbitmqMongoApp.rabbitmq_URL}/api/health/checks/alarms'
        try:
            response = requests.get(url, auth=(user, password), timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    @staticmethod
    def check_mongodb_health(url=None) -> bool:
        if url is None:
            url = RabbitmqMongoApp.mongo_URL
        try:
            client = MongoClient(url, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            return True
        except ConnectionFailure:
            return False

    @classmethod
    def check_services(cls) -> bool:
        rabbitmq_health = cls.check_rabbitmq_health()
        mongodb_health = cls.check_mongodb_health()
        return rabbitmq_health and mongodb_health

    @staticmethod
    def get_tasks_collection():
        client = MongoClient(RabbitmqMongoApp.mongo_URL)
        db = client.get_database(RabbitmqMongoApp.mongo_DB)
        collection = db.get_collection(RabbitmqMongoApp.celery_META)
        return collection

    @staticmethod
    def get_tasks_list():
        collection = RabbitmqMongoApp.get_tasks_collection()
        tasks = []
        for task in collection.find():
            task_data = {
                "task_id": task.get('_id'),
                "status": task.get('status'),
                "result": task.get('result'),
                "date_done": task.get('date_done')
            }
            tasks.append(task_data)
        return tasks

    @staticmethod
    def get_task_meta(task_id: str):
        collection = RabbitmqMongoApp.get_tasks_collection()
        res = collection.find_one({'_id': task_id})
        if res:
            del res['_id']
            return res
        else:
            return {}
    
    @staticmethod
    def get_task_status(task_id: str):
        return RabbitmqMongoApp.get_task_meta(task_id).get('status',None)

    @staticmethod
    def set_task_started(task_model: 'ServiceOrientedArchitecture.Model'):
        collection = RabbitmqMongoApp.get_tasks_collection()
        collection.update_one(
            {'_id': task_model.task_id},
            {'$set': {
                'status': celery.states.STARTED,
                'result': task_model.model_dump_json()
            }},
            upsert=True
        )

    @staticmethod
    def set_task_revoked(task_id):
        collection = RabbitmqMongoApp.get_tasks_collection()
        update_result = collection.update_one({'_id': task_id}, {'$set': {'status': 'REVOKED'}})
        if update_result.matched_count > 0:
            res = collection.find_one({'_id': task_id})
        else:
            res = {'error': 'Task not found'}
        return res

class RedisApp(AppInterface):
    store = SingletonKeyValueStorage().redis_backend()
    # Redis URL configuration
    redis_URL = REDIS_URL
    redis_client = redis.Redis.from_url(redis_URL)

    @staticmethod
    def send_data_to_task(task_id, data):
        message = json.dumps({'task_id': task_id, 'data': data})
        RedisApp.redis_client.publish(task_id, message)
        # print(f" [x] Sent data to task {task_id}: {data}")

    @staticmethod
    def listen_data_of_task(task_id, data_callback=lambda data: data, eternal=False):
        pubsub = RedisApp.redis_client.pubsub()
        pubsub.subscribe(task_id)

        def listen():
            # print(f" [*] Listening for data on task {task_id}...")
            for message in pubsub.listen():
                if RedisApp.get_task_status(task_id) in celery.states.READY_STATES: break

                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    # print(f" [x] Received data for task {task_id}: {data['data']}")
                    data_callback(data['data'])
                    if not eternal: break
                    
                if RedisApp.get_task_status(task_id) in celery.states.READY_STATES: break
            
            pubsub.unsubscribe(task_id)

        listener_thread = threading.Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()


    @staticmethod
    def get_celery_app():
        return celery.Celery('tasks', broker=RedisApp.redis_URL, backend=RedisApp.redis_URL)

    @staticmethod    
    def check_services() -> bool:
        """Check Redis connection health."""
        try:
            return RedisApp.redis_client.ping()
        except redis.ConnectionError:
            return False

    @staticmethod        
    def get_tasks_collection():
        """Returns a list of keys representing tasks in Redis."""
        return RedisApp.redis_client.keys(pattern='celery-task-meta-*')

    @staticmethod
    def get_tasks_list():    
        """Fetches a list of all tasks stored in Redis."""
        task_keys = RedisApp.get_tasks_collection()
        tasks = []

        for key in task_keys:
            task_data_json = RedisApp.redis_client.get(key)
            if task_data_json:
                task:dict = json.loads(task_data_json)
                task_data = {
                    "task_id": task.get('task_id'),
                    "status": task.get('status'),
                    "result": json.dumps(task.get('result')),
                    "date_done": task.get('date_done')
                }
                tasks.append(task_data)
        return tasks
    
    @staticmethod
    def get_task_meta(task_id: str):
        task_key = f'celery-task-meta-{task_id}'
        task_data_json = RedisApp.redis_client.get(task_key)
        if task_data_json:
            task_data = json.loads(task_data_json)
            return task_data
        return {}
    
    @staticmethod
    def get_task_status(task_id: str):
        return RedisApp.get_task_meta(task_id).get('status',None)

    @staticmethod
    def set_task_started(task_model:'ServiceOrientedArchitecture.Model'):
        """Marks a task as started in Redis."""
        task_key = f'celery-task-meta-{task_model.task_id}'
        task_data = {
            'task_id': task_model.task_id,
            'status': celery.states.STARTED,
            'result': task_model.model_dump_json()  # Assuming `task_model` has this method
        }
        RedisApp.redis_client.set(task_key, json.dumps(task_data))

    @staticmethod
    def set_task_revoked(task_id):
        """Marks a task as revoked in Redis."""
        task_key = f'celery-task-meta-{task_id}'
        task_data_json = RedisApp.redis_client.get(task_key)
        if task_data_json:
            task_data = json.loads(task_data_json)
            task_data['status'] = 'REVOKED'
            RedisApp.redis_client.set(task_key, json.dumps(task_data))
            return task_data
        else:
            return {'error': 'Task not found'}

if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp
else:
    raise ValueError(f'no back end of {APP_BACK_END}')

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

        @contextmanager
        def listen_stop_flag(self):
            task_id=self.model.task_id
            BasicApp.set_task_started(self.model)
            # A shared flag to communicate between threads
            stop_flag = threading.Event()
            # Function to check if the task should be stopped, running in a separate thread
            def check_task_status(data:dict,task_id=task_id):
                if data.get('status',None) == celery.states.REVOKED:
                    BasicApp.set_task_revoked(task_id)
                    stop_flag.set()
            BasicApp.listen_data_of_task(task_id,check_task_status,True)
            
            try:
                yield stop_flag  # Provide the stop_flag to the `with` block
            finally:
                BasicApp.send_data_to_task(self.model.task_id,{})
            return stop_flag

        def __call__(self, *args, **kwargs):
            return self.model

##################### IO 

def now_utc():
    return datetime.now().replace(tzinfo=ZoneInfo("UTC"))

class AbstractObj(BaseModel):
    id: str= Field(default_factory=lambda:f"AbstractObj:{uuid4()}")
    rank: list = [0]
    create_time: datetime = Field(default_factory=now_utc)
    update_time: datetime = Field(default_factory=now_utc)
    status: str = ""
    metadata: dict = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(f'BasicApp.store.set({self.id},{self.__class__.__name__})')
        BasicApp.store.set(self.id,self.model_dump_json_dict())
    
    def __del__(self):
        print(f'BasicApp.store.delete({self.id})')
        BasicApp.store.delete(self.id)

    def model_dump_json_dict(self)->dict:
        return json.loads(self.model_dump_json())
         
class CommonIO:
    class Base(AbstractObj):            
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

        def build_buffer(self):
            # Initialize shared memory with the validated size and sanitized name
            self._shm = shared_memory.SharedMemory(name=self.shm_name, create=self.create, size=self.shm_size)
            self._buffer = memoryview(self._shm.buf)  # View into the shared memory buffer
            return self
                
        def close(self):
            """Detach from the shared memory."""
            # Release the memoryview before closing the shared memory
            if hasattr(self,'_buffer') and self._buffer is not None:
                self._buffer.release()
                del self._buffer
            if hasattr(self,'_shm'):
                self._shm.close()  # Detach from shared memory

        def __del__(self):
            super().__del__()
            self.close()

    class Reader(CommonIO.Reader, Base):
        id: str= Field(default_factory=lambda:f"GeneralSharedMemoryIO.Reader:{uuid4()}")
        def read(self, size: int = None) -> bytes:
            """Read binary data from shared memory."""
            if size is None or size > self.shm_size:
                size = self.shm_size  # Read the whole buffer by default
            return bytes(self._buffer[:size])  # Convert memoryview to bytes
  
    class Writer(CommonIO.Writer, Base):
        id: str= Field(default_factory=lambda:f"GeneralSharedMemoryIO.Writer:{uuid4()}")
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
        return GeneralSharedMemoryIO.Reader(shm_name=shm_name, create=False, shm_size=shm_size).build_buffer()
    
    @staticmethod
    def writer(shm_name: str, shm_size: int):
        return GeneralSharedMemoryIO.Writer(shm_name=shm_name, create=True, shm_size=shm_size).build_buffer()
   
class NumpyUInt8SharedMemoryIO(GeneralSharedMemoryIO):
    class Base(GeneralSharedMemoryIO.Base):
        array_shape: tuple = Field(..., description="Shape of the NumPy array to store in shared memory")
        _dtype: np.dtype = np.uint8
        _shared_array: np.ndarray
        def __init__(self, **kwargs):
            kwargs['shm_size'] = np.prod(kwargs['array_shape']) * np.dtype(np.uint8).itemsize
            super().__init__(**kwargs)
            
        def build_buffer(self):
            super().build_buffer()
            self._shared_array = np.ndarray(self.array_shape, dtype=self._dtype, buffer=self._buffer)
            return self

    class Reader(GeneralSharedMemoryIO.Reader, Base):
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryIO.Reader:{uuid4()}")
        def read(self,copy=True) -> np.ndarray:
            return self._shared_array.copy() if copy else self._shared_array
            # binary_data = super().read(size=self.shm_size)
            # return np.frombuffer(binary_data, dtype=self._dtype).reshape(self.array_shape)
    
    class Writer(GeneralSharedMemoryIO.Writer, Base):
        id: str= Field(default_factory=lambda:f"NumpyUInt8SharedMemoryIO.Writer:{uuid4()}")
        def write(self, data: np.ndarray):
            if data.shape != self.array_shape:
                raise ValueError(f"Data shape {data.shape} does not match expected shape {self.array_shape}.")
            if data.dtype != self._dtype:
                raise ValueError(f"Data type {data.dtype} does not match expected type {self._dtype}.")            
            self._shared_array[:] = data[:]
            # super().write(data.tobytes())

    @staticmethod
    def reader(shm_name: str, array_shape: tuple):
        shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
        return NumpyUInt8SharedMemoryIO.Reader(shm_size=shm_size,
                                    shm_name=shm_name, create=False, array_shape=array_shape).build_buffer()
    
    @staticmethod
    def writer(shm_name: str, array_shape: tuple):
        shm_size = np.prod(array_shape) * np.dtype(np.uint8).itemsize
        return NumpyUInt8SharedMemoryIO.Writer(shm_size=shm_size,
                                    shm_name=shm_name, create=True, array_shape=array_shape).build_buffer()

##################### stream IO 
class CommonStreamIO(CommonIO):
    class Base(CommonIO.Base):
        stream_key: str = 'NULL'
        is_close: bool = False

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            tmp = self.model_dump_json_dict()
            tmp['id'] = self.stream_id()
            BasicApp.store.set(self.stream_id(),tmp)
        
        def __del__(self):
            super().__del__()
            BasicApp.store.delete(self.stream_id())

        def stream_id(self):
            return f'streams:{self.stream_key}'

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
        id: str= Field(default_factory=lambda:f"CommonStreamIO.StreamReader:{uuid4()}")
        def read(self)->tuple[Any,dict]:
            return super().read(),{}
        
        def __iter__(self):
            return self

        def __next__(self):
            return self.read()        
        
    class StreamWriter(CommonIO.Writer, Base):
        id: str= Field(default_factory=lambda:f"CommonStreamIO.StreamWriter:{uuid4()}")
        def write(self, data, metadata={}):
            raise ValueError("[StreamWriter]: 'write' not implemented")

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

class BidirectionalStream:
    class Bidirectional:
        id: str= Field(default_factory=lambda:f"BidirectionalStream.Bidirectional:{uuid4()}")
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
        id: str= Field(default_factory=lambda:f"BidirectionalStream.WriteOnly:{uuid4()}")
        def __init__(self, frame_processor=lambda i,frame,frame_metadata:(frame,frame_metadata),
                    stream_writer:CommonStreamIO.StreamWriter=None):
            self.frame_processor = frame_processor
            self.stream_writer = stream_writer
            self.streams:list[CommonStreamIO.Base] = [self.stream_writer]
            
            def mock_stream():
                while True: yield None,{}
            self.stream_reader = mock_stream()

    class ReadOnly(Bidirectional):
        id: str= Field(default_factory=lambda:f"BidirectionalStream.ReadOnly:{uuid4()}")
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
    writer = shm_io.writer(stream_key="numpy:uint8:shm", array_shape=(7680, 4320, 3))
    img = np.random.randint(0, 256, size=(7680, 4320, 3), dtype=np.uint8)
    bwriter = BidirectionalStream.WriteOnly(
        lambda  i,frame,frame_metadata:(img,{'No':print(frame_metadata.get('fps',0))}),
        writer)    
    bwriter.run()

# test_NumpyUInt8SharedMemoryIO()
# test_redisIO()
# test_BidirectionalStream()