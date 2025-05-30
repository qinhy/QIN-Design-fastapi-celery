# from https://github.com/qinhy/singleton-key-value-storage.git
import math
import os
import uuid
import fnmatch
import json
import unittest
from pathlib import Path

try:
    from .utils import SimpleRSAChunkEncryptor, PEMFileReader
except Exception as e:
    from utils import SimpleRSAChunkEncryptor, PEMFileReader

class AbstractStorage:
    # statics for singleton
    _uuid = uuid.uuid4()
    _store = None
    _is_singleton = True
    _meta = {}
        
    def __init__(self,id=None,store=None,is_singleton=None):
        self.uuid = uuid.uuid4() if id is None else id
        self.store = None if store is None else store
        self.is_singleton = False if is_singleton is None else is_singleton
    
    def get_singleton(self):
        return self.__class__(self._uuid,self._store,self._is_singleton)
    
class AbstractStorageController:
    def __init__(self, model): self.model:AbstractStorage = model
    
    def is_singleton(self)->bool: return self.model.is_singleton if 'is_singleton' in self.model else False

    def exists(self, key: str)->bool: print(f'[{self.__class__.__name__}]: not implement')

    def set(self, key: str, value: dict): print(f'[{self.__class__.__name__}]: not implement')

    def get(self, key: str)->dict: print(f'[{self.__class__.__name__}]: not implement')

    def delete(self, key: str): print(f'[{self.__class__.__name__}]: not implement')

    def keys(self, pattern: str='*')->list[str]: print(f'[{self.__class__.__name__}]: not implement')
    
    def clean(self): [self.delete(k) for k in self.keys('*')]

    def dumps(self): return json.dumps({k:self.get(k) for k in self.keys('*')})
    
    def loads(self, json_string=r'{}'): [ self.set(k,v) for k,v in json.loads(json_string).items()]

    def dump(self, path: str):return Path(path).write_text(self.dumps())

    def load(self, path: str):return self.loads(Path(path).read_text())

    def dump_RSA(self,path,public_pkcs8_key_path):
        encryptor = SimpleRSAChunkEncryptor(
            PEMFileReader(public_pkcs8_key_path).load_public_pkcs8_key(), None)
        return Path(path).write_text(encryptor.encrypt_string(self.dumps()))

    def load_RSA(self,path,private_pkcs8_key_path):
        encryptor = SimpleRSAChunkEncryptor(
            None, PEMFileReader(private_pkcs8_key_path).load_private_pkcs8_key())
        return self.loads(encryptor.decrypt_string(Path(path).read_text()))

class PythonDictStorage:
    # statics for singleton
    _uuid = uuid.uuid4()
    _store = {}
    _is_singleton = True
    _meta = {}
        
    def __init__(self,id=None,store=None,is_singleton=None):
        self.uuid = uuid.uuid4() if id is None else id
        self.store = {} if store is None else store
        self.is_singleton = False if is_singleton is None else is_singleton
    
    def get_singleton(self):
        return self.__class__(self._uuid,self._store,self._is_singleton)

class PythonDictStorageController(AbstractStorageController):
    def __init__(self, model:PythonDictStorage):
        self.model:PythonDictStorage = model
        self.store = self.model.store

    def exists(self, key: str)->bool: return key in self.store

    def set(self, key: str, value: dict): self.store[key] = value

    def get(self, key: str)->dict: return self.store.get(key,None)

    def delete(self, key: str): return self.store.pop(key)

    def keys(self, pattern: str='*'): return fnmatch.filter(self.store.keys(), pattern)

