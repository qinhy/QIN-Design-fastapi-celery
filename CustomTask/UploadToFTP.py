import os
import ftplib
import base64  # Import base64 to handle decoding
from typing import Optional
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class UploadToFTP(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Uploads files to FTP servers.
Supports both active and passive FTP modes.
Can create files from base64-encoded content if they don't exist locally.
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            passive_mode: bool = Field(True, description="Whether to use passive mode for FTP connection")

        class Args(BaseModel):
            local_file: str = Field("", description="Path to the local file to upload")
            remote_dir: str = Field("", description="Remote directory path on the FTP server")
            host: str = Field("", description="FTP server hostname")
            username: str = Field("", description="FTP username")
            password: str = Field("", description="FTP password")
            # New field for providing the file content encoded in base64
            local_file_content_b64: Optional[str] = Field(
                "", description="Base64 encoded content to create local_file if it does not exist"
            )

        class Return(BaseModel):
            success: bool = Field(False, description="Whether the upload was successful")
            remote_path: str = Field("", description="Full path where the file was uploaded")
            error_message: str = Field("", description="Error message if upload failed")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{ 
                "param": {"passive_mode": True},
                "args": {
                    "local_file": "example.txt",
                    "remote_dir": "/uploads",
                    "host": "ftp.example.com",
                    "username": "user",
                    "password": "password",
                }
            },
            {
                "param": {"passive_mode": True},
                "args": {
                    "local_file": "/tmp/image_upload.png",
                    "remote_dir": "/images",
                    "host": "ftp.imagehost.com",
                    "username": "imguser",
                    "password": "imgpass",
                    "local_file_content_b64": "iVBORw0KGgoAAAANSUhEUgAAAAUA"  
                }
            }]
        
        version: Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: UploadToFTP.Model = self.model

        def __call__(self, *args, **kwargs):
            # Flag to check if the file is created from base64 content
            temp_created = False
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                local_file = self.model.args.local_file
                remote_dir = self.model.args.remote_dir

                # If the local file does not exist, try to create it using the provided base64 content.
                if not os.path.exists(local_file):
                    if self.model.args.local_file_content_b64:
                        self.log_and_send(f"Local file {local_file} not found; creating from provided base64 content")
                        try:
                            # Decode the base64 content and write it to local_file
                            file_content = base64.b64decode(self.model.args.local_file_content_b64)
                            with open(local_file, "wb") as f:
                                f.write(file_content)
                            temp_created = True
                        except Exception as e:
                            error_msg = f"Failed to create local file from base64 content: {str(e)}"
                            self.log_and_send(error_msg, UploadToFTP.Levels.ERROR)
                            self.model.ret.success = False
                            self.model.ret.error_message = error_msg
                            return self.model
                    else:
                        self.log_and_send(f"Error: Local file {local_file} not found", UploadToFTP.Levels.ERROR)
                        self.model.ret.success = False
                        self.model.ret.error_message = f"Local file {local_file} not found"
                        return self.model

                # Prepare FTP configuration
                ftp_config = {
                    'host': self.model.args.host,
                    'username': self.model.args.username,
                    'password': self.model.args.password
                }
                
                # Calculate remote path
                remote_path = f"{remote_dir}/{os.path.basename(local_file)}"
                self.model.ret.remote_path = remote_path
                
                self.log_and_send(f"Uploading {local_file} to {remote_path}")
                
                try:
                    with ftplib.FTP(ftp_config['host'], ftp_config['username'], ftp_config['password']) as ftp:
                        ftp.set_pasv(self.model.param.passive_mode)
                        
                        # Create remote directory if it doesn't exist
                        try:
                            self.log_and_send(f"Checking if directory {remote_dir} exists")
                            ftp.cwd(remote_dir)
                        except ftplib.error_perm:
                            self.log_and_send(f"Directory {remote_dir} doesn't exist, creating it")
                            ftp.mkd(remote_dir)
                            ftp.cwd(remote_dir)
                        
                        # Upload file
                        with open(local_file, 'rb') as file:
                            self.log_and_send("Uploading file...")
                            ftp.storbinary(f'STOR {os.path.basename(local_file)}', file)
                    
                    self.log_and_send(f"File uploaded successfully to {remote_path}")
                    self.model.ret.success = True
                    return self.model
                    
                except Exception as e:
                    error_msg = f"FTP upload failed: {str(e)}"
                    self.log_and_send(error_msg, UploadToFTP.Levels.ERROR)
                    self.model.ret.success = False
                    self.model.ret.error_message = error_msg
                finally:
                    # Clean up the temporary file if it was created from base64 content
                    if temp_created and os.path.exists(local_file):
                        try:
                            os.unlink(local_file)
                            self.log_and_send(f"Temporary file {local_file} deleted after upload")
                        except Exception as e:
                            self.log_and_send(f"Failed to delete temporary file {local_file}: {e}",
                                              UploadToFTP.Levels.WARNING)
                    return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected, canceling upload.", UploadToFTP.Levels.WARNING)
            self.model.ret.success = False
            self.model.ret.error_message = "Upload canceled by user"
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

