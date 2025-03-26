import time
import subprocess
import redis
import os
import sys
from xmlrpc.client import ServerProxy

# === Config ===
REDIS_HOST = "localhost"
REDIS_PORT = 6379
VERSION_KEY = "deployed_version"
SUPERVISOR_URL = "http://localhost:9001/RPC2"
CHECK_INTERVAL = 10  # in seconds

# === Setup Connections ===
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
supervisor = ServerProxy(SUPERVISOR_URL)


# === Version Management ===
def get_kv_version():
    if not r.exists(VERSION_KEY):
        return r.set(VERSION_KEY,get_local_version())        
    return r.get(VERSION_KEY)


def get_local_version():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except Exception as e:
        print("[GIT] Failed to get local commit hash:", e)
        return None


# === Git Operations ===
def git_checkout(commit_hash):
    print(f"[GIT] Checking out commit: {commit_hash}")
    subprocess.run(["git", "fetch"], check=True)
    subprocess.run(["git", "checkout", commit_hash], check=True)


# === Dependency Installer ===
def install_requirements():
    req_file = "requirements.txt"
    if not os.path.exists(req_file):
        print("[PIP] No requirements.txt found, skipping.")
        return

    print("[PIP] Installing dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode == 0:
        print("[PIP] Dependencies installed successfully.")
    else:
        print("[PIP] Error installing dependencies:")
        print(result.stderr)


# === Service Restart ===
def restart_services():
    print("[SUPERVISOR] Restarting all services...")
    # supervisor.supervisor.stopAll()
    # time.sleep(2)
    supervisor.supervisor.restartAll()
    print("[SUPERVISOR] All services restarted.")


# === Full Deploy Flow ===
def deploy(commit_hash):
    print(f"[DEPLOY] Deploying commit {commit_hash}")
    git_checkout(commit_hash)
    install_requirements()
    restart_services()

# === Main Loop ===
def main_loop():
    print("[DEPLOY AGENT] Running. Checking for updates every", CHECK_INTERVAL, "seconds.")
    while True:
        try:
            kv_version = get_kv_version()
            local_version = get_local_version()

            if kv_version and kv_version != local_version:
                print(f"[DEPLOY] New version found in Redis: {kv_version} (current: {local_version})")
                deploy(kv_version)
            else:
                print("[DEPLOY] No update needed. Current version:", local_version)

        except Exception as e:
            print("[ERROR]", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main_loop()
