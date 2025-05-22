import json
import time
import requests

def get_task_res(id,
    url="http://localhost:8000/tasks/meta/{task_id}",
    timeout=10,):
    url = url.format(task_id=id)
    for i in range(timeout):
        res = requests.get(url)
        if'result' in res.json():
            return res.json()['result']
        time.sleep(1)

def test_fibonacci_fast():
    url = "http://localhost:8000/fibonacci/"  # Replace with actual host if different
    payload = {
        "param": {
            "mode": "fast"
        },
        "args": {
            "n": 13
        }
    }
    params = {
        "execution_time": "NOW",
        "timezone": "Asia/Tokyo"
    }

    response = requests.post(url, json=payload, params=params)
    assert response.status_code == 200
    data = response.json()
    res = json.loads(get_task_res(data['task_id']))
    # You may need to adjust this key based on the actual API response
    assert res["ret"]["n"] == 233  # Fibonacci(13) = 233

def test_http_request_task_get(url,execution_time="NOW"):
    url = "http://localhost:8000/httprequesttask/"
    payload = {
        "param": {
            "method": "GET"
        },
        "args": {
            "url": url
        }
    }
    params = {
        "execution_time": execution_time,
        "timezone": "Asia/Tokyo"
    }

    response = requests.post(url, json=payload, params=params)
    assert response.status_code == 200

    data = response.json()
    task_id = data['task_id']
    assert task_id is not None

    res = json.loads(get_task_res(task_id))

    # Ensure the request was successfully performed
    assert res["ret"]["status_code"] == 200
    assert "httpbin.org" in res["ret"]["content"]

    return task_id

def test_add_pipeline(
    base_url: str = "http://localhost:8000",  # Adjust to your actual host
    pipeline_name: str = "FiboPrime",
    method: str = "POST",
    pipeline: list = ["Fibonacci", "PrimeNumberChecker"]
):
    """
    Sends a POST request to the /pipeline/add endpoint to create a new pipeline.
    """
    url = f"{base_url}/pipeline/add"
    params = {
        "name": pipeline_name,
        "method": method
    }
    json_data = pipeline

    try:
        response = requests.post(url, params=params, json=json_data)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Content:", response.text)
    except Exception as e:
        print("Error:", e)

def test_configure_pipeline(
    base_url: str = "http://localhost:8000",  # Adjust to your server
    pipeline_name: str = "FiboPrime",
    config: list = None
):
    """
    Sends a POST request to the /pipeline/config endpoint to set config for a pipeline.
    """
    if config is None:
        config = [
            {"param": {"mode": "slow"}},
            {"number": "n"},
            {"param": {"mode": "smart"}}
        ]

    url = f"{base_url}/pipeline/config"
    params = {
        "name": pipeline_name
    }

    try:
        response = requests.post(url, params=params, json=config)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Content:", response.text)
    except Exception as e:
        print("Error:", e)

def test_pipeline_FiboPrime(
    url = "http://localhost:8000/pipeline/FiboPrime/",  # Replace with actual host if different
    payload = {
        "args": {
            "n": 13
        }
    },
    params = {
        "execution_time": "NOW",
        "timezone": "Asia/Tokyo"
    }):

    response = requests.post(url, json=payload, params=params)
    assert response.status_code == 200
    data = response.json()
    res = json.loads(get_task_res(data['task_id']))
    # You may need to adjust this key based on the actual API response
    assert res["ret"]["is_prime"] == True  # Fibonacci(13) = 233 , is prime


# def wait_until(t:str, tz='Asia/Tokyo', offset=-10):
#     import time, pytz, datetime
#     z,dd,t = pytz.timezone(tz), datetime.datetime, t[:19]
#     target = z.localize(dd.fromisoformat(t)) - dd.now(z)
#     time.sleep(max(0, target.total_seconds()) + offset)

# def schedule_recurring_requests(
#     url: str,
#     headers: dict,
#     data: dict,
#     start_time: str = 'NOW',
#     timezone: str = "Asia/Tokyo",
#     initial_interval: str = "10 s"
# ) -> None:
#     import requests
#     request_params = {
#         "execution_time": f"{start_time}@every {initial_interval}",
#         "timezone": timezone
#     }
    
#     while True:
#         try:
#             response = requests.post(
#                 url=url,
#                 params=request_params,
#                 headers=headers,
#                 json=data
#             )
#             response.raise_for_status()
#             next_execution_time, next_timezone = response.json()['next_schedule']
#         except requests.RequestException as e:
#             print(f"Error during request: {e}")
#             break

#         request_params.update({
#             "execution_time": next_execution_time,
#             "timezone": next_timezone
#         })
        
#         print(f"Next execution: {next_execution_time} {next_timezone}")
#         wait_until(next_execution_time, next_timezone, offset=-5)


if __name__ == "__main__":
    test_fibonacci_fast()
    test_add_pipeline()
    test_configure_pipeline()
    test_pipeline_FiboPrime()

    