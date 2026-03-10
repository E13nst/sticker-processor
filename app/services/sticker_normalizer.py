"""Normalize generated images to Telegram sticker-compatible format."""
from io import BytesIO
from typing import Tuple

from PIL import Image


class StickerNormalizer:
    """Converts arbitrary image bytes to Telegram sticker WebP format."""

    def __init__(self, canvas_size: int = 512):
        self.canvas_size = canvas_size

    def normalize_to_webp(self, image_bytes: bytes) -> Tuple[bytes, str]:
        """
        Normalize image into 512x512 WebP suitable for Telegram sticker upload.

        Returns:
            (content_bytes, mime_type)
        """
        image = Image.open(BytesIO(image_bytes))
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Preserve aspect ratio and fit into 512x512.
        image.thumbnail((self.canvas_size, self.canvas_size), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (self.canvas_size, self.canvas_size), (0, 0, 0, 0))
        x_offset = (self.canvas_size - image.width) // 2
        y_offset = (self.canvas_size - image.height) // 2
        canvas.paste(image, (x_offset, y_offset), image)

        out = BytesIO()
        canvas.save(out, format="WEBP", method=6, lossless=False, quality=92)
        return out.getvalue(), "image/webp"
