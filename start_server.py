import os
import subprocess
import uvicorn
import sys
from config import AppConfig
from tasks import celery_app


def start_celery():
    conf = AppConfig()
    argv = [
        'worker',
        '--loglevel=info',
        f'--concurrency={conf.celery.concurrency}',
        '--pool=threads'
    ]
    celery_app.worker_main(argv)


def start_flower():
    conf = AppConfig()
    subprocess.run([
        "celery",
        "-A", "tasks.celery_app",
        "flower",
        f"--url_prefix=flower",
        f"--port={conf.flower_port}"
    ])


def start_uvicorn():
    conf = AppConfig()
    uvicorn.run(
        "tasks:api",  # Make sure this points to your FastAPI app
        host="0.0.0.0",
        port=conf.uvicorn_port,
        reload=False
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run.py [uvicorn|celery|flower]")
        sys.exit(1)

    arg = sys.argv[1].lower()

    if arg == "uvicorn":
        start_uvicorn()
    elif arg == "celery":
        start_celery()
    elif arg == "flower":
        if "tasks.py" not in os.listdir():
            os.chdir('..')
        start_flower()
    else:
        print(f"Unknown command: {arg}")
        print("Usage: python run.py [uvicorn|celery|flower]")
        sys.exit(1)
