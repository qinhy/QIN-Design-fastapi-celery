import threading
import os
from typing import Optional
from pydantic import BaseModel, Field
import redis
import requests

try:
    from Task.Basic import ServiceOrientedArchitecture
    from Task.UserModel import FileSystem
    from .utils import FileInputHelper
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper

class Downloader(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Downloads files from specified URLs to local storage.
Supports configurable chunk sizes for efficient downloading.
Optionally uploads downloaded files to Redis and removes local copies.
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass
    class Model(ServiceOrientedArchitecture.Model):

        class Param(ServiceOrientedArchitecture.Model.Param):
            chunk_size: int = Field(8192, description="Size of each data chunk in bytes")
            redis_url: Optional[str] = Field(None, description="Redis connection URL, e.g., redis://localhost:6379/0, if provided, the file will be uploaded to Redis and deleted from local storage.")

        class Args(BaseModel):
            url: str = Field(default="http://example.com/sample.txt", description="The URL of the file to download")
            destination_path: str = Field(default="sample.txt", description="Where to temporarily save the file before uploading to Redis")

        class Return(BaseModel):
            success: bool = Field(False, description="Whether the download and Redis upload succeeded")
            message: str = Field("", description="Status or error message")            
            file_path: str = Field("", description="Path to the downloaded file or Redis key if uploaded to Redis. Example: '/path/to/file.txt' for local file or 'redis://localhost:6379/0:web:example.com:sample.txt' for Redis key")

        
        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{
                "param": {
                    "chunk_size": 4096,
                },
                "args": {
                    "url": "http://example.com/sample.txt",
                    "destination_path": "sample.txt"
                }
            },
            {
                "param": {
                    "chunk_size": 8192,
                    "redis_url": None
                },
                "args": {
                    "url": "https://www.python.org/static/img/python-logo.png",
                    "destination_path": "python-logo.png"
                }
            },
            {
                "param": {
                    "chunk_size": 16384,
                    "redis_url": "redis://redis-server:6379/1"
                },
                "args": {
                    "url": "https://github.com/downloads/example/data.zip",
                    "destination_path": "/tmp/downloads/data.zip"
                }
            },
            {
                "param": {
                    "chunk_size": 2048,
                    "redis_url": None
                },
                "args": {
                    "url": "http://speedtest.ftp.otenet.gr/files/test10Mb.db",
                    "destination_path": "test_download.db"
                }
            }]

        version:Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp=None, level=None):
            super().__init__(model, BasicApp, level)
            self.model: Downloader.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                url = self.model.args.url
                dest_path = self.model.args.destination_path
                chunk_size = self.model.param.chunk_size
                redis_url = self.model.param.redis_url

                self.log_and_send(f"Starting download from {url} to {dest_path}")

                try:
                    # Download the file
                    self._download_file(url, dest_path, chunk_size, stop_flag)
                    if stop_flag.is_set():
                        return self.to_stop()

                    # Process the downloaded file
                    self._process_downloaded_file(url, dest_path, redis_url)
                    
                except Exception as e:
                    self._handle_specific_exception(e, url, dest_path)
                
                if hasattr(self.model.param,'user'):
                    self.model.param.user = None
                return self.model
            
        def _fs(self)->FileSystem:
            fs = FileSystem()
            if hasattr(self.model.param,'user') and hasattr(self.model.param.user,'file_system'):
                fs = self.model.param.user.file_system
            return fs

        def _download_file(
            self,
            url: str,
            path: str,
            chunk_size: int,
            stop_flag: threading.Event
        ):
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0 Safari/537.36"
                )
            }
            try:
                with requests.get(url, headers=headers, stream=True, timeout=10) as resp:
                    resp.raise_for_status()
                    total_size = (
                        int(resp.headers.get("Content-Length", 0))
                        if resp.headers.get("Content-Length")
                        else None
                    )
                    downloaded = 0

                    with self._fs().open_for_write(path, "wb") as out_file:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if stop_flag.is_set():
                                break
                            if not chunk:
                                break
                            out_file.write(chunk)
                            downloaded += len(chunk)
                            self._report_progress(downloaded, total_size)

            except requests.exceptions.HTTPError as e:
                print(f"→ HTTPError {e.response.status_code}: {e.response.reason}")
                print("→ Response headers:")
                for k, v in e.response.headers.items():
                    print(f"   {k}: {v}")
                print("→ Partial response body (first 200 chars):")
                print(e.response.text[:200])
                raise
            except Exception:
                raise

        def _report_progress(self, downloaded: int, total_size: Optional[int]):
            """Report download progress to the task."""
            if total_size:
                percent = (downloaded / total_size) * 100
                self.send_data_to_task({"INFO": f"Download progress: {percent:.2f}%"})
            else:
                self.send_data_to_task({"INFO": f"Downloaded {downloaded} bytes..."})

        def _process_downloaded_file(self, url: str, dest_path: str, redis_url: Optional[str]):
            """Process the downloaded file, optionally storing it in Redis."""
            redis_key = self.model.args.url
            
            if redis_url:
                # redis_key = os.path.basename(urlparse(url).path)
                redis_key = redis_key.replace("http://","web:").replace("https://","web:").replace("/",":")
                self.store_file_to_redis(redis_url, redis_key, dest_path)

                if os.path.exists(dest_path):
                    os.remove(dest_path)
                    self.log_and_send(f"Deleted local file: {dest_path}")
                
                # Set the file_path to the Redis key with redis_url prefix
                self.model.ret.file_path = f"{redis_url}:{redis_key}"
            else:
                # Set the file_path to the local file path
                self.model.ret.file_path = dest_path

            # Update return values
            self.model.ret.success = True
            success_message = "Download complete"

            if redis_url:
                success_message += f" and uploaded to Redis with key: {redis_key}"
                
            self.model.ret.message = success_message
            self.log_and_send(self.model.ret.message)

        def store_file_to_redis(self, redis_url: str, redis_key: str, file_path: str):
            """Store a file in Redis."""
            self.log_and_send(f"Uploading file to Redis ({redis_key}) via {redis_url}")
            r = redis.from_url(redis_url)
            with self._fs().open_for_read(file_path, "rb") as f:
                data = f.read()
                r.set(redis_key, data)
            self.send_data_to_task({"INFO": f"File uploaded to Redis with key: {redis_key}"})

        def _handle_specific_exception(
            self, exception: Exception, url: str, dest_path: str
        ):
            """Handle specific exceptions with appropriate error messages."""
            # 1) requests’ HTTP errors (e.g. status codes 4xx/5xx)
            if isinstance(exception, requests.exceptions.HTTPError):
                # requests.exceptions.HTTPError has a .response attribute
                status_code = (
                    exception.response.status_code
                    if exception.response is not None
                    else "?"
                )
                reason = (
                    exception.response.reason
                    if exception.response is not None
                    else str(exception)
                )
                self.handle_exception(
                    f"HTTP Error {status_code}: {reason} for URL: {url}"
                )

            # 2) Any other requests‐level error (ConnectionError, Timeout, etc.)
            elif isinstance(exception, requests.exceptions.RequestException):
                # .args or str(exception) will capture the underlying message
                self.handle_exception(
                    f"Request Error: {str(exception)} for URL: {url}"
                )

            # 3) Filesystem errors
            elif isinstance(exception, FileNotFoundError):
                self.handle_exception(
                    f"Destination path '{dest_path}' is invalid or unwritable."
                )
            elif isinstance(exception, PermissionError):
                self.handle_exception(
                    f"Permission denied when writing to '{dest_path}'."
                )

            # 4) Redis errors (if you’re caching or storing metadata)
            elif isinstance(exception, redis.RedisError):
                self.handle_exception(f"Redis error: {str(exception)}")

            # 5) Any other OS‐level error
            elif isinstance(exception, OSError):
                # OSError.strerror can be None in some cases; fall back to str(exception)
                errmsg = exception.strerror if exception.strerror else str(exception)
                self.handle_exception(f"OS Error: {errmsg} at '{dest_path}'")

            # 6) Anything else
            else:
                self.handle_exception(f"Unexpected error: {str(exception)}")

        def handle_exception(self, message: str):
            """Handle exceptions by logging and updating the model."""
            self.log_and_send(message, Downloader.Levels.ERROR)
            self.model.ret.success = False
            self.model.ret.message = message
            self.model.ret.file_path = ""

        def to_stop(self):
            """Handle stop flag being set."""
            self.log_and_send("Stop flag detected. Download halted.", Downloader.Levels.WARNING)
            self.model.ret.success = False
            self.model.ret.message = "Download stopped by user."
            self.model.ret.file_path = ""
            return self.model

        def log_and_send(self, message: str, level=None):
            """Log a message and send it to the task."""
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


# Simple test code for the Downloader class
if __name__ == "__main__":
    # Create a model instance
    model = Downloader.Model()
    
    # Configure the model
    model.args.url = "https://www.python.org/static/img/python-logo.png"
    model.args.destination_path = "python-logo.png"
    model.param.chunk_size = 4096
    
    action = Downloader.Action(model)
    
    # Execute the download
    print("Starting download test...")
    result = action()
    
    # Print the result
    print(f"Download success: {result.ret.success}")
    print(f"Message: {result.ret.message}")
    print(f"File path: {result.ret.file_path}")
    
    # Test with Redis if available
    print("\nTesting with Redis...")
    model.param.redis_url = "redis://localhost:6379/0"
    result = action()
    print(f"Redis upload success: {result.ret.success}")
    print(f"Message: {result.ret.message}")
    print(f"Redis key: {result.ret.file_path}")
