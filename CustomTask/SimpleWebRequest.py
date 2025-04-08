import requests
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class SimpleWebRequest(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            timeout: int = Field(30, description="Request timeout in seconds")
            verify_ssl: bool = Field(True, description="Whether to verify SSL certificates")

        class Args(BaseModel):
            url: str = Field("", description="URL to send the request to")
            method: Literal['GET', 'POST', 'PUT', 'DELETE'] = Field("GET", description="HTTP method to use")
            headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers to include")
            data: Dict[str, Any] = Field(default_factory=dict, description="Data to send in the request body")

        class Return(BaseModel):
            status_code: int = Field(-1, description="HTTP status code of the response")
            success: bool = Field(False, description="Whether the request was successful")
            response_text: str = Field("", description="Text content of the response")
            response_json: Dict[str, Any] = Field(default_factory=dict, description="JSON content of the response if available")
            error_message: str = Field("", description="Error message if request failed")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass        
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{ 
                "param": {"timeout": 30, "verify_ssl": True},
                "args": {
                    "url": "https://jsonplaceholder.typicode.com/posts/1",
                    "method": "GET",
                    "headers": {"Content-Type": "application/json"},
                    "data": {}
                }
            }]
        
        version:Version = Version()
        param:Param = Param()
        args:Args = Args()
        ret:Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model:SimpleWebRequest.Model = self.model
            
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                url = self.model.args.url
                method = self.model.args.method
                headers = self.model.args.headers
                data = self.model.args.data
                timeout = self.model.param.timeout
                verify_ssl = self.model.param.verify_ssl

                self.log_and_send(f"Sending {method} request to {url}")
                
                try:
                    response = self._make_request(
                        url=url,
                        method=method,
                        headers=headers,
                        data=data,
                        timeout=timeout,
                        verify=verify_ssl,
                        stop_flag=stop_flag
                    )
                    
                    if stop_flag.is_set():
                        return self.to_stop()
                    
                    self.model.ret.status_code = response.status_code
                    self.model.ret.success = 200 <= response.status_code < 300
                    self.model.ret.response_text = response.text
                    
                    # Try to parse JSON response
                    try:
                        self.model.ret.response_json = response.json()
                    except ValueError:
                        self.log_and_send("Response is not valid JSON", SimpleWebRequest.Levels.WARNING)
                    
                    self.log_and_send(f"Request completed with status code {response.status_code}")
                    
                except Exception as e:
                    error_msg = f"Request failed: {str(e)}"
                    self.log_and_send(error_msg, SimpleWebRequest.Levels.ERROR)
                    self.model.ret.success = False
                    self.model.ret.error_message = error_msg

            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, returning empty response.", SimpleWebRequest.Levels.WARNING)
            self.model.ret.error_message = "Operation was stopped"
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

        def _make_request(self, url, method, headers, data, timeout, verify, stop_flag):
            """Makes the HTTP request with the specified parameters."""
            if stop_flag.is_set():
                raise Exception("Operation was stopped")
                
            if method == "GET":
                return requests.get(url=url, headers=headers, params=data, timeout=timeout, verify=verify)
            elif method == "POST":
                return requests.post(url=url, headers=headers, json=data, timeout=timeout, verify=verify)
            elif method == "PUT":
                return requests.put(url=url, headers=headers, json=data, timeout=timeout, verify=verify)
            elif method == "DELETE":
                return requests.delete(url=url, headers=headers, json=data, timeout=timeout, verify=verify)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")


# Unit tests for SimpleWebRequest
import unittest
from unittest.mock import patch, MagicMock, Mock
import threading

class TestSimpleWebRequest(unittest.TestCase):
    
    def setUp(self):
        self.model = SimpleWebRequest.Model()
        self.model.args.url = "https://jsonplaceholder.typicode.com/posts"
        self.model.args.method = "GET"
        self.model.args.headers = {"Content-Type": "application/json"}
        self.model.args.data = {"userId": 1}
        self.model.param.timeout = 10
        self.model.param.verify_ssl = True
        
        self.basic_app_mock = MagicMock()
        self.action = SimpleWebRequest.Action(self.model, self.basic_app_mock)
        
    @patch('requests.get')
    def test_successful_get_request(self, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": 1, "title": "Test Post", "body": "Content"}'
        mock_response.json.return_value = {"id": 1, "title": "Test Post", "body": "Content"}
        mock_get.return_value = mock_response
        
        # Execute action
        result = self.action()
        
        # Verify request was made with correct parameters
        mock_get.assert_called_once_with(
            url="https://jsonplaceholder.typicode.com/posts",
            headers={"Content-Type": "application/json"},
            params={"userId": 1},
            timeout=10,
            verify=True
        )
        
        # Verify response was processed correctly
        self.assertEqual(result.ret.status_code, 200)
        self.assertTrue(result.ret.success)
        self.assertEqual(result.ret.response_text, '{"id": 1, "title": "Test Post", "body": "Content"}')
        self.assertEqual(result.ret.response_json, {"id": 1, "title": "Test Post", "body": "Content"})
        
    @patch('requests.post')
    def test_post_request(self, mock_post):
        # Setup for POST request
        self.model.args.method = "POST"
        self.model.args.data = {"title": "New Post", "body": "Post content", "userId": 1}
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = '{"id": 101, "title": "New Post", "body": "Post content", "userId": 1}'
        mock_response.json.return_value = {"id": 101, "title": "New Post", "body": "Post content", "userId": 1}
        mock_post.return_value = mock_response
        
        # Execute action
        result = self.action()
        
        # Verify request was made with correct parameters
        mock_post.assert_called_once_with(
            url="https://jsonplaceholder.typicode.com/posts",
            headers={"Content-Type": "application/json"},
            json={"title": "New Post", "body": "Post content", "userId": 1},
            timeout=10,
            verify=True
        )
        
        # Verify response was processed correctly
        self.assertEqual(result.ret.status_code, 201)
        self.assertTrue(result.ret.success)
        self.assertEqual(result.ret.response_json, {"id": 101, "title": "New Post", "body": "Post content", "userId": 1})
        
    @patch('requests.get')
    def test_request_error(self, mock_get):
        # Setup mock to raise exception
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        # Execute action
        result = self.action()
        
        # Verify error handling
        self.assertFalse(result.ret.success)
        self.assertEqual(result.ret.error_message, "Request failed: Connection refused")
        
    @patch('requests.get')
    def test_invalid_json_response(self, mock_get):
        # Setup mock with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Not JSON"
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        # Execute action
        result = self.action()
        
        # Verify handling of invalid JSON
        self.assertTrue(result.ret.success)  # Request was still successful
        self.assertEqual(result.ret.response_text, "Not JSON")
        self.assertEqual(result.ret.response_json, {})
        
    def test_stop_flag(self):
        # Create a mock stop flag that's already set
        stop_flag = threading.Event()
        stop_flag.set()
        
        # Mock the listen_stop_flag context manager
        self.action.listen_stop_flag = MagicMock()
        self.action.listen_stop_flag.return_value.__enter__.return_value = stop_flag
        
        # Execute action
        result = self.action()
        
        # Verify early return due to stop flag
        self.assertEqual(result.ret.error_message, "Operation was stopped")
        
    def test_unsupported_method(self):
        # Setup invalid method
        self.model.args.method = "PATCH"  # Not supporte

if __name__ == "__main__":
    unittest.main()
