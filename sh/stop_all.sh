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
