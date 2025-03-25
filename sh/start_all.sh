#!/bin/bash

mkdir -p logs pids

echo "Starting Uvicorn..."
nohup python3 ..\start_server.py uvicorn > logs/uvicorn.log 2>&1 &
echo $! > pids/uvicorn.pid

echo "Starting Flower..."
nohup python3 ..\start_server.py flower > logs/flower.log 2>&1 &
echo $! > pids/flower.pid

echo "Starting Redis..."
nohup redis-server > logs/redis.log 2>&1 &
echo $! > pids/redis.pid

echo "Starting Celery..."
nohup python3 ..\start_server.py celery > logs/celery.log 2>&1 &
echo $! > pids/celery.pid

echo "All services started."
