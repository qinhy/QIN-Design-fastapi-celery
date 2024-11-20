import requests
import time

BASE_URL = "http://localhost:8000"  # Adjust as necessary for your server

def test_calculate_fibonacci():
    response = requests.post(f"{BASE_URL}/fibonacci/", json={"n": 10})
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data, "Task ID not found in response."
    task_id = data["task_id"]
    print(f"Fibonacci task started with ID: {task_id}")
    return task_id

def test_task_status(task_id):
    # Check the status of the task after giving it some time to process
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/tasks/status/{task_id}")
    assert response.status_code == 200, "Failed to get task status."
    data = response.json()
    assert "status" in data, "Task status not found in response."
    print(f"Task status for ID {task_id}: {data}")
    return data

# Run the tests sequentially
if __name__ == "__main__":
    task_id = test_calculate_fibonacci()
    test_task_status(task_id)
