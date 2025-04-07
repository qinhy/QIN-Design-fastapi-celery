from contextlib import contextmanager
from datetime import datetime
import io
import json
import logging
import os
import re
import requests
import threading
import time
from typing import Optional
from uuid import uuid4

import celery
import celery.states
import pika
import pymongo
from pymongo import MongoClient
import pymongo.errors
import redis
from pydantic import BaseModel, Field, PrivateAttr


try:
    from ..Storages import EventDispatcherController, PythonDictStorage
except Exception as e:
    from Storages import EventDispatcherController, PythonDictStorage

try:
    from ..Storages.BasicModel import BasicStore
except Exception as e:
    from Storages.BasicModel import BasicStore

class PubSubInterface:
    ROOT_KEY = 'PubSub'

    def __init__(self):
        self._event_disp = EventDispatcherController(PythonDictStorage())
    
    def subscribe(self, topic: str, callback, eternal=False, id: str = None):
        """Subscribe to a topic with a given callback."""
        if id is None: id = str(uuid4())
        self._event_disp.set(f'{PubSubInterface.ROOT_KEY}:{topic}:{id}', callback)
        self._event_disp.set(f'{PubSubInterface.ROOT_KEY}:{topic}:{id}:eternal', eternal)
        return id
    
    def unsubscribe(self, id: str):
        """Unsubscribe from a topic using the given id."""
        keys = self._event_disp.keys(f'{PubSubInterface.ROOT_KEY}:*:{id}')
        if len(keys)==1:
            key = keys[0]
            if self._event_disp.exists(key):
                self._event_disp.delete(key)
                return True
        return False
    
    def publish(self, topic: str, data:dict):
         raise NotImplementedError('publish')

    def call_subscribers(self,topic,data:dict):
        for sub_key, subscriber in self.get_subscribers(topic):
            if callable(subscriber):
                subscriber(data)
                if not self._event_disp.get(f'{sub_key}:eternal'):
                    self._event_disp.delete(sub_key)

    def get_subscribers(self, topic: str):
        """Retrieve all subscribers for a given topic."""
        return [(sub_key, self._event_disp.get(sub_key)) for sub_key in self._event_disp.keys(f'{PubSubInterface.ROOT_KEY}:{topic}:*')]
    
    def get_topics(self):
        ts = [k for k in self._event_disp.keys(f'{PubSubInterface.ROOT_KEY}:*')]
        ts = [k.split(':')[1] for k in ts]
        return ts

    def clear_subscribers(self, topic: str):
        """Remove all subscribers from a specific topic."""
        for sub_key in self._event_disp.keys(f'{PubSubInterface.ROOT_KEY}:{topic}:*'):
            self._event_disp.delete(sub_key)

class RabbitmqPubSub(PubSubInterface):
    def __init__(self, rabbitmq_url:str, rabbitmq_user:str, rabbitmq_password:str,
                 task_pubsub_name:str='RabbitmqPubSub'):
        super().__init__()        
        self.rabbitmq_url = rabbitmq_url
        self.rabbitmq_user = rabbitmq_user
        self.rabbitmq_password = rabbitmq_password
        self.task_pubsub_name = task_pubsub_name
        self.connection = None
        self.channel = None
        self.uuid = str(self._event_disp.model.uuid)
    
    def _conn(self):        
        host, port = self.rabbitmq_url.split(':')
        # print(host, port)
        connection = pika.BlockingConnection(pika.ConnectionParameters(host))
        channel = connection.channel()
        channel.exchange_declare(exchange=self.task_pubsub_name, exchange_type='direct')
        return connection,channel

    def publish(self, topic: str, data: dict):
        connection,channel = self._conn()
        message = json.dumps({'topic': topic, 'data': data})
        channel.basic_publish(exchange=self.task_pubsub_name, routing_key=self.ROOT_KEY, body=message)
        connection.close()

    def start_listener(self):
        connection,channel = self._conn()
        self.connection = connection
        self.channel = channel

        result = self.channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue
        self.channel.queue_bind(exchange=self.task_pubsub_name, queue=queue_name, routing_key=self.ROOT_KEY)

        self.listener_thread = threading.Thread(target=self.listen_data_of_topic, args=(queue_name,), daemon=True)
        self.listener_thread.start()

    def listen_data_of_topic(self, queue_name):
        def callback(ch, method, properties, body):
            message:dict = json.loads(body)
            topic = message.get('topic')
            if not topic: return
                            
            self.call_subscribers(topic,message.get('data'))

        self.channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
        self.channel.start_consuming()

    def stop_listener(self):
        self.channel.stop_consuming()
        self.connection.close()

