from src.product.settings import get_settings


def test_settings_exposes_api_base_url() -> None:
    settings = get_settings()
    assert settings.api_base_url
    assert settings.api_port > 0