######################
# Testing Functions  #
######################

def test_upload_to_ftp():
    """Test function for standard scenarios of UploadToFTP."""
    from unittest.mock import patch, MagicMock
    import tempfile
    import os
    import ftplib
    import uuid

    # Create a temporary file for testing the normal upload scenario
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file_path = temp_file.name
    
    try:
        # Mock BasicApp
        mock_basic_app = MagicMock()
        
        # Create model instance for a successful upload using an existing file
        model = UploadToFTP.Model()
        model.param.passive_mode = True
        model.args.local_file = temp_file_path
        model.args.remote_dir = "/test_uploads"
        model.args.host = "ftp.example.com"
        model.args.username = "testuser"
        model.args.password = "testpass"
        model.args.local_file_content_b64 = ""  # Not used in this test
        
        # Test successful upload with existing file
        with patch('ftplib.FTP') as mock_ftp_class:
            mock_ftp = MagicMock()
            mock_ftp_class.return_value.__enter__.return_value = mock_ftp
            
            action = UploadToFTP.Action(model, mock_basic_app)
            result = action()
            
            assert result.ret.success is True
            assert result.ret.remote_path == f"/test_uploads/{os.path.basename(temp_file_path)}"
            assert result.ret.error_message == ""
            mock_ftp.set_pasv.assert_called_once_with(True)
            mock_ftp.cwd.assert_called_once_with("/test_uploads")
            mock_ftp.storbinary.assert_called_once()
        
        # Test scenario when the file is not found and no base64 content is provided
        model.args.local_file = "/nonexistent/file.txt"
        model.args.local_file_content_b64 = ""
        action = UploadToFTP.Action(model, mock_basic_app)
        result = action()
        assert result.ret.success is False
        assert "not found" in result.ret.error_message.lower()
        
        # Test FTP error handling (simulate permission errors)
        model.args.local_file = temp_file_path
        with patch('ftplib.FTP') as mock_ftp_class:
            mock_ftp = MagicMock()
            mock_ftp_class.return_value.__enter__.return_value = mock_ftp
            mock_ftp.cwd.side_effect = ftplib.error_perm("550 Permission denied")
            mock_ftp.mkd.side_effect = ftplib.error_perm("550 Permission denied")
            
            action = UploadToFTP.Action(model, mock_basic_app)
            result = action()
            
            assert result.ret.success is False
            assert "ftp upload failed" in result.ret.error_message.lower()
        
        print("Standard tests passed!")
    
    finally:
        # Clean up the temporary file if it still exists
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

def test_upload_with_local_file_content_b64():
    """
    Test uploading using base64 content when the file does not already exist.
    This test ensures that the file is created from the base64 data,
    the upload proceeds, and the temporary file is deleted afterwards.
    """
    from unittest.mock import patch, MagicMock
    import tempfile
    import os
    import uuid
    import base64

    # Generate a unique temporary file path that does not exist
    temp_file_path = os.path.join(tempfile.gettempdir(), f"temp_{uuid.uuid4().hex}.txt")
    # Prepare base64 encoded content for the file (e.g., "Hello World")
    file_content = b"Hello World"
    encoded_content = base64.b64encode(file_content).decode('utf-8')

    # Create model instance for upload using base64 content
    model = UploadToFTP.Model()
    model.param.passive_mode = True
    model.args.local_file = temp_file_path
    model.args.remote_dir = "/test_uploads_base64"
    model.args.host = "ftp.example.com"
    model.args.username = "testuser"
    model.args.password = "testpass"
    model.args.local_file_content_b64 = encoded_content

    # Simulate the FTP server behavior using patch
    with patch('ftplib.FTP') as mock_ftp_class:
        mock_ftp = MagicMock()
        mock_ftp_class.return_value.__enter__.return_value = mock_ftp

        mock_basic_app = MagicMock()
        action = UploadToFTP.Action(model, mock_basic_app)
        result = action()

        # Assert that the upload was successful and the remote path is calculated correctly
        assert result.ret.success is True
        assert result.ret.remote_path == f"/test_uploads_base64/{os.path.basename(temp_file_path)}"
        # Check that the FTP upload method was called
        mock_ftp.storbinary.assert_called_once()
        # Verify that the temporary file has been deleted after the upload
        assert not os.path.exists(temp_file_path)

    print("Base64 content file upload test passed!")

if __name__ == "__main__":
    test_upload_to_ftp()
    test_upload_with_local_file_content_b64()
