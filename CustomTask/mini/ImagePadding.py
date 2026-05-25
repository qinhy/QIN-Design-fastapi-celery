from typing import Optional
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, ImageColor
import os

try:
    from Task.Basic import ServiceOrientedArchitecture
except ImportError:
    from mockServiceOrientedArchitecture import ServiceOrientedArchitecture


class ImagePadding(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return "Pad an image to specific height and width ratios (e.g., 1.1x height, 1.2x width)."

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Parameter(BaseModel):
            h_ratio: float = Field(
                1.1,
                ge=1.0,
                description="Height ratio to original (>=1.0; e.g., 1.1 means 10% more height)"
            )
            w_ratio: float = Field(
                1.1,
                ge=1.0,
                description="Width ratio to original (>=1.0; e.g., 1.2 means 20% more width)"
            )
            color: str = Field(
                "white",
                description="Padding color (e.g., 'white', 'black', or '#RRGGBB')"
            )

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
                    # "desc": "Taller only (letterbox bars top/bottom)",
                    "para": {"h_ratio": 1.1, "w_ratio": 1.0, "color": "black"},
                    "args": {"path": "assets/landscape.jpg"}
                },
                {
                    # "desc": "Wider only (side bars)",
                    "para": {"h_ratio": 1.0, "w_ratio": 1.2, "color": "#000000"},
                    "args": {"path": "assets/portrait.jpg"}
                },
                {
                    # "desc": "Both height and width increased (light gray mat)",
                    "para": {"h_ratio": 1.25, "w_ratio": 1.25, "color": "#f5f5f5"},
                    "args": {"path": "assets/sample.jpg"}
                },
                {
                    # "desc": "Identity (no padding) — smoke test",
                    "para": {"h_ratio": 1.0, "w_ratio": 1.0, "color": "white"},
                    "args": {"path": "assets/sample.jpg"}
                },
            ]

        version:Version = Version()
        para: Parameter = Parameter()
        args: Arguments = Arguments()
        rets: Optional[Returness] = None
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: ImagePadding.Model = self.model

        def __call__(self, *args, **kwargs):
            try:
                if not os.path.exists(self.model.args.path):
                    raise FileNotFoundError(f"Image not found: {self.model.args.path}")

                # Validate color early (raises if invalid)
                try:
                    ImageColor.getrgb(self.model.para.color)
                except Exception:
                    raise ValueError(f"Invalid padding color: {self.model.para.color}")

                img = Image.open(self.model.args.path)
                orig_w, orig_h = img.size

                new_h = int(round(orig_h * self.model.para.h_ratio))
                new_w = int(round(orig_w * self.model.para.w_ratio))

                delta_w = max(0, new_w - orig_w)
                delta_h = max(0, new_h - orig_h)

                padding = (
                    delta_w // 2,                      # left
                    delta_h // 2,                      # top
                    delta_w - (delta_w // 2),          # right
                    delta_h - (delta_h // 2)           # bottom
                )

                print(img.size)
                print(padding)
                padded_img = ImageOps.expand(img, padding, fill=self.model.para.color)

                output_path = f"{os.path.splitext(self.model.args.path)[0]}_padded.jpg"
                padded_img.save(output_path)

                self.model.rets = self.model.Returness(path=output_path)

            except Exception as e:
                raise ValueError(f"ImagePadding failed: {e}")            
            finally:                
                return self.model

# Simple test for ImageTiler
if __name__ == "__main__":
    # Create test images
    test_dir = "tmp"
    os.makedirs(test_dir, exist_ok=True)

    # Initialize the model
    model = ImagePadding.Model(**{
                    "para": {"h_ratio": 1.1, "w_ratio": 1.1, "color": "white"},
                    "args": {"path": "./tmp/Lenna_(test_image).png"}})
    
    
    # Run the tiler
    print(ImagePadding.Action(model,None)().model_dump())    

