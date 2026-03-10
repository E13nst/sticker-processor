"""Unit tests for WaveSpeed request model."""
import pytest

from app.models.requests import WaveSpeedGenerateRequest


@pytest.mark.unit
class TestWaveSpeedGenerateRequest:
    """Validation tests for WaveSpeed request payload."""

    def test_valid_defaults(self):
        req = WaveSpeedGenerateRequest(prompt="Cute fox sticker")
        assert req.model == "flux-schnell"
        assert req.remove_background is False
        assert req.size == "512*512"

    def test_valid_model_flux(self):
        req = WaveSpeedGenerateRequest(prompt="test", model="flux-schnell")
        assert req.model == "flux-schnell"

    def test_valid_model_nanabanana_with_source_image(self):
        req = WaveSpeedGenerateRequest(
            prompt="test",
            model="nanabanana",
            source_image_url="https://example.com/image.png",
        )
        assert req.model == "nanabanana"
    
    def test_valid_model_nanabanana_text_to_image(self):
        req = WaveSpeedGenerateRequest(
            prompt="test",
            model="nanabanana",
        )
        assert req.model == "nanabanana"

    def test_invalid_model(self):
        with pytest.raises(ValueError, match="model must be one of"):
            WaveSpeedGenerateRequest(prompt="test", model="bad-model")

    @pytest.mark.parametrize("size", ["512x512", "abc", "512*foo", "10240*256"])
    def test_invalid_size(self, size):
        with pytest.raises(ValueError):
            WaveSpeedGenerateRequest(prompt="test", size=size)

    def test_source_image_legacy_field_is_supported(self):
        req = WaveSpeedGenerateRequest(prompt="test", image="abc123")
        assert req.source_image_base64 == "abc123"

    def test_source_image_url_or_base64_exclusive(self):
        with pytest.raises(ValueError, match="Use only one source image field"):
            WaveSpeedGenerateRequest(
                prompt="test",
                source_image_base64="a",
                source_image_url="https://example.com/image.png",
            )

    def test_legacy_image_conflicts_with_new_fields(self):
        with pytest.raises(ValueError, match="cannot be combined"):
            WaveSpeedGenerateRequest(
                prompt="test",
                image="legacy",
                source_image_base64="new",
            )

    def test_swagger_placeholder_strings_are_ignored(self):
        req = WaveSpeedGenerateRequest(
            prompt="fat gold cat with rick and morty style",
            model="nanabanana",
            image="string",
            source_image_base64="string",
            source_image_url="string",
        )
        assert req.source_image_base64 is None
        assert req.source_image_url is None

