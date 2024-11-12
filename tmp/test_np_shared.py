import time
import numpy as np
from multiprocessing import shared_memory
import torch  # Import torch

def test_shared_memory_performance():
    # Define 8K resolution (7680x4320) with 3 channels (RGB)
    width, height, channels = 7680, 4320, 3
    frame_size = width * height * channels
    # Create random data to simulate an 8K frame (using uint8 values for RGB)
    original_frame = np.random.randint(0, 256, frame_size, dtype=np.uint8)
    small_frame = np.random.randint(0, 256, frame_size // 100, dtype=np.uint8)
    # Create a shared memory block
    shm = shared_memory.SharedMemory(create=True, size=original_frame.nbytes)
    # Create a numpy array using the shared memory block
    shared_array = np.ndarray(original_frame.shape, dtype=original_frame.dtype, buffer=shm.buf)

    shm2 = shared_memory.SharedMemory(create=True, size=small_frame.nbytes)
    shared_array2 = np.ndarray(small_frame.shape, dtype=small_frame.dtype, buffer=shm2.buf)
    # Measure performance for copying/cloning the data
    num_iterations = 1000  # Number of times to copy the frame
    start_time = time.time()
    for _ in range(num_iterations):
        # Copy data to shared memory
        shared_array[:] = original_frame[:]
        shared_array2[:] = original_frame[::100]
        shared_array_c = shared_array2.copy()

        # Convert shared_array to a PyTorch tensor and move it to the GPU
        tensor_gpu = torch.from_numpy(shared_array).to('cuda')  # Move to GPU

    end_time = time.time()
    # Calculate and print performance metrics
    total_time = end_time - start_time
    fps = num_iterations / total_time
    print(f"Cloned {num_iterations} frames in {total_time:.4f} seconds")
    print(f"Approximate FPS: {fps:.2f}")
    # Clean up
    shm.close()
    shm.unlink()
    shm2.close()
    shm2.unlink()

if __name__ == "__main__":
    test_shared_memory_performance()
