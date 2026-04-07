"""Image transformation helpers for upload/source flows."""
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, UnidentifiedImageError


class ImageTransformer:
    """Normalize source images for external generation providers."""

    _popular_raster_formats = "JPEG, PNG, WEBP, GIF, BMP, TIFF, HEIC/HEIF, and AVIF"
    _heif_registration_attempted = False
    _heif_supported = False

    def __init__(self, max_side: int = 1024):
        self.max_side = max_side

    def normalize_for_nanabanana(
        self,
        image_bytes: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Normalize image for nanabanana edit input.

        Returns:
            tuple: (normalized_bytes, mime_type, output_format)
        """
        try:
            image = self._open_image(image_bytes, content_type=content_type)
        except ValueError:
            raise
        except UnidentifiedImageError as exc:
            raise ValueError(
                self._build_decode_error_message(filename=filename, content_type=content_type)
            ) from exc

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

    def _open_image(self, image_bytes: bytes, content_type: Optional[str] = None) -> Image.Image:
        """Open common images and retry with HEIF/HEIC plugin when needed."""
        try:
            return Image.open(BytesIO(image_bytes))
        except UnidentifiedImageError:
            major_brand = self._extract_isobmff_major_brand(image_bytes)
            if major_brand not in self._heif_avif_brands():
                raise

            if not self._register_heif_opener():
                raise ValueError(
                    self._build_missing_heif_decoder_message(
                        major_brand=major_brand,
                        content_type=content_type,
                    )
                ) from None

            return Image.open(BytesIO(image_bytes))

    @staticmethod
    def _extract_isobmff_major_brand(image_bytes: bytes) -> Optional[bytes]:
        """Extract ISO BMFF major_brand from ftyp header, if present."""
        if len(image_bytes) < 12:
            return None
        if image_bytes[4:8] != b"ftyp":
            return None
        return image_bytes[8:12].lower()

    @staticmethod
    def _heif_avif_brands() -> set[bytes]:
        return {
            b"heic",
            b"heix",
            b"hevc",
            b"hevx",
            b"heim",
            b"heis",
            b"mif1",
            b"msf1",
            b"avif",
            b"avis",
        }

    @classmethod
    def _register_heif_opener(cls) -> bool:
        """Try to enable HEIF support in Pillow only once."""
        if cls._heif_registration_attempted:
            return cls._heif_supported

        cls._heif_registration_attempted = True
        try:
            from pillow_heif import register_heif_opener  # pyright: ignore[reportMissingImports]

            register_heif_opener()
            cls._heif_supported = True
        except Exception:
            cls._heif_supported = False

        return cls._heif_supported

    @classmethod
    def _build_decode_error_message(cls, filename: Optional[str], content_type: Optional[str]) -> str:
        extension = cls._extract_extension(filename)
        if content_type == "image/svg+xml" or extension == "svg":
            return (
                "SVG is not supported for upload. Please upload a raster image "
                f"({cls._popular_raster_formats})."
            )

        if extension in {"cr2", "nef", "arw", "dng", "rw2", "orf"}:
            return (
                "Camera RAW files are not supported for upload. "
                f"Please convert to one of: {cls._popular_raster_formats}."
            )

        return (
            "Could not decode the uploaded image. Please upload a valid raster image "
            f"({cls._popular_raster_formats})."
        )

    @staticmethod
    def _extract_extension(filename: Optional[str]) -> str:
        if not filename:
            return ""
        return Path(filename).suffix.lower().lstrip(".")

    @staticmethod
    def _build_missing_heif_decoder_message(major_brand: bytes, content_type: Optional[str]) -> str:
        if major_brand in {b"avif", b"avis"} or content_type == "image/avif":
            family = "AVIF"
        else:
            family = "HEIC/HEIF"
        return (
            f"{family} image support is unavailable on this server. "
            "Install 'pillow-heif' with libheif support and redeploy."
        )
