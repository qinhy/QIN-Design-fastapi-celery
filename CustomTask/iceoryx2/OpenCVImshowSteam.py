import time
from typing import Optional

import cv2
import numpy as np
from pydantic import BaseModel, Field

from Task.Basic import ServiceOrientedArchitecture
from .utils import IoxImageSubscriber, RateMeter


class OpenCVImshowSteam(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
subscribe image stream by iceoryx2 and show images with OpenCV imshow.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Parameter(BaseModel):
            pass

        class Arguments(BaseModel):
            topic: str = Field(default="/your/topic/name", description="Topic name, /your/topic/name")

            window_name: str = Field(default="OpenCVImshowSteam", description="OpenCV window name")

            # cv2.waitKey delay. 1 is usually enough for realtime display.
            wait_key_ms: int = Field(default=1, description="OpenCV waitKey delay in milliseconds")

            # Sleep when no frame is available, to avoid busy CPU loop.
            poll_sleep_s: float = Field(default=0.001, description="Sleep time when no frame is received")

            # If publisher sends RGB, set this True because cv2.imshow expects BGR.
            input_rgb: bool = Field(default=False, description="Convert RGB/RGBA input to BGR/BGRA for imshow")

            # Resize display only; does not affect received image.
            resize: bool = Field(default=False, description="Resize image before showing")
            display_width: int = Field(default=1280, description="Display width when resize=True")
            display_height: int = Field(default=720, description="Display height when resize=True")

            # Press q or ESC to stop.
            quit_on_key: bool = Field(default=True, description="Quit when q or ESC is pressed")

            debug: bool = Field(default=False, description="Debug mode")

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
                        "window_name": "Image Stream",
                        "wait_key_ms": 1,
                        "input_rgb": False,
                    }
                },
                {
                    "args": {
                        "topic": "/camera/front",
                        "window_name": "Front Camera",
                        "resize": True,
                        "display_width": 1280,
                        "display_height": 720,
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
            self.model: OpenCVImshowSteam.Model = self.model

            self.sub = IoxImageSubscriber(
                topic=self.model.args.topic,
            )

            self.received_frames = 0
            self.dropped_frames = 0
            self.error_count = 0
            self.last_frame_id: Optional[int] = None
            self.last_latency_us = 0

            self.fps_meter = RateMeter()
            self.last_log_t = time.perf_counter()

            cv2.namedWindow(self.model.args.window_name, cv2.WINDOW_NORMAL)

        def normalize_for_imshow(self, image: np.ndarray) -> np.ndarray:
            """
            Convert received image into a format suitable for cv2.imshow.

            The received image is zero-copy and read-only, so this function only
            copies when conversion or resize is needed.
            """

            if image is None:
                raise ValueError("received empty image")

            show = image

            if show.dtype != np.uint8:
                show = show.astype(np.uint8, copy=False)

            if show.ndim == 3:
                channels = show.shape[2]

                if channels == 1:
                    show = show[:, :, 0]

                elif channels == 3:
                    if self.model.args.input_rgb:
                        show = cv2.cvtColor(show, cv2.COLOR_RGB2BGR)

                elif channels == 4:
                    if self.model.args.input_rgb:
                        show = cv2.cvtColor(show, cv2.COLOR_RGBA2BGRA)

                else:
                    raise ValueError(f"unsupported channel count for imshow: {channels}")

            elif show.ndim != 2:
                raise ValueError(f"unsupported image shape for imshow: {show.shape}")

            if self.model.args.resize:
                show = cv2.resize(
                    show,
                    (self.model.args.display_width, self.model.args.display_height),
                    interpolation=cv2.INTER_LINEAR,
                )

            return show

        def tick(self) -> bool:
            """
            Returns False when the display loop should stop.
            """

            frame = self.sub.receive()

            if frame is None:
                key = cv2.waitKey(self.model.args.wait_key_ms) & 0xFF
                if self.should_quit_from_key(key):
                    return False

                time.sleep(self.model.args.poll_sleep_s)
                return True

            try:
                frame_id = int(frame.header.frame_id)

                if self.last_frame_id is not None and frame_id > self.last_frame_id + 1:
                    self.dropped_frames += frame_id - self.last_frame_id - 1

                self.last_frame_id = frame_id
                self.last_latency_us = frame.latency_us

                image = self.normalize_for_imshow(frame.image)

                cv2.imshow(self.model.args.window_name, image)

                self.received_frames += 1
                self.fps_meter.tick()

                key = cv2.waitKey(self.model.args.wait_key_ms) & 0xFF
                if self.should_quit_from_key(key):
                    return False

                return True

            except Exception as e:
                self.error_count += 1
                self.log_and_send(f"imshow error: {e}", level=self.logger.level)
                return True

        def should_quit_from_key(self, key: int) -> bool:
            if not self.model.args.quit_on_key:
                return False

            # ESC or q
            return key == 27 or key == ord("q")

        def __call__(self, *args, **kwargs):
            try:
                with self.listen_stop_flag() as stop_flag:
                    while True:
                        now = time.perf_counter()

                        if now - self.last_log_t >= 1.0:
                            self.log_and_send(
                                f"received={self.received_frames} "
                                f"fps={self.fps_meter.value:.1f} "
                                f"latency_us={self.last_latency_us} "
                                f"dropped={self.dropped_frames} "
                                f"errors={self.error_count}"
                            )
                            self.last_log_t = now

                            if stop_flag.is_set():
                                return self.to_stop()

                        keep_running = self.tick()
                        if not keep_running:
                            return self.to_stop()

            finally:
                cv2.destroyWindow(self.model.args.window_name)

        def to_stop(self):
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
            OpenCVImshowSteam.as_openai_tool()["function"]["parameters"]["properties"]["args"],
            indent=4,
        )
    )