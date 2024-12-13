import time
import threading
import numpy as np

try:
    from ..Vision import BasicModel
except Exception as e:
    from Vision import BasicModel


# Example Usage:
def test():
    # Define the shape and queue parameters
    image_shape = (250, 250, 1)
    buffer_capacity = 1000
    q = BasicModel.NumpyDualBufferDiskBackedQueue(base_dirs=['data'],array_shape=image_shape,
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

# test()