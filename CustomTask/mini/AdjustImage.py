from typing import Optional
from pydantic import BaseModel, Field
from PIL import Image
import os
from PIL import Image, ImageEnhance

try:
    from Task.Basic import ServiceOrientedArchitecture
except ImportError:
    from mockServiceOrientedArchitecture import ServiceOrientedArchitecture


class AdjustImage(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return "Adjust the brightness, contrast, or saturation of an image."

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass
    
    class Model(ServiceOrientedArchitecture.Model):
        class Parameter(BaseModel):
            brightness: float = Field(1.0, description="Brightness factor (0.0-2.0, 1.0 is original)")
            contrast: float = Field(1.0, description="Contrast factor (0.0-2.0, 1.0 is original)")
            saturation: float = Field(1.0, description="Saturation factor (0.0-2.0, 1.0 is original)")

        class Arguments(BaseModel):
            path: str = ''

        class Returness(BaseModel):
            path: str

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    # "desc": "Identity (no change) — smoke test",
                    "para": {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0},
                    "args": {"path": "assets/sample.jpg"},
                },
                {
                    # "desc": "Slightly brighter",
                    "para": {"brightness": 1.15, "contrast": 1.0, "saturation": 1.0},
                    "args": {"path": "assets/sample.jpg"},
                },
                {
                    # "desc": "Boost contrast",
                    "para": {"brightness": 1.0, "contrast": 1.25, "saturation": 1.0},
                    "args": {"path": "assets/sample.jpg"},
                }
            ]



        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Optional[Returness] = None

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: AdjustImage.Model = self.model

        def __call__(self, *args, **kwargs):
            try:
                if not os.path.exists(self.model.args.path):
                    raise FileNotFoundError(f"Image not found: {self.model.args.path}")
                img = Image.open(self.model.args.path)
                
                # Apply brightness adjustment
                if self.model.para.brightness != 1.0:
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(self.model.para.brightness)
                
                # Apply contrast adjustment
                if self.model.para.contrast != 1.0:
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(self.model.para.contrast)
                    
                # Apply saturation adjustment
                if self.model.para.saturation != 1.0:
                    enhancer = ImageEnhance.Color(img)
                    img = enhancer.enhance(self.model.para.saturation)
                    
                output_path = f"{os.path.splitext(self.model.args.path)[0]}_adjusted.jpg"
                img.save(output_path)
                self.rets = self.model.Returness(path=output_path)
                return self.rets
            except Exception as e:
                raise ValueError(f"AdjustImage failed: {e}")
                