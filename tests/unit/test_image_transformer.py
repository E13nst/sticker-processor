"""Unit tests for image transformer HEIC fallback."""
import io
from unittest.mock import patch

import pytest
from PIL import Image, UnidentifiedImageError

from app.services.image_transformer import ImageTransformer


def _png_bytes() -> bytes:
    image = Image.new("RGB", (128, 128), color=(30, 120, 220))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.unit
def test_normalize_non_image_raises_validation_error():
    transformer = ImageTransformer()

    with pytest.raises(ValueError, match="Could not decode the uploaded image"):
        transformer.normalize_for_nanabanana(b"not-an-image")


@pytest.mark.unit
def test_normalize_heic_without_decoder_returns_config_error():
    transformer = ImageTransformer()
    heic_like_bytes = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"

    with patch("app.services.image_transformer.Image.open", side_effect=UnidentifiedImageError):
        with patch.object(ImageTransformer, "_register_heif_opener", return_value=False):
            with pytest.raises(ValueError, match="HEIC/HEIF image support is unavailable"):
                transformer.normalize_for_nanabanana(heic_like_bytes)


@pytest.mark.unit
def test_normalize_heic_retries_after_registering_decoder():
    transformer = ImageTransformer()
    heic_like_bytes = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
    decoded = Image.new("RGB", (64, 64), color=(255, 255, 255))

    with patch(
        "app.services.image_transformer.Image.open",
        side_effect=[UnidentifiedImageError("first open fails"), decoded],
    ):
        with patch.object(ImageTransformer, "_register_heif_opener", return_value=True):
            normalized, mime_type, output_format = transformer.normalize_for_nanabanana(heic_like_bytes)

    assert normalized
    assert mime_type == "image/jpeg"
    assert output_format == "jpg"


@pytest.mark.unit
def test_normalize_svg_returns_explicit_error_message():
    transformer = ImageTransformer()

    with pytest.raises(ValueError, match="SVG is not supported for upload"):
        transformer.normalize_for_nanabanana(
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            filename="icon.svg",
            content_type="image/svg+xml",
        )


@pytest.mark.unit
def test_normalize_raw_returns_explicit_error_message():
    transformer = ImageTransformer()

    with pytest.raises(ValueError, match="Camera RAW files are not supported"):
        transformer.normalize_for_nanabanana(
            b"raw-camera-bytes",
            filename="photo.nef",
            content_type="image/x-nikon-nef",
        )
