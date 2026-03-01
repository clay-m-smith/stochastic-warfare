"""Tests for core/logging.py."""

import logging

from stochastic_warfare.core.logging import configure_logging, get_logger


class TestGetLogger:
    def test_namespace(self) -> None:
        log = get_logger("core.rng")
        assert log.name == "stochastic_warfare.core.rng"

    def test_returns_logger_instance(self) -> None:
        log = get_logger("combat")
        assert isinstance(log, logging.Logger)

    def test_same_name_returns_same_logger(self) -> None:
        a = get_logger("movement")
        b = get_logger("movement")
        assert a is b


class TestConfigureLogging:
    def test_sets_level(self) -> None:
        configure_logging(level="DEBUG")
        root = logging.getLogger("stochastic_warfare")
        assert root.level == logging.DEBUG

    def test_console_handler_added(self) -> None:
        configure_logging(level="INFO")
        root = logging.getLogger("stochastic_warfare")
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_file_handler(self, tmp_path) -> None:
        log_file = tmp_path / "test.log"
        configure_logging(level="INFO", log_file=log_file)
        root = logging.getLogger("stochastic_warfare")
        assert any(isinstance(h, logging.FileHandler) for h in root.handlers)
        # Write a message and verify it appears in the file
        logger = get_logger("test_mod")
        logger.info("hello file")
        for h in root.handlers:
            h.flush()
        assert "hello file" in log_file.read_text()

    def test_module_level_override(self) -> None:
        configure_logging(level="WARNING", module_levels={"core.rng": "DEBUG"})
        rng_log = logging.getLogger("stochastic_warfare.core.rng")
        assert rng_log.level == logging.DEBUG
        # Parent stays at WARNING
        root = logging.getLogger("stochastic_warfare")
        assert root.level == logging.WARNING

    def test_format_contains_expected_fields(self) -> None:
        configure_logging(level="INFO")
        root = logging.getLogger("stochastic_warfare")
        handler = root.handlers[0]
        fmt = handler.formatter._fmt  # type: ignore[union-attr]
        assert "%(asctime)s" in fmt
        assert "%(name)s" in fmt
        assert "%(levelname)s" in fmt

    def test_reconfigure_clears_old_handlers(self) -> None:
        configure_logging(level="INFO")
        configure_logging(level="DEBUG")
        root = logging.getLogger("stochastic_warfare")
        # Should have exactly 1 handler (console), not 2
        assert len(root.handlers) == 1
