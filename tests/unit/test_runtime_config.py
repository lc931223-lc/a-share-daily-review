import json

import pytest

from src.config.runtime import RuntimeSettings


def test_runtime_allows_missing_tushare_token_for_eastmoney_primary(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    settings = RuntimeSettings.load()

    assert settings.pipeline.primary_market_source == "eastmoney"
    assert settings.tushare_token is None


def test_runtime_requires_tushare_token_for_tushare_primary(monkeypatch, tmp_path):
    config_path = tmp_path / "data_pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "rule_version": "test.1",
                "primary_market_source": "tushare",
                "tushare_role": "required_primary",
                "request_timeout_seconds": 15,
                "max_retries": 2,
                "major_indices": ["000001.SH"],
                "thresholds": {
                    "security_status_explained": 0.995,
                    "daily_quote_required_fields": 0.995,
                    "major_index_coverage": 1.0,
                    "limit_candidate_coverage": 0.98,
                    "supplemental_abs_diff": 2,
                    "supplemental_ratio_diff": 0.02,
                    "critical_conflicts": 0,
                },
                "eastmoney_fallback_fields": ["advancers"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TUSHARE_TOKEN"):
        RuntimeSettings.load(config_path=config_path)


def test_runtime_safe_dict_excludes_tushare_token(monkeypatch, tmp_path):
    config_path = tmp_path / "data_pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "rule_version": "test.1",
                "request_timeout_seconds": 15,
                "max_retries": 2,
                "major_indices": ["000001.SH"],
                "thresholds": {
                    "security_status_explained": 0.995,
                    "daily_quote_required_fields": 0.995,
                    "major_index_coverage": 1.0,
                    "limit_candidate_coverage": 0.98,
                    "supplemental_abs_diff": 2,
                    "supplemental_ratio_diff": 0.02,
                    "critical_conflicts": 0,
                },
                "eastmoney_fallback_fields": ["advancers"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-value")

    settings = RuntimeSettings.load(config_path=config_path)

    assert settings.tushare_token == "secret-value"
    assert "secret-value" not in str(settings.safe_dict())
    assert "tushare_token" not in settings.safe_dict()


def test_runtime_uses_config_path_from_environment(monkeypatch, tmp_path):
    config_path = tmp_path / "data_pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "rule_version": "env-path.1",
                "request_timeout_seconds": 10,
                "max_retries": 1,
                "major_indices": ["399001.SZ"],
                "thresholds": {
                    "security_status_explained": 0.995,
                    "daily_quote_required_fields": 0.995,
                    "major_index_coverage": 1.0,
                    "limit_candidate_coverage": 0.98,
                    "supplemental_abs_diff": 2,
                    "supplemental_ratio_diff": 0.02,
                    "critical_conflicts": 0,
                },
                "eastmoney_fallback_fields": ["limit_up"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-value")
    monkeypatch.setenv("DATA_PIPELINE_CONFIG", str(config_path))

    settings = RuntimeSettings.load()

    assert settings.pipeline.rule_version == "env-path.1"
