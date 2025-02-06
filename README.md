# QIN-Design-fastapi-celery
 QIN Design of fastapi with celery

## Target
- working at both win and linux
- Object-oriented, MVC model.


# FastAPI Celery Microservice

## Overview
This project is a **FastAPI** microservice integrating **Celery** for task management and execution. It supports **Redis** and **MongoDB with RabbitMQ** as backend configurations and provides an API to compute Fibonacci numbers asynchronously.

## Features
- **FastAPI-based API** with **CORS** and **session management**.
- **Celery integration** for background task execution.
- **Redis or MongoDB with RabbitMQ** as backend options.
- **Task management endpoints** to list, track, and revoke tasks.
- **Fibonacci computation service** with an option for fast or recursive mode.
- **Generic task execution framework** for scalable microservice actions.

## Installation

### Prerequisites
- **Python 3.8+**
- **Redis or RabbitMQ with MongoDB**
- **Celery**
- **Uvicorn** (for running FastAPI)
- **Pydantic** (for request validation)

### Install Dependencies
```bash
pip install fastapi celery uvicorn pydantic redis pymongo requests
```

## Configuration

Environment variables can be used to configure backend settings:

```bash
export APP_BACK_END=redis               # Choose between "redis" or "mongodbrabbitmq"
export APP_INVITE_CODE=123
export APP_SECRET_KEY=super_secret_key
export ACCESS_TOKEN_EXPIRE_MINUTES=30
export UVICORN_PORT=8000
export FLOWER_PORT=5555
export RABBITMQ_URL=amqp://localhost
export RABBITMQ_USER=guest
export RABBITMQ_PASSWORD=guest
export MONGO_URL=mongodb://localhost:27017
export MONGO_DB=tasks
export CELERY_RABBITMQ_BROKER=amqp://localhost
export REDIS_URL=redis://localhost:6379/0
```

## Running the Application ( all in one is provided in examples)

### Start FastAPI
```bash
uvicorn tasks:CeleryTask.api --host 0.0.0.0 --port 8000 --reload
```

### Start Celery Worker
For **Redis backend**:
```bash
celery -A tasks.celery_app worker --loglevel=info
```
For **MongoDB with RabbitMQ backend**:
```bash
celery -A tasks.celery_app worker --loglevel=info --broker=$CELERY_RABBITMQ_BROKER
```

### Start Flower (Celery Monitoring Tool)
```bash
celery -A tasks.celery_app flower --port=5555
```

## API Endpoints

### 1. **Get API Documentation**
- **Method:** `GET`
- **URL:** `/`
- **Redirects to:** `/docs` (Swagger UI)

### 2. **List Available Tasks**
- **Method:** `GET`
- **URL:** `/tasks/`
- **Response:** JSON list of available tasks.

### 3. **Get Task Metadata**
- **Method:** `GET`
- **URL:** `/tasks/meta/{task_id}`
- **Response:** Task status and details.

### 4. **Stop a Running Task**
- **Method:** `GET`
- **URL:** `/tasks/stop/{task_id}`
- **Response:** Stops the task execution.

### 5. **List Active Celery Workers**
- **Method:** `GET`
- **URL:** `/workers/`
- **Response:** List of active Celery workers with their statuses.

### 6. **Calculate Fibonacci Number (Async)**
- **Method:** `POST`
- **URL:** `/fibonacci/`
- **Payload:**
```json
{
  "args": {"n": 10},
  "param": {"mode": "fast"}
}
```
- **Response:** `{"task_id": "some-task-id"}`

### 7. **Perform Generic Action**
- **Method:** `POST`
- **URL:** `/action/perform`
- **Payload:**
```json
{
  "name": "Fibonacci",
  "data": {
    "args": {"n": 10}
  }
}
```
- **Response:** `{"task_id": "some-task-id"}`

## Notes
- The Fibonacci function supports **fast (iterative)** and **recursive** modes.
- The API uses **Celery workers** for background task execution.
- You can check task status using `/tasks/meta/{task_id}`.

## License
MIT