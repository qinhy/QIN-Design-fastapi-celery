from typing import Any, List, Tuple, Union
import numpy as np
import threading
import time
import uuid
import os
import shutil
import threading
import numpy as np
import os
import shutil
import uuid
from pydantic import BaseModel, Field

class NumpyDualBufferDiskBackedQueue(BaseModel):
    image_shape: Tuple[int, ...]
    buffer_capacity: int
    dtype: str = 'uint8'
    is_init:bool = False
    base_dirs: List[str] = Field(default_factory=lambda: ["D:/data","C:/data"])

    active_buffer:str = 'A'  # start writing to buffer A
    write_index:int = 0
    total_images_written:int = 0
    total_images_read:int = 0
    next_buffer_id_to_save:int = 0  # increments every time we save a full buffer
    next_buffer_id_to_overwrite:int = 0  # track how many buffers have been overwritten
    storage_dirs:list = []
    remaining_space:list = []  # in bytes
    current_storage_index:int = 0  # Start with the first storage directory
    buffers_to_save:list = []

    _stop_event: threading.Event = None
    _save_thread: threading.Thread = None
    _lock: threading.Lock = None
    _buffer_full_condition: threading.Condition = None
    _buffer_a:Any = None
    _buffer_b:Any = None

    def init(self):
        dtype = np.__dict__[self.dtype]

        # Pre-allocate the two buffers
        self._buffer_a = np.zeros((self.buffer_capacity,) + self.image_shape, dtype=dtype)
        self._buffer_b = np.zeros((self.buffer_capacity,) + self.image_shape, dtype=dtype)

        # State variables
        self.active_buffer = 'A'  # start writing to buffer A
        self.write_index = 0
        self.total_images_written = 0
        self.total_images_read = 0
        self.next_buffer_id_to_save = 0  # increments every time we save a full buffer
        self.next_buffer_id_to_overwrite = 0  # track how many buffers have been overwritten

        # Locks and conditions
        self._lock = threading.Lock()
        self._buffer_full_condition = threading.Condition(self._lock)

        # Setup directories and capacities
        self.storage_dirs = []
        self.remaining_space = []  # in bytes

        for base_dir in self.base_dirs:
            uuid_dir = os.path.join(base_dir, str(uuid.uuid4()))
            os.makedirs(uuid_dir, exist_ok=True)
            self.storage_dirs.append(uuid_dir)
            self.remaining_space.append(self._calculate_free_space(uuid_dir))

        self.current_storage_index = 0  # Start with the first storage directory

        # Buffers pending save
        self.buffers_to_save = []

        # Event for stopping the thread
        self._stop_event = threading.Event()

        self._save_thread = threading.Thread(target=self.disk_saver_thread, daemon=True)
        self._save_thread.start()
        self.is_init = True
        return self

    def push(self, image: np.ndarray):
        if not self.is_init:
            raise ValueError("Class not init.")
        with self._lock:
            if image.shape != self.image_shape:
                raise ValueError("Image shape does not match the buffer's image shape.")

            # Check if both buffers are full and not saved
            if len(self.buffers_to_save) >= 2:
                raise RuntimeError("Both buffers are full and not yet saved. Cannot push more data.")

            # Write to the active buffer
            if self.active_buffer == 'A':
                self._buffer_a[self.write_index] = image
            else:
                self._buffer_b[self.write_index] = image

            self.write_index += 1
            self.total_images_written += 1

            # Check if the active buffer is now full
            if self.write_index == self.buffer_capacity:
                full_buffer = self.active_buffer

                # Switch active buffer
                if self.active_buffer == 'A':
                    self.active_buffer = 'B'
                else:
                    self.active_buffer = 'A'
                self.write_index = 0

                # Queue buffer for saving
                self.buffers_to_save.append((full_buffer, self.next_buffer_id_to_save))
                self.next_buffer_id_to_save += 1
                self._buffer_full_condition.notify()

    def _calculate_free_space(self, path):
        """Calculate free space at the specified path in bytes."""
        usage = shutil.disk_usage(path)
        return usage.free  # Returns the free space in bytes

    def disk_saver_thread(self):
        while not self._stop_event.is_set():
            with self._buffer_full_condition:
                while not self.buffers_to_save and not self._stop_event.is_set():
                    self._buffer_full_condition.wait()

                if not self.buffers_to_save:
                    # Stop event was set, and there are no buffers to save
                    break

                buffer_to_save, buffer_id = self.buffers_to_save.pop(0)

            # Copy the buffer out (not holding lock to avoid blocking)
            if buffer_to_save == 'A':
                buffer_data = self._buffer_a.copy()
                self._buffer_a[:] = 0
            else:
                buffer_data = self._buffer_b.copy()
                self._buffer_b[:] = 0

            while True:
                # Check the remaining space in the current storage directory
                current_dir = self.storage_dirs[self.current_storage_index]
                required_space = buffer_data.nbytes

                if self.remaining_space[self.current_storage_index] >= required_space:
                    # Save the buffer to the current directory
                    filename = os.path.join(current_dir, f"buffer_{buffer_id}.npy")
                    np.save(filename, buffer_data)

                    # Update remaining space
                    self.remaining_space[self.current_storage_index] -= required_space
                    break
                else:
                    # Switch to the next storage directory
                    self.current_storage_index += 1
                    if self.current_storage_index >= len(self.storage_dirs):
                        raise RuntimeError("All storage directories are full. Cannot save more data.")

    def pop(self):
        with self._lock:
            if self.total_images_read >= self.total_images_written:
                # No images available
                return None

            global_read_index = self.total_images_read
            self.total_images_read += 1

        buffer_id = global_read_index // self.buffer_capacity
        index_in_buffer = global_read_index % self.buffer_capacity

        with self._lock:
            current_buffer_id = (self.next_buffer_id_to_save - 1)

            if buffer_id == self.next_buffer_id_to_save: 
                if self.active_buffer == 'A':
                    img = self._buffer_a[index_in_buffer].copy()
                else:
                    img = self._buffer_b[index_in_buffer].copy()
                return img

        filename = os.path.join(self.storage_dirs[self.current_storage_index], f"buffer_{buffer_id}.npy")
        buffer_data = np.load(filename, mmap_mode='r')
        img = buffer_data[index_in_buffer].copy()
        return img

    def close(self):
        # Signal the thread to stop
        self._stop_event.set()
        with self._buffer_full_condition:
            self._buffer_full_condition.notify_all()
        self._save_thread.join()

    def __del__(self):
        self.close()
        for dir_path in self.storage_dirs:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)

