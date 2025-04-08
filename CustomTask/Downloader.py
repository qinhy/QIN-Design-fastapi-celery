import threading
import urllib.request
import urllib.error
import os
from typing import Optional
from pydantic import BaseModel, Field
import redis
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class Downloader(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
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
                    "redis_url": "redis://localhost:6379/0"
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
                
                return self.model

        def _download_file(self, url: str, path: str, chunk_size: int, stop_flag: threading.Event):
            """Download a file from the given URL to the specified path."""
            with urllib.request.urlopen(url, timeout=10) as response, open(path, 'wb') as out_file:
                content_length = response.info().get("Content-Length")
                total_size = int(content_length) if content_length else None
                downloaded = 0

                while not stop_flag.is_set():
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    self._report_progress(downloaded, total_size)

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
            with open(file_path, "rb") as f:
                data = f.read()
                r.set(redis_key, data)
            self.send_data_to_task({"INFO": f"File uploaded to Redis with key: {redis_key}"})

        def _handle_specific_exception(self, exception: Exception, url: str, dest_path: str):
            """Handle specific exceptions with appropriate error messages."""
            if isinstance(exception, urllib.error.HTTPError):
                self.handle_exception(f"HTTP Error {exception.code}: {exception.reason} for URL: {url}")
            elif isinstance(exception, urllib.error.URLError):
                self.handle_exception(f"URL Error: {exception.reason} for URL: {url}")
            elif isinstance(exception, FileNotFoundError):
                self.handle_exception(f"Destination path '{dest_path}' is invalid or unwritable.")
            elif isinstance(exception, PermissionError):
                self.handle_exception(f"Permission denied when writing to '{dest_path}'.")
            elif isinstance(exception, redis.RedisError):
                self.handle_exception(f"Redis error: {str(exception)}")
            elif isinstance(exception, OSError):
                self.handle_exception(f"OS Error: {exception.strerror} at '{dest_path}'")
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
