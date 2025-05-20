import os
import re
import base64
import tempfile
import requests


class FileInputHelper:
    @staticmethod
    def resolve_to_local_path(source: str, default_ext: str = ".bin") -> str:
        """
        Resolves a source (file path, URL, or base64) to a temporary local file path.
        """
        if FileInputHelper.is_url(source):
            return FileInputHelper._download_to_temp_file(source, default_ext)
        elif FileInputHelper.is_base64(source):
            return FileInputHelper._decode_base64_to_temp_file(source, default_ext)
        elif os.path.exists(source):
            return source
        else:
            raise ValueError("Unsupported file source: must be a path, URL, or base64 string.")

    @staticmethod
    def is_url(source: str) -> bool:
        return source.startswith("http://") or source.startswith("https://")

    @staticmethod
    def is_base64(source: str) -> bool:
        return bool(re.match(r"^data:[^;]+;base64,", source))

    @staticmethod
    def _download_to_temp_file(url: str, default_ext: str) -> str:
        response = requests.get(url)
        if not response.ok:
            raise ValueError(f"Failed to download from URL: {url}")
        ext = os.path.splitext(url)[-1] or default_ext
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(response.content)
            return tmp.name

    @staticmethod
    def _decode_base64_to_temp_file(data_uri: str, default_ext: str) -> str:
        header, encoded = data_uri.split(',', 1)
        mime = header.split(':')[1].split(';')[0]
        ext = FileInputHelper._mime_to_ext(mime) or default_ext
        data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            return tmp.name

    @staticmethod
    def _mime_to_ext(mime: str) -> str:
        return {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'application/pdf': '.pdf',
            'text/plain': '.txt',
        }.get(mime, '.bin')

    @staticmethod
    def delete_temp_file(path: str):
        """Delete the specified temporary file if it exists."""
        try:
            if os.path.exists(path) and FileInputHelper._is_in_temp_dir(path):
                os.remove(path)
        except Exception as e:
            # Silently ignore or optionally log
            print(f"[Warning] Could not delete temp file {path}: {e}")

    @staticmethod
    def _is_in_temp_dir(path: str) -> bool:
        # Only allow deletion if file resides in temp directory
        return os.path.commonpath([path, tempfile.gettempdir()]) == tempfile.gettempdir()