class EventDispatcherController(PythonDictStorageController):
    ROOT_KEY = 'Event'
    
    def _find_event(self, uuid: str):
        es = self.keys(f'*:{uuid}')
        return [None] if len(es)==0 else es
    
    def events(self):
        return list(zip(self.keys('*'),[self.get(k) for k in self.keys('*')]))

    def get_event(self, uuid: str):
        return [self.get(k) for k in self._find_event(uuid)]
    
    def delete_event(self, uuid: str):
        return [self.delete(k) for k in self._find_event(uuid)]
    
    def set_event(self, event_name: str, callback, id:str=None):
        if id is None:id = uuid.uuid4()
        self.set(f'{EventDispatcherController.ROOT_KEY}:{event_name}:{id}', callback)
        return id
    
    def dispatch_event(self, event_name, *args, **kwargs):
        for event_full_uuid in self.keys(f'{EventDispatcherController.ROOT_KEY}:{event_name}:*'):
            self.get(event_full_uuid)(*args, **kwargs)

class MessageQueueController(PythonDictStorageController):
    ROOT_KEY = 'MessageQueue'
    
    def __init__(self, model: PythonDictStorage):
        super().__init__(model)
        self.counters = {}  # Track counters for each queue

    def _get_queue_key(self, queue_name: str, index: int) -> str:
        return f'{MessageQueueController.ROOT_KEY}:{queue_name}:{index}'

    def _get_queue_counter(self, queue_name: str) -> int:
        if queue_name not in self.counters:
            self.counters[queue_name] = 0
        return self.counters[queue_name]

    def _increment_queue_counter(self, queue_name: str):
        self.counters[queue_name] = self._get_queue_counter(queue_name) + 1

    def push(self, message: dict, queue_name: str = 'default'):
        counter = self._get_queue_counter(queue_name)
        key = self._get_queue_key(queue_name, counter)
        self.set(key, message)
        self._increment_queue_counter(queue_name)
        return key

    def pop(self, queue_name: str = 'default') -> dict:
        keys = self.keys(f'{MessageQueueController.ROOT_KEY}:{queue_name}:*')
        if not keys: return None  # Queue is empty
        earliest_key = keys[0]
        message = self.get(earliest_key)
        self.delete(earliest_key)
        return message

    def peek(self, queue_name: str = 'default') -> dict:
        keys = self.keys(f'{MessageQueueController.ROOT_KEY}:{queue_name}:*')
        if not keys: return None  # Queue is empty
        return self.get(keys[0])

    def size(self, queue_name: str = 'default') -> int:
        return len(self.keys(f'{MessageQueueController.ROOT_KEY}:{queue_name}:*'))

    def clear(self, queue_name: str = 'default'):
        for key in self.keys(f'{MessageQueueController.ROOT_KEY}:{queue_name}:*'):
            self.delete(key)
        if queue_name in self.counters:
            del self.counters[queue_name]

class LocalVersionController:
    
    TABLENAME = '_Operation'
    LISTNAME = '_Operations'
    KEY = 'ops'
    FORWARD = 'forward'    
    REVERT = 'revert'

    def __init__(self,client=None):
        if client is None:
            client = PythonDictStorageController(PythonDictStorage())
        self.client:AbstractStorageController = client
        self._set_versions([])
        self._current_version = None
    
    def get_versions(self)->list: 
        return self.client.get(LocalVersionController.TABLENAME)[LocalVersionController.KEY]
    
    def _set_versions(self,ops:list): 
        return self.client.set(LocalVersionController.TABLENAME,{LocalVersionController.KEY:ops})
    
    def find_version(self,version_uuid:str):         
        versions = [i for i in self.get_versions()]
        current_version_idx = versions.index(self._current_version
                                             ) if self._current_version in versions else None
        target_version_idx = versions.index(version_uuid
                                            ) if version_uuid in versions else None
        op = self.client.get(f'{LocalVersionController.TABLENAME}:{versions[target_version_idx]}'
                             ) if target_version_idx else None
        return versions,current_version_idx,target_version_idx,op

    def add_operation(self,operation:tuple,revert:tuple=None):
        opuuid = str(uuid.uuid4())
        self.client.set(f'{LocalVersionController.TABLENAME}:{opuuid}',{
            LocalVersionController.FORWARD:operation,LocalVersionController.REVERT:revert})
        
        ops = self.get_versions()
        if self._current_version is not None:
            opidx = ops.index(self._current_version)
            ops = ops[:opidx+1]

        ops.append(opuuid)
        self._set_versions(ops)
        self._current_version = opuuid

    def forward_one_operation(self,forward_callback:lambda forward:None):
        versions,current_version_idx,_,_ = self.find_version(self._current_version)
        if current_version_idx is None or len(versions)<=(current_version_idx+1):return
        op = self.client.get(f'{LocalVersionController.TABLENAME}:{versions[current_version_idx+1]}')
        # do forward
        forward_callback(op[LocalVersionController.FORWARD])
        self._current_version = versions[current_version_idx+1]
    
    def revert_one_operation(self,revert_callback:lambda revert:None):        
        versions,current_version_idx,_,op = self.find_version(self._current_version)
        if current_version_idx is None or (current_version_idx-1)<0:return
        # do revert
        revert_callback(op[LocalVersionController.REVERT])
        self._current_version = versions[current_version_idx-1]

    def to_version(self,version_uuid:str,version_callback:lambda ops:None):
        _,current_version_idx,target_version_idx,_ = self.find_version(version_uuid)
        if target_version_idx is None:raise ValueError(f'no such version of {version_uuid}')

        delta_idx = target_version_idx - current_version_idx
        sign = math.copysign(1, delta_idx)
        
        while abs(delta_idx) != 0:
            if sign>0:
                self.forward_one_operation(version_callback)
            else:
                self.revert_one_operation(version_callback)
            delta_idx = delta_idx - sign

