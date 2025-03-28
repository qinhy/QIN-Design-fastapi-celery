# from https://github.com/qinhy/singleton-key-value-storage.git
import fnmatch
import uuid
import json
import uuid
import json
from pathlib import Path

try:
    from .Storage import SingletonKeyValueStorage,AbstractStorageController
except Exception as e:
    from Storage import SingletonKeyValueStorage,AbstractStorageController


def try_if_error(func):
    try:
        func()
    except Exception as e:
        print(e)
        return e

class SingletonFileSystemStorage:
    _instance = None
    _meta = {}

    def __new__(cls, storage_dir=None):
        if cls._instance is not None and cls._meta.get('storage_dir') == storage_dir:
            return cls._instance

        if storage_dir is None:
            raise ValueError("storage_dir must be provided the first time")

        if cls._instance is not None and cls._meta.get('storage_dir') != storage_dir:
            print(f'warning: storage instance changed to directory {storage_dir}')

        storage_path = Path(storage_dir).resolve()
        storage_path.mkdir(parents=True, exist_ok=True)

        cls._instance = super(SingletonFileSystemStorage, cls).__new__(cls)
        cls._instance.uuid = uuid.uuid4()
        cls._instance.storage_dir = storage_path
        cls._meta['storage_dir'] = str(storage_path)

        return cls._instance

    def __init__(self, storage_dir=None):
        self.uuid: str = self.uuid
        self.storage_dir: Path = self.storage_dir

class SingletonFileSystemStorageController(AbstractStorageController):
    def __init__(self, model: SingletonFileSystemStorage):
        self.model:SingletonFileSystemStorage = model

    def _get_file_path(self, key: str) -> Path:
        # Sanitize key to avoid path traversal, e.g., "some/../path"
        safe_key = key.replace('/', '_').replace('\\', '_')
        return self.model.storage_dir / f"{safe_key}.json"

    def exists(self, key: str) -> bool:
        return self._get_file_path(key).exists()

    def set(self, key: str, value: dict):
        path = self._get_file_path(key)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(value, f)

    def get(self, key: str) -> dict:
        path = self._get_file_path(key)
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def delete(self, key: str):
        path = self._get_file_path(key)
        if path.exists():
            path.unlink()

    def keys(self, pattern: str = '*') -> list[str]:
        all_keys = [f.stem for f in self.model.storage_dir.glob('*.json')]
        return fnmatch.filter(all_keys, pattern)

SingletonKeyValueStorage.backs['file']=lambda *args,**kwargs:SingletonFileSystemStorageController(SingletonFileSystemStorage(*args,**kwargs))