class RedisPubSub(PubSubInterface):
    def __init__(self, redis_url: str, redis_port: int = 6379, redis_db: int = 0, redis_password: str = None,
                 task_pubsub_name: str = 'RedisPubSub'):
        super().__init__()
        self.redis_url = redis_url
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self.task_pubsub_name = task_pubsub_name
        self.uuid = str(self._event_disp.model.uuid)

        # Establish Redis connection
        self.redis_pubsub_client = redis.Redis.from_url(self.redis_url)
        # redis.Redis(
        #     host=self.redis_host,
        #     port=self.redis_port,
        #     db=self.redis_db,
        #     password=self.redis_password,
        #     decode_responses=True
        # )
        self.pubsub = self.redis_pubsub_client.pubsub()
        self.listener_thread = None

    def publish(self, topic: str, data: dict):
        """Publish a message to a topic."""
        message = json.dumps({'topic': topic, 'data': data})
        self.redis_pubsub_client.publish(self.ROOT_KEY, message)

    def start_listener(self):
        """Start listening to subscribed topics in a separate thread."""
        self.listener_thread = threading.Thread(target=self.listen_data_of_topic, daemon=True)
        self.listener_thread.start()

    def listen_data_of_topic(self):
        """Continuously listen for messages on subscribed topics."""
        self.pubsub.subscribe(self.ROOT_KEY)
        for message in self.pubsub.listen():
            if message["type"] == "message":
                message:dict = json.loads(message["data"])
                topic = message.get('topic')
                if not topic:continue
                self.call_subscribers(topic,message.get('data'))

    def unsubscribe(self, id: str):
        """Unsubscribe from a topic and remove Redis subscription."""
        keys = self._event_disp.keys(f'{PubSubInterface.ROOT_KEY}:*:{id}')
        if len(keys) == 1:
            topic = keys[0].split(":")[1]  # Extract topic name
            self.pubsub.unsubscribe(topic)  # Unsubscribe from Redis
            return super().unsubscribe(id)
        return False

    def stop_listener(self):
        """Stop the Redis listener."""
        if self.pubsub:
            self.pubsub.close()
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join()

