import time
from typing import List, Optional
import numpy as np
from pydantic import BaseModel, Field


from Task.Basic import ServiceOrientedArchitecture
from .utils import IoxImagePublisher, RateMeter


class NumpyImageSteam(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
steam numpy images by iceoryx2.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Parameter(BaseModel):
            pass

        class Arguments(BaseModel):
            topic: str = Field(default="/your/topic/name", description="Topic name, /your/topic/name")
            width: int = Field(default=1280, description="Image width")
            height: int = Field(default=720, description="Image height")
            channels: int = Field(default=3, description="Number of image channels")
            FPS: float = Field(default=30.0, description="Frames per second")
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
                {"args": {"topic": "/your/topic/name", "width": 1280, "height": 720, "channels": 3, "FPS": 30.0}},
            ]

        version: Version = Version()
        para: Parameter = Parameter()
        args: Arguments
        rets: Optional[Returness] = Returness(sum=0)
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: NumpyImageSteam.Model = self.model
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
            self.FPS = self.model.args.FPS
            self.period_s = 1.0 / self.model.args.FPS
            self.next_t = time.perf_counter()
            H,W,C = self.pub.height,self.pub.width,self.pub.channels
            self.HWC = H,W,C
            if self.model.args.debug:
                self.image = np.random.randint(0, 256, size=(H,W,C), dtype=np.uint8)

        def tick(self) -> None:
            self.frame_id += 1
            if self.model.args.debug:
                image = self.image
            else:
                image = np.empty(self.HWC, dtype=np.uint8)
            image[:, :, 0] = self.frame_id % 256
            image[:, :, 1] = np.arange(self.pub.width, dtype=np.uint8)[None, :]
            image[:, :, 2] = np.arange(self.pub.height, dtype=np.uint8)[:, None]

            frame_id,timestamp_ns,payload_size,copy_us = self.pub.publish(image)
            self.copy_ms = copy_us / 1000.0
            self.published_frames += 1
            self.fps_meter.tick()

            self.next_t += self.period_s
            sleep_s = self.next_t - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
                
        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                while True:
                    if self.frame_id % max(1, int(self.FPS)) == 0:
                        self.log_and_send(f"sent frame={self.frame_id} fps={self.fps_meter.value:.1f} copy_ms={self.copy_ms:.3f}")
                        if stop_flag.is_set():
                            return self.to_stop()
                    self.tick()

        def to_stop(self):
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

if __name__ == "__main__":
    import json
    print(json.dumps(NumpyImageSteam.as_openai_tool()["function"]["parameters"]["properties"]["args"], indent=4))
