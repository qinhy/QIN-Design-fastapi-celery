@echo off
start ..\bin\redis\redis-server.exe
start python ..\start_server.py uvicorn
start python ..\start_server.py flower
start python ..\start_server.py celery