class FileSystemPubSub(PubSubInterface):
    def __init__(self, base_dir: str = "/tmp/pubsub", task_pubsub_name: str = "FileSystemPubSub"):
        super().__init__()
        self.pubsub_base_dir = os.path.abspath(base_dir)
        self.task_pubsub_name = task_pubsub_name
        self.uuid = str(self._event_disp.model.uuid)
        self.listener_thread = None
        os.makedirs(self.pubsub_base_dir, exist_ok=True)
        self._stop_event = threading.Event()

    def publish(self, topic: str, data: dict):
        """Write a message to a file in the topic directory."""
        topic_dir = os.path.join(self.pubsub_base_dir, topic)
        os.makedirs(topic_dir, exist_ok=True)
        message_id = len(os.listdir(topic_dir))
        filepath = os.path.join(topic_dir, f"{message_id}.json")
        with open(filepath, "w") as f:
            json.dump({"topic": topic, "data": data}, f)

    def start_listener(self):
        """Start monitoring the base directory for new messages."""
        self._stop_event.clear()
        self.listener_thread = threading.Thread(target=self.listen_data_of_topic, daemon=True)
        self.listener_thread.start()

    def listen_data_of_topic(self):
        """Monitor the file system for new messages."""
        processed_files = set()
        while not self._stop_event.is_set():
            for topic in os.listdir(self.pubsub_base_dir):
                topic_dir = os.path.join(self.pubsub_base_dir, topic)
                if not os.path.isdir(topic_dir):
                    continue
                for filename in os.listdir(topic_dir):
                    filepath = os.path.join(topic_dir, filename)
                    if filepath in processed_files or not filename.endswith(".json"):
                        continue
                    try:
                        with open(filepath, "r") as f:
                            message:dict = json.load(f)
                        self.call_subscribers(topic, message.get("data"))
                        processed_files.add(filepath)
                        # os.remove(filepath)  # Remove after processing
                    except Exception as e:
                        print(f"Failed to read/parse {filepath}: {e}")
            time.sleep(1)  # Poll interval

    def stop_listener(self):
        """Stop the listener thread."""
        self._stop_event.set()
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join()

class TaskModel(BaseModel):
    task_id: str
    status: Optional[str] = None
    result: Optional[str] = None
    date_done: Optional[datetime] = None
    scheduled_for_the_timezone: Optional[datetime] = None
    scheduled_for_utc: Optional[datetime] = None
    timezone: Optional[str] = None

class AppInterface(PubSubInterface):
    def redis_client(self) -> redis.Redis: raise NotImplementedError('redis_client')
    def store(self) -> BasicStore: raise NotImplementedError('store')
    def check_services(self) -> bool: raise NotImplementedError('check_services')
    def get_celery_app(self)->celery.Celery: raise NotImplementedError('get_celery_app')
    def check_rabbitmq_health(self, url=None, user='', password='') -> bool:('check_rabbitmq_health')
    def check_mongodb_health(self, url=None) -> bool:('check_mongodb_health')
    def get_tasks_collection(self): raise NotImplementedError('get_tasks_collection')
    def get_tasks_list(self)->list[TaskModel]: raise NotImplementedError('get_tasks_list')
    def get_task_meta(self, task_id: str)->dict: raise NotImplementedError('get_task_meta')
    def set_task_status(self, task_id, result='', status=celery.states.STARTED): raise NotImplementedError('set_task_status')

    def get_task_status(self, task_id: str):
        return self.get_task_meta(task_id).get('status', None)   
    
    def set_task_started(self, task_model: 'ServiceOrientedArchitecture.Model'):
        self.set_task_status(task_model.task_id,task_model.model_dump_json(),celery.states.STARTED)

    def send_data_to_task(self, task_id, data):        
        self.publish(task_id,data)
        
    def listen_data_of_task(self, task_id, data_callback=lambda data: data, eternal=False):
        return self.subscribe(task_id,data_callback,eternal)

