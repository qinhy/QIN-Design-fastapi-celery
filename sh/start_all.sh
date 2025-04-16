#!/bin/bash

mkdir -p logs pids
#!/bin/bash

echo "Stopping services..."

for pidfile in pids/*.pid; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        echo "Killing process $pid from $pidfile"
        kill "$pid" && rm "$pidfile"
    fi
done

echo "All services stopped."

echo "Starting Uvicorn..."
nohup python3 ../start_server.py uvicorn > logs/uvicorn.log 2>&1 &
echo $! > pids/uvicorn.pid

echo "Starting Flower..."
nohup python3 ../start_server.py flower > logs/flower.log 2>&1 &
echo $! > pids/flower.pid

echo "Starting Redis..."
nohup redis-server --maxmemory 32mb --maxmemory-policy allkeys-lru --save "" --appendonly no --maxclients 50 > logs/redis.log 2>&1 &
echo $! > pids/redis.pid

echo "Starting Celery..."
nohup python3 ../start_server.py celery > logs/celery.log 2>&1 &
echo $! > pids/celery.pid

echo "All services started."
