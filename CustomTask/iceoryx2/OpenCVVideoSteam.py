import time
from typing import Optional, Union

import cv2
import numpy as np
from pydantic import BaseModel, Field

from Task.Basic import ServiceOrientedArchitecture
from .utils import IoxImagePublisher, RateMeter


class OpenCVVideoSteam(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
stream OpenCV video frames by iceoryx2.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Parameter(BaseModel):
            pass

        class Arguments(BaseModel):
            topic: str = Field(default="/your/topic/name", description="Topic name, /your/topic/name")

            # Can be camera index, video file path, RTSP URL, etc.
            source: Union[int, str] = Field(default=0, description="OpenCV VideoCapture source")

            width: int = Field(default=1280, description="Image width")
            height: int = Field(default=720, description="Image height")
            channels: int = Field(default=3, description="Number of image channels, usually 1, 3, or 4")

            FPS: float = Field(default=30.0, description="Frames per second")
            debug: bool = Field(default=False, description="Debug mode")

            # OpenCV options
            backend: int = Field(default=cv2.CAP_ANY, description="OpenCV VideoCapture backend")
            buffer_size: int = Field(default=1, description="OpenCV capture buffer size")

            # If True, converts OpenCV BGR frames to RGB before publishing
            rgb: bool = Field(default=False, description="Publish RGB instead of OpenCV BGR")

            # For video files, loop back to frame 0 when the file ends
            loop: bool = Field(default=True, description="Loop video file when end is reached")

            # Try reopening capture when read fails
            reconnect: bool = Field(default=True, description="Reconnect when capture read fails")

        class Returness(BaseModel):
            pass

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "args": {
                        "topic": "/your/topic/name",
                        "source": 0,
                        "width": 1280,
                        "height": 720,
                        "channels": 3,
                        "FPS": 30.0,
                    }
                },
                {
                    "args": {
                        "topic": "/camera/front",
                        "source": "rtsp://user:password@192.168.1.10/stream",
                        "width": 1280,
                        "height": 720,
                        "channels": 3,
                        "FPS": 30.0,
                    }
                },
                {
                    "args": {
                        "topic": "/video/file",
                        "source": "/path/to/video.mp4",
                        "width": 1280,
                        "height": 720,
                        "channels": 3,
                        "FPS": 30.0,
                        "loop": True,
                    }
                },
            ]

        version: Version = Version()
        para: Parameter = Parameter()
        args: Arguments
        rets: Optional[Returness] = Returness()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: OpenCVVideoSteam.Model = self.model

            self.pub = IoxImagePublisher(
                topic=self.model.args.topic,
                width=self.model.args.width,
                height=self.model.args.height,
                channels=self.model.args.channels,
                source_id=0,
            )

            self.frame_id = 0
            self.published_frames = 0
            self.dropped_frames = 0
            self.copy_ms = 0.0
            self.fps_meter = RateMeter()

            self.FPS = float(self.model.args.FPS)
            self.period_s = 1.0 / self.FPS if self.FPS > 0 else 0.0
            self.next_t = time.perf_counter()

            self.H = self.pub.height
            self.W = self.pub.width
            self.C = self.pub.channels
            self.HWC = (self.H, self.W, self.C)

            self.cap = None
            self.open_capture()

        def open_capture(self):
            if self.cap is not None:
                self.cap.release()

            self.cap = cv2.VideoCapture(
                self.model.args.source,
                self.model.args.backend,
            )

            if not self.cap.isOpened():
                raise RuntimeError(f"Failed to open OpenCV source: {self.model.args.source}")

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.W)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
            self.cap.set(cv2.CAP_PROP_FPS, self.FPS)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.model.args.buffer_size)

        def normalize_frame(self, frame: np.ndarray) -> np.ndarray:
            """
            Convert OpenCV frame into HWC uint8 image matching publisher shape.
            """

            if frame is None:
                raise ValueError("Received empty frame")

            # Resize if needed
            if frame.shape[0] != self.H or frame.shape[1] != self.W:
                frame = cv2.resize(frame, (self.W, self.H), interpolation=cv2.INTER_LINEAR)

            # Handle channel conversion
            if self.C == 1:
                if frame.ndim == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = frame[:, :, None]

            elif self.C == 3:
                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if self.model.args.rgb:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            elif self.C == 4:
                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGRA)
                elif frame.shape[2] == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)

                if self.model.args.rgb:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)

            else:
                raise ValueError(f"Unsupported channel count: {self.C}")

            return np.ascontiguousarray(frame, dtype=np.uint8)

        def read_frame(self):
            ok, frame = self.cap.read()

            if ok and frame is not None:
                return frame

            self.dropped_frames += 1

            # If source is a video file and loop is enabled, restart from first frame
            if self.model.args.loop and not isinstance(self.model.args.source, int):
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    return frame

            # Reconnect for cameras / streams
            if self.model.args.reconnect:
                try:
                    self.open_capture()
                    ok, frame = self.cap.read()
                    if ok and frame is not None:
                        return frame
                except Exception as e:
                    self.log_and_send(f"OpenCV reconnect failed: {e}", level=self.logger.level)

            return None

        def tick(self) -> None:
            frame = self.read_frame()

            if frame is None:
                self.sleep_until_next_tick()
                return

            image = self.normalize_frame(frame)

            frame_id, timestamp_ns, payload_size, copy_us = self.pub.publish(image)

            self.frame_id += 1
            self.copy_ms = copy_us / 1000.0
            self.published_frames += 1
            self.fps_meter.tick()

            self.sleep_until_next_tick()

        def sleep_until_next_tick(self):
            if self.period_s <= 0:
                return

            self.next_t += self.period_s
            sleep_s = self.next_t - time.perf_counter()

            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # Prevent infinite drift if processing is slower than target FPS
                self.next_t = time.perf_counter()

        def __call__(self, *args, **kwargs):
            try:
                with self.listen_stop_flag() as stop_flag:
                    while True:
                        if self.frame_id % max(1, int(self.FPS)) == 0:
                            self.log_and_send(
                                f"sent frame={self.frame_id} "
                                f"fps={self.fps_meter.value:.1f} "
                                f"copy_ms={self.copy_ms:.3f} "
                                f"dropped={self.dropped_frames}"
                            )

                            if stop_flag.is_set():
                                return self.to_stop()

                        self.tick()

            finally:
                if self.cap is not None:
                    self.cap.release()

        def to_stop(self):
            if self.cap is not None:
                self.cap.release()
                self.cap = None

            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level

            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            OpenCVVideoSteam.as_openai_tool()["function"]["parameters"]["properties"]["args"],
            indent=4,
        )
    )