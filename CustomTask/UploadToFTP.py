import os
import ftplib
from typing import Optional
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class UploadToFTP(ServiceOrientedArchitecture):
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
                    "password": "password"
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
            self.model:UploadToFTP.Model = self.model
            
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                local_file = self.model.args.local_file
                remote_dir = self.model.args.remote_dir
                
                # Check if local file exists
                if not os.path.exists(local_file):
                    self.log_and_send(f"Error: Local file {local_file} not found", UploadToFTP.Levels.ERROR)
                    self.model.ret.success = False
                    self.model.ret.error_message = f"Local file {local_file} not found"
                    return self.model
                
                # Prepare FTP config
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
                        
                        # Create directory if it doesn't exist
                        try:
                            self.log_and_send(f"Checking if directory {remote_dir} exists")
                            ftp.cwd(remote_dir)
                        except ftplib.error_perm:
                            self.log_and_send(f"Directory {remote_dir} doesn't exist, creating it")
                            ftp.mkd(remote_dir)
                            ftp.cwd(remote_dir)
                        
                        # Upload file
                        with open(local_file, 'rb') as file:
                            self.log_and_send(f"Uploading file...")
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

def test_upload_to_ftp():
    """Test function for UploadToFTP"""
    # Create a service instance
    from unittest.mock import patch, MagicMock
    import tempfile
    import os
    import ftplib
    
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file_path = temp_file.name
    
    try:
        # Mock BasicApp
        mock_basic_app = MagicMock()
        
        # Create model instance
        model = UploadToFTP.Model()
        model.param.passive_mode = True
        model.args.local_file = temp_file_path
        model.args.remote_dir = "/test_uploads"
        model.args.host = "ftp.example.com"
        model.args.username = "testuser"
        model.args.password = "testpass"
        
        # Test successful upload
        with patch('ftplib.FTP') as mock_ftp_class:
            # Configure mock FTP instance
            mock_ftp = MagicMock()
            mock_ftp_class.return_value.__enter__.return_value = mock_ftp
            
            # Create action instance
            action = UploadToFTP.Action(model, mock_basic_app)
            
            # Execute action
            result = action()
            
            # Verify results
            assert result.ret.success is True
            assert result.ret.remote_path == f"/test_uploads/{os.path.basename(temp_file_path)}"
            assert result.ret.error_message == ""
            
            # Verify FTP interactions
            mock_ftp.set_pasv.assert_called_once_with(True)
            mock_ftp.cwd.assert_called_once_with("/test_uploads")
            mock_ftp.storbinary.assert_called_once()
        
        # Test file not found
        model.args.local_file = "/nonexistent/file.txt"
        action = UploadToFTP.Action(model, mock_basic_app)
        result = action()
        assert result.ret.success is False
        assert "not found" in result.ret.error_message.lower()
        
        # Test FTP error
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
        
        print("All tests passed!")
    
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

if __name__ == "__main__":
    test_upload_to_ftp()
