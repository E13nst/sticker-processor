"""Service for combining multiple images into a grid."""
import io
import math
import logging
from typing import List, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


def resize_to_square(image: Image.Image, size: int = 128, background_color: str = "white") -> Image.Image:
    """
    Resize image to square with preserved aspect ratio.
    
    Resizes the larger side to target size while maintaining aspect ratio,
    then places the image in the center of a square canvas, filling
    remaining space with background color.
    
    Args:
        image: PIL Image to resize
        size: Target square size in pixels (default: 128)
        background_color: Background color for padding (default: "white")
        
    Returns:
        Square PIL Image of size x size
    """
    # Get original dimensions
    original_width, original_height = image.size
    
    # Calculate scaling factor based on larger side
    if original_width > original_height:
        scale = size / original_width
    else:
        scale = size / original_height
    
    # Calculate new dimensions maintaining aspect ratio
    new_width = int(original_width * scale)
    new_height = int(original_height * scale)
    
    # Resize image
    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Create square canvas with background color
    square_image = Image.new("RGB", (size, size), background_color)
    
    # Calculate position to center the resized image
    x_offset = (size - new_width) // 2
    y_offset = (size - new_height) // 2
    
    # Paste resized image onto square canvas
    # Handle RGBA images (with transparency)
    if resized_image.mode == "RGBA":
        square_image.paste(resized_image, (x_offset, y_offset), resized_image)
    else:
        square_image.paste(resized_image, (x_offset, y_offset))
    
    return square_image


def calculate_grid_layout(num_images: int) -> Tuple[int, int]:
    """
    Calculate optimal grid layout dimensions close to square.
    
    Finds factors that create a grid as close to square as possible.
    For example: 12 images = 4x3, 8 images = 3x3 (with one empty slot).
    
    Args:
        num_images: Number of images to arrange
        
    Returns:
        Tuple of (columns, rows) for the grid
    """
    if num_images <= 0:
        return (1, 1)
    
    # Start with square root to find dimensions close to square
    sqrt = math.sqrt(num_images)
    
    # Try to find the best factor pair
    best_cols = int(math.ceil(sqrt))
    best_rows = int(math.ceil(num_images / best_cols))
    
    # Try alternative: floor of sqrt
    alt_cols = int(math.floor(sqrt))
    if alt_cols > 0:
        alt_rows = int(math.ceil(num_images / alt_cols))
        # Choose the layout with aspect ratio closer to 1:1
        best_ratio = max(best_cols, best_rows) / min(best_cols, best_rows)
        alt_ratio = max(alt_cols, alt_rows) / min(alt_cols, alt_rows)
        
        if alt_ratio < best_ratio:
            best_cols = alt_cols
            best_rows = alt_rows
    
    return (best_cols, best_rows)


def combine_images(images: List[Image.Image], tile_size: int = 128) -> Image.Image:
    """
    Combine multiple images into a single grid image in WebP format.
    
    Args:
        images: List of PIL Images to combine
        tile_size: Size of each tile in pixels (default: 128)
        
    Returns:
        Combined PIL Image in WebP format
    """
    if not images:
        raise ValueError("Cannot combine empty list of images")
    
    # Calculate grid layout
    num_images = len(images)
    cols, rows = calculate_grid_layout(num_images)
    
    logger.info(f"Combining {num_images} images into {cols}x{rows} grid")
    
    # Resize all images to squares
    square_images = [resize_to_square(img, tile_size) for img in images]
    
    # Create output canvas
    canvas_width = cols * tile_size
    canvas_height = rows * tile_size
    combined_image = Image.new("RGB", (canvas_width, canvas_height), "white")
    
    # Place images in grid (no padding between tiles)
    for idx, square_img in enumerate(square_images):
        row = idx // cols
        col = idx % cols
        
        x = col * tile_size
        y = row * tile_size
        
        combined_image.paste(square_img, (x, y))
    
    return combined_image


def image_from_bytes(image_bytes: bytes) -> Image.Image:
    """
    Convert image bytes to PIL Image.
    
    Supports PNG, WebP, JPEG formats.
    
    Args:
        image_bytes: Image file bytes
        
    Returns:
        PIL Image object
        
    Raises:
        ValueError: If image format is not supported or cannot be decoded
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Convert to RGB if necessary (handles RGBA, P, etc.)
        if image.mode not in ("RGB", "RGBA"):
            # Convert palette images to RGB
            if image.mode == "P":
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
        elif image.mode == "RGBA":
            # Keep RGBA for transparency support
            pass
        else:
            # Ensure RGB mode
            image = image.convert("RGB")
        return image
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        raise ValueError(f"Unsupported image format or corrupted image: {e}")


def image_to_webp(image: Image.Image, quality: int = 85) -> bytes:
    """
    Convert PIL Image to WebP format bytes.
    
    Args:
        image: PIL Image to convert
        quality: WebP quality (0-100, default: 85)
        
    Returns:
        WebP image bytes
    """
    output = io.BytesIO()
    
    # Convert RGBA to RGB if needed for WebP
    if image.mode == "RGBA":
        # Create white background
        rgb_image = Image.new("RGB", image.size, "white")
        rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        image = rgb_image
    
    image.save(output, format="WEBP", quality=quality, method=6)
    output.seek(0)
    return output.getvalue()

