import pytest

from scripts.guard_deep_regression import REQUIRED_CONFIRMATION, validate_deep_regression_safety


SAFE_ENV = {
    "APP_ENV": "local",
    "ALLOW_REAL_INTEGRATION_TESTS": "1",
    "WEB_DEEP_RESET_DEMO_DB": "1",
    "WEB_DEEP_CONFIRM": REQUIRED_CONFIRMATION,
    "WEB_DEEP_EXTERNAL_PREFIX": "DEEP_TEST",
    "FRONTEND_ORIGIN": "http://127.0.0.1:3000",
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_DB": "enterprise_ai",
    "FEISHU_APP_TOKEN": "",
    "FEISHU_TABLE_ID": "",
    "DIFY_WORKFLOW_ID": "",
}


def set_safe_env(monkeypatch):
    for key, value in SAFE_ENV.items():
        monkeypatch.setenv(key, value)


def test_deep_guard_allows_strict_local_confirmation(monkeypatch):
    set_safe_env(monkeypatch)
    summary = validate_deep_regression_safety()
    assert summary["ok"] is True


def test_deep_guard_blocks_missing_confirmation(monkeypatch):
    set_safe_env(monkeypatch)
    monkeypatch.setenv("WEB_DEEP_CONFIRM", "")
    with pytest.raises(RuntimeError) as exc_info:
        validate_deep_regression_safety()
    assert "WEB_DEEP_CONFIRM" in str(exc_info.value)


def test_deep_guard_blocks_missing_explicit_app_env(monkeypatch):
    set_safe_env(monkeypatch)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        validate_deep_regression_safety()
    assert "APP_ENV must be explicitly set to local" in str(exc_info.value)


@pytest.mark.parametrize("app_env", ["demo", "test", "ci", "production"])
def test_deep_guard_blocks_non_local_app_env(monkeypatch, app_env):
    set_safe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", app_env)
    with pytest.raises(RuntimeError) as exc_info:
        validate_deep_regression_safety()
    assert "APP_ENV must be exactly" in str(exc_info.value) or "production-like" in str(exc_info.value)


@pytest.mark.parametrize("missing_key", ["ALLOW_REAL_INTEGRATION_TESTS", "WEB_DEEP_RESET_DEMO_DB", "WEB_DEEP_CONFIRM"])
def test_deep_guard_blocks_missing_required_confirmation_vars(monkeypatch, missing_key):
    set_safe_env(monkeypatch)
    monkeypatch.delenv(missing_key, raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        validate_deep_regression_safety()
    assert missing_key in str(exc_info.value)


def test_deep_guard_blocks_production_like_env(monkeypatch):
    set_safe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MYSQL_DB", "enterprise_ai_prod")
    with pytest.raises(RuntimeError) as exc_info:
        validate_deep_regression_safety()
    assert "production-like" in str(exc_info.value) or "not allowed" in str(exc_info.value)
