from celery import Celery, Task
from time import sleep
import random
from celery import chain, group, chord
from typing import Dict, List, Any
from collections import defaultdict
import re
import json
from collections import defaultdict, deque
from typing import Any, Dict, List
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

app = Celery('mock_pipeline', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

def mock_output(name, delay=0.2):
    def wrapper(config):
        sleep(delay)  # simulate work
        print(f"✅ {name} executed with config: {config}")
        return {f"{name.lower()}_output": random.randint(100, 999)}
    return wrapper

@app.task(name="StoreSharedResult")
def StoreSharedResult(tag: str, data: dict):
    redis_client.set(tag, json.dumps(data))
    return tag  # pass the tag forward if needed

@app.task(name="LoadSharedResult")
def LoadSharedResult(tag: str):
    return json.loads(redis_client.get(tag))

@app.task(name="LoadCSV")
def LoadCSV(config):
    return mock_output("LoadCSV")(config)

@app.task(name="LoadJSON")
def LoadJSON(config):
    return mock_output("LoadJSON")(config)

@app.task(name="CleanData")
def CleanData(config):
    return mock_output("CleanData")(config)

@app.task(name="Normalize")
def Normalize(config):
    return mock_output("Normalize")(config)

@app.task(name="MergeData")
def MergeData(config):
    return mock_output("MergeData")(config)

@app.task(name="FeatureExtract")
def FeatureExtract(config):
    return mock_output("FeatureExtract")(config)

@app.task(name="MLModel")
def MLModel(config):
    return mock_output("MLModel")(config)

@app.task(name="ExplainModel")
def ExplainModel(config):
    return mock_output("ExplainModel")(config)

@app.task(name="ArchiveOutput")
def ArchiveOutput(config):
    return mock_output("ArchiveOutput")(config)

@app.task(name="ChatGPT")
def ChatGPT(config):
    return mock_output("ChatGPT")(config)