import numpy as np
import requests
import time
from Task.Basic import AppInterface,RedisApp,RabbitmqMongoApp

from Task.Customs import ServiceOrientedArchitecture
from Config import APP_BACK_END, SESSION_DURATION, APP_SECRET_KEY, RABBITMQ_URL, MONGO_URL, MONGO_DB, CELERY_META, CELERY_RABBITMQ_BROKER, RABBITMQ_USER, RABBITMQ_PASSWORD, REDIS_URL
if APP_BACK_END=='redis':
    BasicApp:AppInterface = RedisApp(REDIS_URL)
elif APP_BACK_END=='mongodbrabbitmq':
    BasicApp:AppInterface = RabbitmqMongoApp(RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,
                                             MONGO_URL,MONGO_DB,CELERY_META,
                                             CELERY_RABBITMQ_BROKER)
else:
    raise ValueError(f'no back end of {APP_BACK_END}')
ServiceOrientedArchitecture.BasicApp  = BasicApp

from Task.Basic import BidirectionalStream, NumpyUInt8SharedMemoryIO, RedisIO
from Vison.BasicModel import NumpyUInt8SharedMemoryStreamIO

BASE_URL = "http://localhost:8000"  # Adjust as necessary for your server

def test_calculate_fibonacci():
    response = requests.post(f"{BASE_URL}/fibonacci/", json={"n": 10})
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data, "Task ID not found in response."
    task_id = data["task_id"]
    print(f"Fibonacci task started with ID: {task_id}")
    return task_id

def test_task_status(task_id):
    # Check the status of the task after giving it some time to process
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/tasks/status/{task_id}")
    assert response.status_code == 200, "Failed to get task status."
    data = response.json()
    assert "status" in data, "Task status not found in response."
    print(f"Task status for ID {task_id}: {data}")
    return data

# task_id = test_calculate_fibonacci()
# test_task_status(task_id)


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

test_NumpyUInt8SharedMemoryIO()
test_redisIO()
test_BidirectionalStream()
