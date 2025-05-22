import os
import numpy as np
from PIL import Image
from typing import Optional
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper



class GrayscaleImage(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Converts an image to 8-bit grayscale using ImageJ-style processing.
Handles 16-bit and floating-point images by scaling to 8-bit.
RGB images are converted using luminance averaging.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            pass  # No configurable parameters needed yet

        class Args(BaseModel):
            path: str = Field(..., description="Path (file path, URL, or base64) to the input image")

        class Return(BaseModel):
            path: str = Field(..., description="Path to the saved grayscale image")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{"args":  {"path": "example.jpg"}},
                    { "args": { "path": "https://example.com/sample.jpg" } },
                    { "args": { "path": "data:image/jpeg;base64,/9j/4AAQSk..." } }
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = None
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: GrayscaleImage.Model = self.model

        def __call__(self, *args, **kwargs):
            path = self.model.args.path
            try:
                path = FileInputHelper.resolve_to_local_path(path)

                img = Image.open(path)
                img_np = np.array(img)

                # Handle image dtype conversion
                if img_np.dtype == np.uint16:
                    img_np = (img_np / 256).astype(np.uint8)
                elif img_np.dtype in [np.float32, np.float64]:
                    img_np = np.clip(img_np, 0, 1)
                    img_np = (img_np * 255).astype(np.uint8)

                # Convert to grayscale if needed
                if img.mode in ["RGB", "RGBA"]:
                    img_np = img_np.mean(axis=2).astype(np.uint8)

                # Convert back to 8-bit grayscale image
                img_gray = Image.fromarray(img_np, mode='L')
                output_path = f"{os.path.splitext(path)[0]}_gray.jpg"
                img_gray.save(output_path)

                self.log_and_send(f"Grayscale image saved to: {output_path}")
                self.model.ret = self.model.Return(path=output_path)

            except Exception as e:
                error_msg = f"GrayscaleImage failed: {e}"
                self.log_and_send(error_msg, GrayscaleImage.Levels.ERROR)
                raise ValueError(error_msg)

            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(GrayscaleImage.as_mcp_tool(), indent=4))
