import os
from typing import Optional
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture


class EnhanceImage(ServiceOrientedArchitecture):

    @classmethod
    def description(cls):
        return """
Adjusts the brightness, contrast, and saturation of an image.
Each factor of 1.0 is the original value.
The adjusted image is saved to a new file and its path is returned.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            brightness: float = Field(1.0, description="Brightness factor (1.0 is original)")
            contrast: float = Field(1.0, description="Contrast factor (1.0 is original)")
            saturation: float = Field(1.0, description="Saturation factor (1.0 is original)")

        class Args(BaseModel):
            path: str = Field(..., description="Path to the input image")

        class Return(BaseModel):
            path: str = Field(..., description="Path to the adjusted image")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [{
                "param": {"brightness": 1.2, "contrast": 1.0, "saturation": 1.1},
                "args": {"path": "example.jpg"}
            }]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = None
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: EnhanceImage.Model = self.model

        def __call__(self, *args, **kwargs):
            try:
                input_path = self.model.args.path
                self.log_and_send(f"Loading image from {input_path}")
                if not os.path.exists(input_path):
                    raise FileNotFoundError(f"Image not found at path: {input_path}")
                
                img = Image.open(input_path)

                # Apply adjustments
                img = self._adjust_image(img)

                output_path = f"{os.path.splitext(input_path)[0]}_adjusted.jpg"
                img.save(output_path)
                self.log_and_send(f"Image saved to {output_path}")
                self.model.ret = self.model.Return(path=output_path)
            except Exception as e:
                self.log_and_send(f"AdjustImage failed: {e}", EnhanceImage.Levels.ERROR)
                self.model.ret = self.model.Return(path="")
            return self.model

        def _adjust_image(self, img):
            param = self.model.param
            if param.brightness != 1.0:
                self.log_and_send(f"Adjusting brightness: {param.brightness}")
                img = ImageEnhance.Brightness(img).enhance(param.brightness)

            if param.contrast != 1.0:
                self.log_and_send(f"Adjusting contrast: {param.contrast}")
                img = ImageEnhance.Contrast(img).enhance(param.contrast)

            if param.saturation != 1.0:
                self.log_and_send(f"Adjusting saturation: {param.saturation}")
                img = ImageEnhance.Color(img).enhance(param.saturation)
            return img

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


if __name__ == "__main__":
    import json
    print(json.dumps(EnhanceImage.as_mcp_tool(), indent=4))
