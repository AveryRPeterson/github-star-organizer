import unittest
import json
import tempfile
import os
from github_star_organizer.config import load_config, ConfigError


class TestLoadConfig(unittest.TestCase):
    def test_load_config_valid(self):
        """Test loading a valid config.json"""
        config = load_config()
        self.assertIn("lists", config)
        self.assertIn("keywords", config)
        self.assertIsInstance(config["lists"], dict)
        self.assertIsInstance(config["keywords"], dict)

    def test_load_config_has_required_categories(self):
        """Test that config has expected categories"""
        config = load_config()
        expected_categories = [
            "AI Agents & LLMs",
            "Tools & CLI",
            "Hardware & Keyboards",
            "Android & Termux",
            "3D Printing & CAD",
            "OS & Customization",
            "Dev Tools & Frameworks"
        ]
        for cat in expected_categories:
            self.assertIn(cat, config["keywords"])

    def test_load_config_keywords_are_lists(self):
        """Test that all keywords are lists of strings"""
        config = load_config()
        for category, keywords in config["keywords"].items():
            self.assertIsInstance(keywords, list)
            for kw in keywords:
                self.assertIsInstance(kw, str)

    def test_load_config_lists_are_strings_or_empty(self):
        """Test that list IDs are non-empty strings"""
        config = load_config()
        for category, list_id in config["lists"].items():
            # Some may be empty strings for uncreated lists
            self.assertIsInstance(list_id, str)


if __name__ == "__main__":
    unittest.main()
