# 🧠 Task Queue Backend with FastAPI, Celery, Redis/RabbitMQ, and MongoDB

A modular, plug-and-play backend system built with **FastAPI**, **Celery**, and flexible backends such as **Redis** or **RabbitMQ + MongoDB**, providing asynchronous task execution, scheduling, and a clean API interface.

---

## 🚀 Features

- RESTful API powered by **FastAPI**
- Background task management with **Celery**
- Dynamic backend selection: `redis` or `mongodbrabbitmq`
- RabbitMQ support with `advanced.config` auto-updating
- Monitoring via **Flower**
- Timezone-aware scheduling
- Plug-and-play custom task support

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

## 📦 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/qinhy/QIN-Design-fastapi-celery
   cd QIN-Design-fastapi-celery
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment:**
   - Edit `.env` or `.env.docker` as needed for your setup.

---

## 🐳 Docker Setup

You can run the entire stack using Docker Compose:

```bash
docker-compose up --build
```

This will start:
- Redis (as broker)
- FastAPI app (API server)
- Celery worker
- Flower (monitoring dashboard at port 5555)

---

## 🏗️ Project Structure

- `CustomTask/` — Custom task implementations (e.g., Fibonacci, PrimeNumberChecker, ChatGPTService, etc.)
- `Storages/` — Storage backends (Redis, MongoDB, FileSystem)
- `Task/` — Core task and app interfaces
- `tasks.py` — Main Celery and FastAPI integration, task registration
- `start_server.py` — Entrypoint for running API, Celery worker, or Flower
- `config.py` — Configuration utilities (including RabbitMQ advanced config)
- `docker-compose.yml` & `Dockerfile` — Containerization setup
- `sh/` — Shell and batch scripts for quick start/stop

---

## 🛠️ Quick Start Scripts

### Windows
- Start all services:
  ```bat
  sh\start_all.bat
  ```
- Start only the API server:
  ```bat
  sh\uvicorn.bat
  ```
- Start only Redis:
  ```bat
  sh\redis.bat
  ```

### Linux/macOS
- Start all services:
  ```bash
  bash sh/start_all.sh
  ```
- Stop all services:
  ```bash
  bash sh/stop_all.sh
  ```

---

## 🚦 Usage

- **Start API server:**
  ```bash
  python start_server.py uvicorn
  ```
- **Start Celery worker:**
  ```bash
  python start_server.py celery
  ```
- **Start Flower monitoring:**
  ```bash
  python start_server.py flower
  ```

---

## 🧩 Adding Custom Tasks

To add your own custom task:

1. **Create a new Python file** in the `CustomTask/` directory (e.g., `MyCustomTask.py`).
2. **Define your task class**. Your class should implement the logic you want to run as a task. For example:
   ```python
   # CustomTask/Fibonacci.py
    class Fibonacci(ServiceOrientedArchitecture):
        @classmethod
        def description(cls):
            return """...
   ```
3. **Register your task** in `CustomTask/__init__.py` by importing your class:
   ```python
   from .MyCustomTask import MyCustomTask
   ```
4. **(Optional) Add dependencies** to `requirements.txt` if your task needs extra packages.
5. **Restart the backend** to load your new task.

Your new task will now be available via the API and can be scheduled or called like the built-in tasks. For advanced usage, see the structure of existing tasks in `CustomTask/` and how they are registered in `ACTION_REGISTRY`. If your task needs to interact with storage or other services, you can inject dependencies via the constructor or use the provided storage interfaces in `Storages/`.

---

## 📑 API Endpoints

The API exposes endpoints for submitting tasks, managing pipelines, and querying results. See `tasks.py` for details or use `/docs` when the server is running for interactive documentation.

---

## 📝 License

MIT License. See [LICENSE](LICENSE) for details.