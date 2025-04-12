import json
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field
import requests
from io import BytesIO
from PIL import Image
import os
import tempfile

try:
    from Task.Basic import ServiceOrientedArchitecture
except ImportError:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture


class ImageTiler(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            img_size_limit: int = Field(250000000, description="Maximum image size limit in pixels")
            cols: int = Field(2, description="Number of columns for tiling images")
            rows: int = Field(2, description="Number of rows for tiling images")
            final_width: int = Field(800, description="Final image width in pixels")
            final_height: int = Field(600, description="Final image height in pixels")
            output_format: str = Field("jpg", description="Output image format (jpg, png, etc.)")
            output_path: Optional[str] = Field('tiled_image.jpg', description="Custom output path for the tiled image")
            
        class Args(BaseModel):
            image_sources: List[str] = Field(
                [],
                description="List of image URLs or local file paths, depending on the mode parameter."
            )
            image_slices: List[Tuple[float, float]] = Field(
                [],
                description="List of normalized coordinates (x,y) in range -1.0 to 1.0 that to do slicing to sub each image , with: width * x, height * y"
            )
            
        class Return(BaseModel):
            tiled_image_path: Optional[str] = Field(
                None,
                description="Path to the saved tiled image"
            )
            

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {
                        "cols": 2,
                        "rows": 2,
                        "final_width": 800,
                        "final_height": 600,
                        "output_format": "jpg"
                    },
                    "args": {
                        "image_sources": [
                            "https://example.com/image1.jpg",
                            "https://example.com/image2.jpg",
                            "https://example.com/image3.jpg",
                            "https://example.com/image4.jpg"
                        ]
                    }
                },
                {
                    "param": {
                        "cols": 3,
                        "rows": 2,
                        "final_width": 1200,
                        "final_height": 800,
                        "output_format": "png",
                        "output_path": "custom_output/my_tiled_image.png"
                    },
                    "args": {
                        "image_sources": [
                            "/path/to/local/image1.jpg",
                            "/path/to/local/image2.png",
                            "/path/to/local/image3.jpg",
                            "/path/to/local/image4.png",
                            "/path/to/local/image5.jpg",
                            "/path/to/local/image6.png"
                        ]
                    }
                },
                {
                    "param": {
                        "cols": 2,
                        "rows": 2,
                        "final_width": 1000,
                        "final_height": 1000
                    },
                    "args": {
                        "image_sources": [
                            "https://example.com/image1.jpg",
                            "https://example.com/image2.jpg",
                            "https://example.com/image3.jpg",
                            "https://example.com/image4.jpg"
                        ],
                        "image_slices": [
                            (0.5, 0.5),  # Take left half and top half of image1
                            (-0.5, 0.5), # Take right half and top half of image2
                            (0.5, -0.5), # Take left half and bottom half of image3
                            (-0.5, -0.5) # Take right half and bottom half of image4
                        ]
                    }
                }
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: ImageTiler.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()
                
                self.log_and_send("Starting image tiling process.")
                
                # Process images and create tiled image
                if not self._validate_inputs():
                    self.model.ret.tiled_image_path = ""
                    
                    return self.model
                
                images = self._process_images(stop_flag)
                
                if stop_flag.is_set():
                    return self.to_stop()
                
                if not images:
                    self.log_and_send("No valid images were processed. Exiting.", ImageTiler.Levels.ERROR)
                    self.model.ret.tiled_image_path = ""
                    
                    return self.model                
                
                self._create_tiled_image(images)
                
                return self.model

        def _validate_inputs(self):
            """Validate input parameters and sources."""
            sources = self.model.args.image_sources
            if not sources:
                self.log_and_send("No image sources provided. Please provide at least one image source.", ImageTiler.Levels.ERROR)
                return False
                
            if self.model.param.cols <= 0 or self.model.param.rows <= 0:
                self.log_and_send("Columns and rows must be positive integers.", ImageTiler.Levels.ERROR)
                return False
                
            if self.model.param.final_width <= 0 or self.model.param.final_height <= 0:
                self.log_and_send("Final width and height must be positive integers.", ImageTiler.Levels.ERROR)
                return False
                
            return True
            
        def _process_images(self, stop_flag):
            """Process all image sources and return a list of processed images."""
            sources = self.model.args.image_sources
            cols = self.model.param.cols
            rows = self.model.param.rows
            final_width = self.model.param.final_width
            final_height = self.model.param.final_height
            
            # Calculate dimensions for each cell in the grid
            cell_width = final_width // cols
            cell_height = final_height // rows
            self.log_and_send(
                f"Tiling parameters: {cols} cols x {rows} rows; Final size: {final_width}x{final_height}; Each cell: {cell_width}x{cell_height}."
            )
            
            # List to store processed images
            images = []
            for idx, source in enumerate(sources):
                if stop_flag.is_set():
                    return []
                
                try:
                    img = self._load_image(source, idx, len(sources))
                    if img is None:
                        continue
                    
                    # Apply image slicing if specified
                    img = self._apply_slicing(img, idx)
                    
                    # Resize image to fit cell dimensions
                    original_size = img.size
                    img = img.resize((cell_width, cell_height), Image.LANCZOS)
                    self.log_and_send(
                        f"Resized image {idx+1} from {original_size} to {img.size}."
                    )
                    
                    images.append(img)
                except Exception as e:
                    self.log_and_send(f"Unexpected error processing image at {source}: {str(e)}", ImageTiler.Levels.ERROR)
                    continue
                    
            return images
            
        def _load_image(self, source, idx, total_sources):
            """Load an image from a URL or local file path."""
            try:
                # Set PIL's maximum image size limit to prevent decompression bomb attacks
                Image.MAX_IMAGE_PIXELS = self.model.param.img_size_limit

                if source.startswith(("http://", "https://")):
                    self.log_and_send(
                        f"Downloading image {idx + 1}/{total_sources} from {source}."
                    )
                    response = requests.get(source, timeout=10)
                    response.raise_for_status()
                    img_data = BytesIO(response.content)
                    
                    img = Image.open(img_data)
                    self.log_and_send(
                        f"Successfully downloaded image {idx+1}: {img.format}, size: {img.size}, mode: {img.mode}"
                    )
                else:
                    if not os.path.exists(source):
                        raise FileNotFoundError(f"Image file not found: {source}")
                    self.log_and_send(
                        f"Opening local image {idx + 1}/{total_sources} from {source}."
                    )
                        
                    img = Image.open(source)
                    self.log_and_send(
                        f"Successfully opened image {idx+1}: {img.format}, size: {img.size}, mode: {img.mode}"
                    )
                
                # Convert image to RGB if necessary
                if img.mode != 'RGB':
                    self.log_and_send(
                        f"Converting image {idx+1} from {img.mode} to RGB mode."
                    )
                    img = img.convert('RGB')
                    
                return img
            except requests.exceptions.RequestException as e:
                self.log_and_send(f"Network error while downloading image {idx+1} from {source}: {str(e)}", ImageTiler.Levels.ERROR)
            except FileNotFoundError as e:
                self.log_and_send(f"{str(e)}", ImageTiler.Levels.ERROR)
            except Image.UnidentifiedImageError:
                self.log_and_send(f"Could not identify image {idx+1} format for {source}", ImageTiler.Levels.ERROR)
            except Image.DecompressionBombError as e:
                self.log_and_send(f"Image {idx+1} from {source} is too large: {str(e)}", ImageTiler.Levels.ERROR)
            
            return None
            
        def _apply_slicing(self, img, idx):
            """Apply slicing to an image if specified in the model args."""
            slices = self.model.args.image_slices
            if not slices or idx >= len(slices) or not slices[idx] or len(slices[idx])!=2:
                return img
                
            rx, ry = slices[idx]
            width, height = img.size
            
            # Calculate target dimensions based on normalized coordinates
            target_width = int(abs(rx) * width)
            target_height = int(abs(ry) * height)
            
            # Calculate starting positions
            start_x = 0 if rx > 0 else width - target_width
            start_y = 0 if ry > 0 else height - target_height
            
            # Crop the image
            cropped_img = img.crop((start_x, start_y, start_x + target_width, start_y + target_height))
            self.log_and_send(
                f"Applied slicing to image {idx+1}: coordinates ({rx}, {ry}), resulting size: {cropped_img.size}"
            )
            
            return cropped_img
            
        def _create_tiled_image(self, images):
            """Create and save the final tiled image."""
            cols = self.model.param.cols
            rows = self.model.param.rows
            final_width = self.model.param.final_width
            final_height = self.model.param.final_height
            cell_width = final_width // cols
            cell_height = final_height // rows
            
            # Create a blank canvas for the final tiled image
            tiled_image = Image.new('RGB', (final_width, final_height))
            img_index = 0
            
            self.log_and_send(f"Tiling {len(images)} images into a {rows}x{cols} grid.")

            for row in range(rows):
                for col in range(cols):
                    if img_index >= len(images):
                        break  # No more images to paste
                    x = col * cell_width
                    y = row * cell_height
                    tiled_image.paste(images[img_index], (x, y))
                    img_index += 1
                    self.log_and_send(
                        f"Placed image {img_index} at grid position ({row}, {col}), at array position ({y}, {x})"
                    )

            self._save_tiled_image(tiled_image)
            
        def _save_tiled_image(self, tiled_image):
            """Save the tiled image to disk."""
            try:
                # Determine output path
                if self.model.param.output_path:
                    output_path = self.model.param.output_path
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                else:
                    output_format = self.model.param.output_format.lower()
                    if not output_format.startswith('.'):
                        output_format = f".{output_format}"
                    
                    # Create a temporary file with the specified extension
                    with tempfile.NamedTemporaryFile(suffix=output_format, delete=False) as tmp:
                        output_path = tmp.name
                
                # Save the image
                tiled_image.save(output_path)
                self.log_and_send(
                    f"Tiled image saved at {output_path}. Final size: {tiled_image.size}"
                )
                self.model.ret.tiled_image_path = output_path
            except Exception as e:
                self.log_and_send(f"Error saving tiled image: {str(e)}", ImageTiler.Levels.ERROR)
                self.model.ret.tiled_image_path = ""

        def to_stop(self):
            self.log_and_send("Stop flag detected, aborting image tiling process.", ImageTiler.Levels.WARNING)
            self.model.ret.tiled_image_path = ""
            
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


# Simple test for ImageTiler
if __name__ == "__main__":
    # Create test images
    test_dir = "tmp"
    os.makedirs(test_dir, exist_ok=True)
    
    # Create a few test images
    for i in range(1, 5):
        img = Image.new('RGB', (200, 200), color=(i*50, i*30, i*70))
        img_path = os.path.join(test_dir, f"test_image_{i}.jpg")
        img.save(img_path)
        print(f"Created test image: {img_path}")
    
    # Initialize the model
    model = ImageTiler.Model()
    
    # Set parameters
    model.param.cols = 2
    model.param.rows = 2
    model.param.final_width = 600
    model.param.final_height = 600
    model.param.output_path = os.path.join(test_dir, "tiled_output.jpg")
    
    # Set arguments
    model.args.image_sources = [
        os.path.join(test_dir, f"test_image_{i}.jpg") for i in range(1, 5)
    ]
    
    # Run the tiler
    print(ImageTiler.Action(model,None)().model_dump())    

    # custom test    
    model = ImageTiler.Model(**json.load(open("tmp/test_image_tiler.json")))
    print(ImageTiler.Action(model,None)().model_dump())
