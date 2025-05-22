# 🧠 Task Queue Backend with FastAPI, Celery, Redis/RabbitMQ, and MongoDB

A modular, plug-and-play backend system built with **FastAPI**, **Celery**, and flexible backends such as **Redis** or **RabbitMQ + MongoDB**, providing asynchronous task execution, scheduling, and a clean API interface.

---

## 🚀 Features

- ✨ RESTful API powered by **FastAPI**
- 🧵 Background task management with **Celery**
- ⚙️ Dynamic backend selection: `redis` or `mongodbrabbitmq`
- 🐇 RabbitMQ support with `advanced.config` auto-updating
- 🌼 Monitoring via **Flower**
- 🕒 Timezone-aware scheduling
- 🔌 Plug-and-play custom task support

---

## 🛠 Tech Stack

| Component      | Tech                     |
|----------------|--------------------------|
| API Framework  | FastAPI, Pydantic        |
| Task Queue     | Celery                   |
| Broker         | Redis or RabbitMQ        |
| Result Backend | Redis or MongoDB         |
| Middleware     | Starlette, CORS, Session |
| Monitoring     | Flower                   |

---

## 📦 Dependencies

Install requirements with:

```bash
pip install -r requirements.txt
```

<details>
<summary>requirements.txt</summary>

```
requests
celery
flower
redis
fastapi
pydantic
pydantic[email]
pydantic-settings
starlette
pymongo
pika
itsdangerous
pytz
uvicorn
...
```

</details>

---

## ⚙️ Configuration

All configuration is driven by environment variables. Create a `.env` file in the root directory:

```env
# Select Backend: redis OR mongodbrabbitmq
APP_BACK_END=redis

# Core App Settings
APP_INVITE_CODE=123
ACCESS_TOKEN_EXPIRE_MINUTES=30
UVICORN_PORT=8000
FLOWER_PORT=5555

# RabbitMQ
RABBITMQ_URL=localhost:15672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_CONSUMER_TIMEOUT=259200000

# MongoDB
MONGO_URL=mongodb://localhost:27017
MONGO_DB=tasks

# Celery
CELERY_CONCURRENCY=4
CELERY_META=celery_taskmeta
CELERY_RABBITMQ_BROKER=amqp://localhost

# Redis
REDIS_URL=redis://localhost:6379/0
```

---

## 📡 Running the App

check folder of /sh/...

---

## 🧪 Sample Task: Fibonacci

The app includes an example `Fibonacci` task with both **immediate** and **scheduled** execution.

### GET Request Example:

```http
GET /myapi/fibonacci/?n=10&mode=fast
```

### POST Endpoint Examples:

```http
POST /fibonacci/
POST /fibonacci/schedule/
```

---

## 📁 Custom Tasks

To define a custom task:

1. Create a class in `CustomTask`
2. Inherit from `ServiceOrientedArchitecture`
3. Define a nested `Model` using Pydantic
4. Your tasks will be auto-registered via reflection

---

## 🧠 Backend Selection Logic

- `redis`: Uses Redis as both broker and backend
- `mongodbrabbitmq`: Uses RabbitMQ + MongoDB; will also validate and optionally update the `advanced.config` to match `RABBITMQ_CONSUMER_TIMEOUT`

---

## 🧰 Dev Utilities

```python
# Access external IP
AppConfig().external_ip

# Automatically fix RabbitMQ's advanced.config
AppConfig().validate_backend()
```

---

## 🌐 API Docs

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Redoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🤝 Contributing

Pull requests welcome! Custom tasks, backend strategies, and plugin systems are especially appreciated.

---

## 📄 License

MIT License. Use freely and improve openly.