class RabbitmqMongoApp(AppInterface, RabbitmqPubSub):
    def __init__(self, rabbitmq_url:str, rabbitmq_user:str, rabbitmq_password:str, 
                 mongo_url:str, mongo_db:str, celery_meta:str, celery_rabbitmq_broker:str, task_pubsub_name='task_updates'):
        super().__init__(rabbitmq_url, rabbitmq_user, rabbitmq_password,task_pubsub_name )
        self.rabbitmq_url = rabbitmq_url
        self.rabbitmq_user = rabbitmq_user
        self.rabbitmq_password = rabbitmq_password

        self.mongo_url = mongo_url
        self.mongo_db = mongo_db
        self.celery_meta = celery_meta
        self.celery_rabbitmq_broker = celery_rabbitmq_broker
        self.task_pubsub_name = task_pubsub_name
        self._store = None
        self.start_listener()
        
    def store(self):
        if self._store is None:
            self._store = BasicStore().mongo_backend(self.mongo_url)
        return self._store

    def get_celery_app(self):
        return celery.Celery(self.mongo_db, broker=self.celery_rabbitmq_broker,
                             backend=f'{self.mongo_url}/{self.mongo_db}')

    def check_rabbitmq_health(self, url=None, user=None, password=None) -> bool:
        if url is None:
            url = f'http://{self.rabbitmq_url}/api/health/checks/alarms'
        try:
            response = requests.get(url, auth=(user, password), timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def check_mongodb_health(self, url=None) -> bool:
        if url is None:
            url = self.mongo_url
        try:
            client = MongoClient(url, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            return True
        except pymongo.errors.ConnectionFailure:
            return False

    def check_services(self) -> bool:
        rabbitmq_health = self.check_rabbitmq_health(user=self.rabbitmq_user, password=self.rabbitmq_password)
        mongodb_health = self.check_mongodb_health()
        return rabbitmq_health and mongodb_health

    def get_tasks_collection(self):
        client = MongoClient(self.mongo_url)
        db = client.get_database(self.mongo_db)
        collection = db.get_collection(self.celery_meta)
        return collection

    def get_tasks_list(self):
        collection = self.get_tasks_collection()
        tasks = []
        for task in collection.find():
            task_data = TaskModel(
                task_id=task.get('_id'),
                status=task.get('status'),
                result=json.dumps(task.get('result')),
                date_done=task.get('date_done')
            )
            tasks.append(task_data)
        return tasks

    def get_task_meta(self, task_id: str):
        collection = self.get_tasks_collection()
        res = collection.find_one({'_id': task_id})
        if res:
            del res['_id']
            return res
        else:
            return None
            
    def set_task_status(self, task_id, result='', status=celery.states.STARTED):
        collection = self.get_tasks_collection()
        collection.update_one(
            {'_id': task_id},
            {'$set': {
                'status': status,
                'result': result
            }},
            upsert=True
        )

class RedisApp(AppInterface, RedisPubSub):
    def __init__(self, redis_url,celery_meta:str='celery-task-meta'):
        super().__init__(redis_url)
        self.celery_meta=celery_meta
        self.redis_url = redis_url
        self._redis_client = None
        self._store = None
        self.start_listener()

    def redis_client(self):
        if self._redis_client is None:
            self._redis_client = redis.Redis.from_url(self.redis_url)
        return self._redis_client

    def store(self):
        if self._store is None:
            self._store = BasicStore().redis_backend()
        return self._store

    def get_celery_app(self):
        return celery.Celery('tasks', broker=self.redis_url, backend=self.redis_url)

    def check_services(self) -> bool:
        """Check Redis connection health."""
        try:
            return self.redis_client().ping()
        except redis.ConnectionError:
            return False

    def get_tasks_collection(self):
        """Returns a list of keys representing tasks in Redis."""
        return self.redis_client().keys(pattern='celery-task-meta-*')

    def get_tasks_list(self):
        """Fetches a list of all tasks stored in Redis."""
        task_keys = self.get_tasks_collection()
        tasks = []

        for key in task_keys:
            task_data_json = self.redis_client().get(key)
            if task_data_json:
                task: dict = json.loads(task_data_json)
                task_data = TaskModel(
                    task_id=task.get('task_id'),
                    status=task.get('status'),
                    result=json.dumps(task.get('result')),
                    date_done=task.get('date_done')
                )
                tasks.append(task_data)
        return tasks

    def get_task_meta(self, task_id: str):
        task_key = f'celery-task-meta-{task_id}'
        task_data_json = self.redis_client().get(task_key)
        if task_data_json:
            task_data = json.loads(task_data_json)
            return task_data
        return None
        
    def set_task_status(self, task_id, result='', status=celery.states.STARTED):
        """Marks a task as started in Redis."""
        task_key = f'celery-task-meta-{task_id}'
        task_data = TaskModel(
                task_id=task_id,
                status=status,
                result=result)
        self.redis_client().set(task_key, json.dumps(task_data.model_dump()))

class FileSystemApp(AppInterface, FileSystemPubSub):
    def __init__(self, base_dir="./FileSystemApp", celery_meta="tasks", task_pubsub_name="FileSystemPubSub"):
        super().__init__(f'{base_dir}/pubsub', task_pubsub_name)
        self.base_dir = base_dir
        self.celery_meta = celery_meta
        self._store = None
        self.start_listener()

        self.broker_in = self.broker_out =os.path.join(self.base_dir, 'celery/broker/')
        self.broker_processed = os.path.join(self.base_dir, 'celery/broker/processed')
        self.backend_dir = os.path.join(self.base_dir, 'celery/results')

        # Create necessary directories
        os.makedirs(self.broker_in, exist_ok=True)
        os.makedirs(self.broker_out, exist_ok=True)
        os.makedirs(self.broker_processed, exist_ok=True)
        os.makedirs(self.backend_dir, exist_ok=True)
        
    def store(self):
        if self._store is None:
            self._store = BasicStore().file_backend(self.backend_dir,ext='')
        return self._store

    def get_celery_app(self):
        return celery.Celery('tasks',
            broker='filesystem://',
            backend=f'file://{self.backend_dir}',
            broker_transport_options={
                'data_folder_in': self.broker_in,
                'data_folder_out': self.broker_out,
                'data_folder_processed': self.broker_processed
            }
        )

    def check_services(self) -> bool:
        try:
            test_file = os.path.join(self.base_dir, "health_check.txt")
            with open(test_file, 'w') as f:
                f.write("ok")
            with open(test_file, 'r') as f:
                content = f.read()
            os.remove(test_file)
            return content == "ok"
        except Exception:
            return False

    def get_tasks_collection(self):
        """Returns list of full paths to celery task metadata files."""
        return self.store().keys("celery-task-meta-*")

    def get_tasks_list(self):
        tasks = []
        for task_full_id in self.get_tasks_collection():
            try:
                task = TaskModel(**self.store().get(task_full_id))
                tasks.append(task)
            except Exception as e:
                print(f"Error reading task {task_full_id}: {e}")
        return tasks

    def get_task_meta(self, task_id: str):
        return self.store().get(f"celery-task-meta-{task_id}")

    def set_task_status(self, task_id, result='', status=celery.states.STARTED):
        task_data = TaskModel(task_id=task_id, status=status, result=result)
        self.store().set(f"celery-task-meta-{task_id}",task_data.model_dump())

class SmartModelConverter(BaseModel):
    """
    A class for building and managing conversion functions between different
    ServiceOrientedArchitecture classes using LLM.
    """
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    
    def model_post_init(self, __context):
        """
        Post initialization validation and setup.
        """
        if self.api_key is None:
            self.api_key = os.environ.get('OPENAI_API_KEY')
            if not self.api_key:
                raise ValueError("API key not found in environment variable 'OPENAI_API_KEY' and not provided")
            
    def build_conversion_prompt(
        self,
        source_class, 
        target_class,
        prompt_template: str = None
    ) -> tuple[str, str]:
        """
        Dynamically build a prompt that requests GPT to write a function
        converting `source_class`'s return to `target_class`'s args.

        Parameters
        ----------
        source_class : ServiceOrientedArchitecture
            The class with a .Model.ret schema to convert from.
        target_class : ServiceOrientedArchitecture
            The class with a .Model.args schema to convert to.
        prompt_template : str, optional
            Custom prompt template to use instead of the default one

        Returns
        -------
        tuple[str, str]
            A tuple of (prompt_text, generated_function_name).
        """
        if prompt_template is None:
            prompt_template = (
                "Please complete the following code and only provide the implementation of the ret to args converter function :\n\n"
                "```{from_class_name}.Model pydanctic schema\n"
                "{from_schema}\n"
                "```\n\n"
                "```{to_class_name}.Model pydanctic schema\n"
                "{to_schema}\n"
                "```\n\n"
                "```python\n"
                "def {from_class_name}{from_class_version}_ret_to_{to_class_name}{from_class_version}_args_convertor(ret,args):\n"
                "    # this function will convert {from_class_name}.ret into {to_class_name}.args\n"
                "    # ...\n"
                "    return args\n"
                "```"
            )

        from_class_name = source_class.__name__
        to_class_name = target_class.__name__
        from_class_version = source_class.Model.Version()
        to_class_version = target_class.Model.Version()

        prompt = prompt_template.format(
            from_class_name=from_class_name,
            from_schema=source_class.Model.Return.model_json_schema(),
            to_class_name=to_class_name,
            to_schema=target_class.Model.Args.model_json_schema(),
            from_class_version=from_class_version,
            to_class_version=to_class_version,
        )

        function_name = self.get_function_name(source_class, target_class)
        return prompt, function_name
    
    def get_function_name(self,source_class, target_class):        
        from_class_name = source_class.__name__
        to_class_name = target_class.__name__
        from_class_version = source_class.Model.Version()
        to_class_version = target_class.Model.Version()
        return f"{from_class_name}{from_class_version}_ret_to_{to_class_name}{to_class_version}_args_convertor"

    def get_func_from_code(self, code_string, function_name):
        """
        Extract a function from a code string.
        
        Parameters
        ----------
        code_string : str
            The code containing the function
        function_name : str
            The name of the function to extract
            
        Returns
        -------
        callable
            The extracted function
        """
        # Execute the extracted code in a new local namespace
        local_namespace = {}
        exec(code_string, globals(), local_namespace)

        # Return the requested function from that namespace
        func = local_namespace.get(function_name)
        if not func:
            raise ValueError(f"Function '{function_name}' not found in the code.")

        return func

    def get_code_from_gpt(self, prompt: str, function_name: str, model: str = None):
        """
        Given a prompt and a function name, this function calls the GPT API and
        extracts the code block containing the function. The code is then
        executed locally, and the specified function is returned as a callable.

        Parameters
        ----------
        prompt : str
            The prompt to send to GPT.
        function_name : str
            The name of the function to extract from GPT's response.
        model : str, optional
            The model to use for this specific request, overriding the default

        Returns
        -------
        tuple[str, callable]
            A tuple containing the extracted code string and the function object.

        Raises
        ------
        ValueError
            If the GPT response is invalid, or if the function is not found in the response.
        """
        model = model or self.model
        
        url = 'https://api.openai.com/v1/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        # Call the GPT API
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        message = response.json()['choices'][0]['message']['content']

        # Attempt to extract the code block
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", message, re.DOTALL)
        if not code_blocks:
            raise ValueError('No code block found in GPT response.')
        code_string = code_blocks[0]

        return code_string, self.get_func_from_code(code_string, function_name)
    
    def build(self, in_class, out_class, model=None, prompt_template=None):
        """
        Build a conversion function between two ServiceOrientedArchitecture classes.
        
        Parameters
        ----------
        in_class : ServiceOrientedArchitecture
            The source class with return values to convert from
        out_class : ServiceOrientedArchitecture
            The target class with args to convert to
        model : str, optional
            The model to use for this specific build, overriding the default
        prompt_template : str, optional
            Custom prompt template to use for this specific build
            
        Returns
        -------
        callable
            The conversion function
        """
        # Build prompt
        prompt_text, function_name = self.build_conversion_prompt(
            in_class, 
            out_class,
            prompt_template
        )

        # Fetch code and function from GPT
        code_snippet, conversion_func = self.get_code_from_gpt(
            prompt_text, 
            function_name,
            model
        )

        return code_snippet, conversion_func
        
    def convert(self, in_class, in_model_instance,
                out_class, out_model_instance,
                model=None, prompt_template=None):

        # Build prompt
        prompt_text, function_name = self.build_conversion_prompt(in_class, out_class, prompt_template)

        # Fetch code and function from GPT
        code_snippet, conversion_func = self.get_code_from_gpt(prompt_text, function_name, model)

        out_model_instance,_ = self.convert_by_function_code(code_snippet, function_name,in_model_instance, out_model_instance)
    
        return out_model_instance, code_snippet, conversion_func 

    def convert_by_function_code(self, function_code, function_name, in_model_instance, out_model_instance):
        """
        Convert a model instance using a function code.
        """
        in_ret_data = in_model_instance.ret.model_dump()
        out_args_data = out_model_instance.args.model_dump() 

        conversion_func = self.get_func_from_code(function_code, function_name)
        # Execute the GPT-provided conversion function
        updated_args = conversion_func(in_ret_data, out_args_data)

        out_model_instance.args = out_model_instance.Args(**updated_args)
        return out_model_instance, conversion_func
    
    def convert_by_function(self, conversion_func, in_model_instance, out_model_instance):
        """
        Convert a model instance using a function code.
        """
        in_ret_data = in_model_instance.ret.model_dump()
        out_args_data = out_model_instance.args.model_dump() 
        
        updated_args = conversion_func(in_ret_data, out_args_data)

        out_model_instance.args = out_model_instance.Args(**updated_args)
        return out_model_instance, conversion_func
        

class ServiceOrientedArchitecture:
    BasicApp:AppInterface = None

    class Model(BaseModel):
        task_id:Optional[str] = Field('AUTO_SET_BUT_NULL_NOW', description="task uuid")

        class Version(BaseModel):
            class_name: str = Field(default='NULL', description="class name")
            major: str = Field(default="1", description="Major version number")
            minor: str = Field(default="0", description="Minor version number")
            patch: str = Field(default="0", description="Patch version number")

            @classmethod
            def get_class_name(cls):
                return cls.__qualname__.split('.')[0]

            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.class_name = self.get_class_name()

            def __repr__(self):
                return self.__str__()
            def __str__(self):
                return f'_v{self.major}{self.minor}{self.patch}_'

        class Param(BaseModel):
            pass
        class Args(BaseModel):
            pass
        class Return(BaseModel):
            pass

        class Logger(BaseModel):
            class Levels:
                ERROR:str='ERROR'
                WARNING:str='WARNING'
                INFO:str='INFO'
                DEBUG:str='DEBUG'
                
            name: str  = "service" # Logger name
            level: str = "INFO"  # Default log level
            logs:str = ''

            _log_buffer: io.StringIO = PrivateAttr()
            _logger: logging.Logger = PrivateAttr()

            def init(self,name:str=None,
                     action_obj:'ServiceOrientedArchitecture.Action'=None):
                if name is None:
                    name = self.name
                # Create a StringIO buffer for in-memory logging
                self._log_buffer = io.StringIO()

                # Configure logging
                self._logger = logging.getLogger(name)
                self._logger.setLevel(
                    getattr(logging, self.level.upper(), logging.INFO))

                # Formatter for log messages
                formatter = logging.Formatter(
                    '%(asctime)s [%(name)s:%(levelname)s] %(message)s')

                # In-Memory Handler
                memory_handler = logging.StreamHandler(self._log_buffer)
                memory_handler.setFormatter(formatter)
                self._logger.addHandler(memory_handler)

                # Console Handler (Optional, remove if not needed)
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                self._logger.addHandler(console_handler)
                return self

            def log(self, level: str, message: str):
                """Logs a message at the specified level."""
                log_method = getattr(self._logger, level.lower(), None)
                if callable(log_method):
                    log_method(message)
                    self.save_logs()
                else:
                    self._logger.error(f"Invalid log level: {level}")

            def info(self, message: str):
                self.log("INFO", message)

            def warning(self, message: str):
                self.log("WARNING", message)

            def error(self, message: str):
                self.log("ERROR", message)

            def debug(self, message: str):
                self.log("DEBUG", message)

            def get_logs(self) -> str:
                """Returns all logged messages stored in memory."""
                return self._log_buffer.getvalue()

            def save_logs(self) -> str:
                """Saves logs to the `logs` attribute."""
                self.logs = self.get_logs()
                return self.logs

            def clear_logs(self):
                """Clears the in-memory log buffer and resets the logger state."""
                self._log_buffer.truncate(0)
                self._log_buffer.seek(0)
                self.logs = ""
                
                # Remove handlers to prevent duplicate logs
                for handler in self._logger.handlers[:]:
                    self._logger.removeHandler(handler)

                
        version:Version = Version()
        param:Param = Param()
        args:Args = Args()
        ret:Optional[Return] = Return()
        logger:Logger = Logger()
        version:Version = Version()

        @classmethod
        def examples(cls): return []
        
        def update_model_data(self,data:dict):
            if data is not None:
                # Update all model components from prior model
                if 'param' in data:
                    self.param = self.param.model_copy(update=data['param'])
                if 'args' in data:
                    self.args = self.args.model_copy(update=data['args'])
                if 'ret' in data:
                    self.ret = self.ret.model_copy(update=data['ret'])
            return self

    class Action:
        def __init__(self, model,BasicApp:AppInterface,level=None):
            outer_class_name:ServiceOrientedArchitecture = self.__class__.__qualname__.split('.')[0]
            if isinstance(model, dict):
                nones = [k for k,v in model.items() if v is None]
                for i in nones:del model[i]
                model = outer_class_name.Model(**model)
            self.model = model
            self.BasicApp = BasicApp
            self.logger = self.model.logger
            if level is None:level=ServiceOrientedArchitecture.Model.Logger.Levels.INFO
            self.logger.level = level
            self.logger.init(
                name=f"{outer_class_name.__class__.__name__}:{self.model.task_id}",action_obj=self)
            self.listen_data_of_task_uuids = []

        def send_data_to_task(self, msg_dict={}):
            self.BasicApp.send_data_to_task(self.model.task_id,msg_dict)

        def listen_data_of_task(self, msg_lambda=lambda msg={}:None,eternal=False):
            id = self.BasicApp.listen_data_of_task(self.model.task_id,msg_lambda,eternal)
            self.listen_data_of_task_uuids.append(id)
            return id

        def set_task_status(self,status):
            self.BasicApp.set_task_status(self.model.task_id,self.model.model_dump_json(),status)

        def get_task_status(self):
            return self.BasicApp.get_task_status(self.model.task_id)

        def stop_service(self):
            task_id=self.model.task_id
            self.BasicApp.send_data_to_task(task_id,{'status': 'REVOKED'})

        def dispose(self):
            for i in self.listen_data_of_task_uuids:
                self.BasicApp.unsubscribe(i)
            
        def __del__(self):
            self.dispose()

        @contextmanager
        def listen_stop_flag(self):            
            # A shared flag to communicate between threads
            stop_flag = threading.Event()

            status = self.get_task_status()
            if status == celery.states.REVOKED:
                stop_flag.set()
                yield stop_flag
            else:
                self.set_task_status(celery.states.STARTED)
                # Function to check if the task should be stopped, running in a separate thread
                def check_task_status(data:dict):
                    if data.get('status',None) == celery.states.REVOKED:
                        self.set_task_status(celery.states.REVOKED)
                        stop_flag.set()
                self.listen_data_of_task(check_task_status,True)
                
                try:
                    yield stop_flag  # Provide the stop_flag to the `with` block
                finally:
                    self.send_data_to_task({})
            return stop_flag

        def __call__(self, *args, **kwargs):
            return self.model
        







        
