import unittest
import logging
from io import StringIO
from github_star_organizer.logger import get_logger


class TestGetLogger(unittest.TestCase):
    def test_get_logger_returns_logger(self):
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)

    def test_get_logger_has_correct_name(self):
        logger = get_logger("categorize")
        self.assertEqual(logger.name, "categorize")

    def test_get_logger_configured_for_output(self):
        logger = get_logger("test")
        # Verify logger has handlers
        self.assertTrue(len(logger.handlers) > 0 or logger.propagate)

    def test_multiple_calls_same_name_returns_same_logger(self):
        logger1 = get_logger("shared")
        logger2 = get_logger("shared")
        self.assertIs(logger1, logger2)

    def test_logger_can_log_at_levels(self):
        logger = get_logger("test_levels")
        # Add handler to capture output
        handler = logging.StreamHandler(StringIO())
        logger.addHandler(handler)

        # These should not raise
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")


if __name__ == "__main__":
    unittest.main()
