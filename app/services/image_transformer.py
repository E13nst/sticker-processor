"""Image transformation helpers for upload/source flows."""
from io import BytesIO
from typing import Tuple

from PIL import Image, UnidentifiedImageError


class ImageTransformer:
    """Normalize source images for external generation providers."""

    def __init__(self, max_side: int = 1024):
        self.max_side = max_side

    def normalize_for_nanabanana(self, image_bytes: bytes) -> Tuple[bytes, str, str]:
        """
        Normalize image for nanabanana edit input.

        Returns:
            tuple: (normalized_bytes, mime_type, output_format)
        """
        try:
            image = Image.open(BytesIO(image_bytes))
        except UnidentifiedImageError as exc:
            raise ValueError("Uploaded file is not a valid image") from exc

        has_alpha = "A" in image.getbands()
        target_mode = "RGBA" if has_alpha else "RGB"
        if image.mode != target_mode:
            image = image.convert(target_mode)

        image.thumbnail((self.max_side, self.max_side), Image.Resampling.LANCZOS)

        output = BytesIO()
        if has_alpha:
            image.save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png", "png"

        image.save(output, format="JPEG", quality=85, optimize=True, progressive=True)
        return output.getvalue(), "image/jpeg", "jpg"