# Example Usage:
def test():
    # Define the shape and queue parameters
    image_shape = (250, 250, 1)
    buffer_capacity = 100
    q = NumpyDualBufferDiskBackedQueue(base_dirs=['data'],image_shape=image_shape,
                                       buffer_capacity=buffer_capacity).init()

    # Number of images to push and pop
    num_images = 3000

    # Fake image
    fake_image = np.ones(image_shape, dtype=np.uint8)

    # Results to store FPS

    def push_images():
        push_fps = 0
        start_time = time.time()
        for i in range(num_images):
            q.push(fake_image * i)
        elapsed_time = time.time() - start_time
        push_fps = num_images / elapsed_time
        print(f"Push FPS: {push_fps:.2f} frames/sec")

    def pop_images():
        pop_fps = 0
        start_time = time.time()
        count = 0
        while count < num_images:
            img = q.pop()
            if img is not None:
                count += 1
        elapsed_time = time.time() - start_time
        pop_fps = num_images / elapsed_time
        print(f"Pop FPS: {pop_fps:.2f} frames/sec")

    # Create threads for pushing and popping
    push_thread = threading.Thread(target=push_images)
    pop_thread = threading.Thread(target=pop_images)

    # Start threads
    push_thread.start()

    time.sleep(2)
    pop_thread.start()

    # Wait for threads to finish
    push_thread.join()
    pop_thread.join()

    # Cleanup
    q.close()
test()