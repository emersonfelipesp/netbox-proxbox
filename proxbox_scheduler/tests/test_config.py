"""Tests for env parsing and ``SchedulerConfig`` defaults."""

from __future__ import annotations

import pytest

from proxbox_scheduler.config import (
    ConfigError,
    ModeKind,
    load_config,
    parse_mode,
)


class TestParseMode:
    def test_default_is_off(self) -> None:
        assert parse_mode(None).kind is ModeKind.OFF

    def test_empty_string_is_off(self) -> None:
        assert parse_mode("").kind is ModeKind.OFF
        assert parse_mode("   ").kind is ModeKind.OFF

    def test_literal_off(self) -> None:
        assert parse_mode("off").kind is ModeKind.OFF
        assert parse_mode("OFF").kind is ModeKind.OFF

    def test_continuous(self) -> None:
        assert parse_mode("continuous").kind is ModeKind.CONTINUOUS
        assert parse_mode("Continuous").kind is ModeKind.CONTINUOUS

    def test_interval(self) -> None:
        mode = parse_mode("interval=45")
        assert mode.kind is ModeKind.INTERVAL
        assert mode.interval_seconds == 45

    def test_interval_zero_rejected(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            parse_mode("interval=0")

    def test_interval_negative_rejected(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            parse_mode("interval=-3")

    def test_interval_non_integer_rejected(self) -> None:
        with pytest.raises(ConfigError, match="integer"):
            parse_mode("interval=foo")

    def test_cron_payload_preserved(self) -> None:
        mode = parse_mode("cron=0 */4 * * *")
        assert mode.kind is ModeKind.CRON
        assert mode.cron_expression == "0 */4 * * *"

    def test_cron_empty_payload_rejected(self) -> None:
        with pytest.raises(ConfigError, match="cron"):
            parse_mode("cron=")

    def test_unknown_mode_keyword_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Unknown"):
            parse_mode("burst=10")

    def test_malformed_value_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Invalid PROXBOX_MODE"):
            parse_mode("not-a-mode")


class TestLoadConfig:
    def test_defaults_off_invoke_http(self) -> None:
        config = load_config({})
        assert config.mode.kind is ModeKind.OFF
        assert config.invoke == "http"
        assert config.timezone.key == "UTC"
        assert config.backoff_seconds == 30.0
        assert config.log_level == "INFO"
        assert config.log_json is True
        assert config.exec_command[:3] == ["python", "manage.py", "proxbox_sync"]
        assert "--enqueue-once" in config.exec_command

    def test_off_mode_does_not_require_api_url(self) -> None:
        # PROXBOX_API_URL is only required when mode != off and invoke == http.
        config = load_config({"PROXBOX_MODE": "off"})
        assert config.proxbox_api_url is None

    def test_http_mode_requires_api_url(self) -> None:
        with pytest.raises(ConfigError, match="PROXBOX_API_URL"):
            load_config({"PROXBOX_MODE": "interval=60"})

    def test_exec_mode_does_not_require_api_url(self) -> None:
        config = load_config(
            {
                "PROXBOX_MODE": "interval=60",
                "PROXBOX_SCHEDULER_INVOKE": "exec",
            }
        )
        assert config.invoke == "exec"
        assert config.proxbox_api_url is None

    def test_tz_parsed(self) -> None:
        config = load_config(
            {
                "PROXBOX_MODE": "off",
                "PROXBOX_SCHEDULER_TZ": "America/Sao_Paulo",
            }
        )
        assert config.timezone.key == "America/Sao_Paulo"

    def test_unknown_tz_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Unknown timezone"):
            load_config({"PROXBOX_SCHEDULER_TZ": "Mars/Olympus_Mons"})

    def test_invalid_invoke_rejected(self) -> None:
        with pytest.raises(ConfigError, match="PROXBOX_SCHEDULER_INVOKE"):
            load_config({"PROXBOX_SCHEDULER_INVOKE": "carrier_pigeon"})

    def test_negative_backoff_rejected(self) -> None:
        with pytest.raises(ConfigError, match="non-negative"):
            load_config({"PROXBOX_SCHEDULER_BACKOFF_ON_ERROR_SECONDS": "-1"})

    def test_zero_api_timeout_rejected(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            load_config(
                {
                    "PROXBOX_MODE": "interval=60",
                    "PROXBOX_API_URL": "http://x",
                    "PROXBOX_API_TIMEOUT": "0",
                }
            )

    def test_verify_ssl_parses_booleans(self) -> None:
        for raw, expected in [
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
        ]:
            config = load_config(
                {
                    "PROXBOX_MODE": "off",
                    "PROXBOX_API_VERIFY_SSL": raw,
                }
            )
            assert config.proxbox_api_verify_ssl is expected, raw

    def test_verify_ssl_garbage_rejected(self) -> None:
        with pytest.raises(ConfigError, match="boolean"):
            load_config({"PROXBOX_API_VERIFY_SSL": "maybe"})

    def test_custom_exec_command_tokenized(self) -> None:
        config = load_config(
            {
                "PROXBOX_SCHEDULER_EXEC_CMD": "/bin/echo 'hello world'",
                "PROXBOX_SCHEDULER_INVOKE": "exec",
            }
        )
        assert config.exec_command == ["/bin/echo", "hello world"]