class SingletonKeyValueStorage(AbstractStorageController):    
    backs={
        'temp_python':lambda *args,**kwargs:PythonDictStorageController(PythonDictStorage(*args,**kwargs)),
        'python':lambda *args,**kwargs:PythonDictStorageController(PythonDictStorage(*args,**kwargs).get_singleton()),
    }

    def __init__(self,version_controll=False,
                 encryptor:SimpleRSAChunkEncryptor=None)->None:
        self.version_controll = version_controll
        self.encryptor = encryptor
        self.conn:AbstractStorageController = None
        self.python_backend()
    
    def _switch_backend(self,name:str='python',*args,**kwargs):
        self._event_dispa = EventDispatcherController(PythonDictStorage())
        self._verc = LocalVersionController()
        back=self.backs.get(name.lower(),None)
        if back is None:raise ValueError(f'no back end of {name}, has {list(self.backs.items())}')
        return back
    
    def s3_backend(self,bucket_name,
                    aws_access_key_id,aws_secret_access_key,region_name,
                    s3_storage_prefix_path = '/SingletonS3Storage'):
        self.conn = self._switch_backend('s3',bucket_name,
                    aws_access_key_id,aws_secret_access_key,region_name,
                    s3_storage_prefix_path = s3_storage_prefix_path)
        
    def file_backend(self,storage_dir='./SingletonKeyValueStorage', ext='.json'):
        self.conn = self._switch_backend('file')(storage_dir=storage_dir,ext=ext)

    def temp_python_backend(self):
        self.conn = self._switch_backend('temp_python')()
    
    def python_backend(self):
        self.conn = self._switch_backend('python')()
    
    def sqlite_pymix_backend(self,mode='sqlite.db'):
        self.conn = self._switch_backend('sqlite_pymix')(mode=mode)
    
    def sqlite_backend(self):             
        self.conn = self._switch_backend('sqlite')()

    def firestore_backend(self,google_project_id:str=None,google_firestore_collection:str=None):
        self.conn = self._switch_backend('firestore')(google_project_id,google_firestore_collection)

    def redis_backend(self,redis_URL:str='redis://127.0.0.1:6379'):
        self.conn = self._switch_backend('redis')(redis_URL)

    def mongo_backend(self,mongo_URL:str="mongodb://127.0.0.1:27017/",
                        db_name:str="SingletonDB", collection_name:str="store"):
        self.conn = self._switch_backend('mongodb')(mongo_URL,db_name,collection_name)

    def _print(self,msg): print(f'[{self.__class__.__name__}]: {msg}')
       
    def delete_slave(self, slave:object)->bool: self.delete_event(getattr(slave,'uuid',None))

    def add_slave(self, slave:object, event_names=['set','delete'])->bool:
        if getattr(slave,'uuid',None) is None:
            try:
                setattr(slave,'uuid',uuid.uuid4())
            except Exception:
                return self._print(f'can not set uuid to {slave}. Skip this slave.')
        for m in event_names:
            if hasattr(slave, m):
                self.set_event(m,getattr(slave,m),getattr(slave,'uuid'))
            else:
                self._print(f'no func of "{m}" in {slave}. Skip it.')         

    def _edit_local(self,func_name:str, key:str=None, value:dict=None):
        if func_name not in ['set','delete','clean','load','loads']:
            return self._print(f'no func of "{func_name}". return.')
        func = getattr(self.conn, func_name)
        args = [i for i in [key,value] if i is not None]
        return func(*args)
    
    def _edit(self,func_name:str, key:str=None, value:dict=None):
        args = [i for i in [key,value] if i is not None]        
        
        if self.encryptor and func_name=='set':
            value = {'rjson':self.encryptor.encrypt_string(json.dumps(value))}

        res = self._edit_local(func_name,key,value)
        self.dispatch_event(func_name,*args)
        return res
    
    def _try_edit_error(self,args):
        if self.version_controll:
            # do local version controll
            func = args[0]
            if func == 'set':
                func,key,_ =args
                revert = None
                if self.exists(key):
                    revert = (func,key,self.get(key))
                else:
                    revert = ('delete',key)
                self._verc.add_operation(args,revert)
                
            elif func == 'delete':
                func,key = args
                revert = ('set',key,self.get(key))
                self._verc.add_operation(args,revert)

            elif func in ['clean','load','loads']:
                revert = ('loads',self.dumps())
                self._verc.add_operation(args,revert)

        try:
            self._edit(*args)
            return True
        except Exception as e:
            self._print(e)
            return False
    
    def revert_one_operation(self):
        self._verc.revert_one_operation(lambda revert:self._edit_local(*revert))

    def get_current_version(self):
        vs = self._verc.get_versions()
        return None if len(vs)==0 else vs[-1]

    def local_to_version(self,opuuid:str):
        self._verc.to_version(opuuid,lambda revert:self._edit_local(*revert))

    # True False(in error)
    def set(self, key: str, value: dict):     return self._try_edit_error(('set',key,value))
    def delete(self, key: str):               return self._try_edit_error(('delete',key))
    def clean(self):                          return self._try_edit_error(('clean',))
    def load(self,json_path):                 return self._try_edit_error(('load', json_path))
    def loads(self,json_str):                 return self._try_edit_error(('loads',json_str))
    
    def _try_load_error(self,func):
        try:
            return func()
        except Exception as e:
            self._print(e)
            return None
    # Object, None(in error)    
    def exists(self, key: str)->bool:         return self._try_load_error(lambda:self.conn.exists(key))
    def keys(self, regx: str='*')->list[str]: return self._try_load_error(lambda:self.conn.keys(regx))

    def get(self, key: str)->dict:            
        value = self._try_load_error(lambda:self.conn.get(key))
        if value and self.encryptor and 'rjson' in value:
            value = self._try_load_error(
                lambda:json.loads(self.encryptor.decrypt_string(value['rjson'])))
        return value
    
    def dumps(self)->str:                  
        return self._try_load_error(lambda:json.dumps({k:self.get(k) for k in self.keys('*')}))
    
    def dump(self,json_path)->None:           return self._try_load_error(lambda:self.conn.dump(json_path))

    # events 
    def events(self): return self._event_dispa.events()
    def get_event(self, uuid: str): return self._event_dispa.get_event(uuid)
    def delete_event(self, uuid: str): return self._event_dispa.delete_event(uuid)
    def set_event(self, event_name: str, callback, id:str=None): return self._event_dispa.set_event(event_name, callback, id)
    def dispatch_event(self, event_name, *args, **kwargs): return self._event_dispa.dispatch_event(event_name, *args, **kwargs)
    def clean_events(self): return self._event_dispa.clean()


