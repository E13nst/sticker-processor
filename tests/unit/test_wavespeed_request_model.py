"""Unit tests for WaveSpeed request model."""
import pytest

from app.models.requests import WaveSpeedGenerateRequest, WaveSpeedSaveToSetRequest


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

    def test_valid_model_nanabanana_with_source_images(self):
        req = WaveSpeedGenerateRequest(
            prompt="test",
            model="nanabanana",
            source_image_urls=["https://example.com/image.png"],
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

    def test_reject_invalid_source_url(self):
        with pytest.raises(ValueError, match="source_image_urls"):
            WaveSpeedGenerateRequest(
                prompt="test",
                model="nanabanana",
                source_image_urls=["ftp://example.com/image.png"],
            )

    def test_reject_more_than_limit_sources(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            WaveSpeedGenerateRequest(
                prompt="test",
                model="nanabanana",
                source_image_ids=["img_1", "img_2", "img_3"],
                source_image_urls=["https://1", "https://2"],
            )

    def test_reject_multiple_sources_for_non_nanabanana(self):
        with pytest.raises(ValueError, match="Only nanabanana supports multiple source images"):
            WaveSpeedGenerateRequest(
                prompt="test",
                model="flux-schnell",
                source_image_urls=["https://example.com/1.png", "https://example.com/2.png"],
            )


@pytest.mark.unit
class TestWaveSpeedSaveToSetRequest:
    def test_valid_payload(self):
        req = WaveSpeedSaveToSetRequest(
            file_id="ws_abc123",
            user_id=123456,
            name="my_set_by_bot",
            title="My Sticker Set",
            emoji="😀",
        )
        assert req.file_id.startswith("ws_")
        assert req.wait_timeout_sec == 60
        assert req.emoji == "😀"

    def test_default_emoji_when_not_provided(self):
        req = WaveSpeedSaveToSetRequest(
            file_id="ws_abc123",
            user_id=123456,
            name="my_set_by_bot",
            title="My Sticker Set",
        )
        assert req.emoji == "😀"

    def test_invalid_file_id(self):
        with pytest.raises(ValueError, match="must start with 'ws_'"):
            WaveSpeedSaveToSetRequest(
                file_id="abc123",
                user_id=123456,
                name="my_set_by_bot",
                title="My Sticker Set",
                emoji="😀",
            )

