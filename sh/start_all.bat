@echo off
start ..\bin\redis\redis-server.exe --maxmemory 32mb --maxmemory-policy allkeys-lru --save "" --appendonly no --maxclients 50
start python ..\start_server.py uvicorn
start python ..\start_server.py flower
start python ..\start_server.py celery




