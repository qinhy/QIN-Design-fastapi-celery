# from https://github.com/qinhy/singleton-key-value-storage.git
from .RedisStorage import *
from .MongoStorage import *
from .FileSystemStorage import *
from .Storage import SingletonKeyValueStorage, EventDispatcherController, PythonDictStorage