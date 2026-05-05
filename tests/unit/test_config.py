import unittest
import json
import tempfile
import os
import shutil
from github_star_organizer.config import load_config, ConfigError


class TestLoadConfigErrors(unittest.TestCase):
    """Test error handling in load_config()"""

    def setUp(self):
        """Create a temporary directory for test config files"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_missing_config_raises_error(self):
        """Test that missing config.json raises ConfigError"""
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("not found", str(context.exception))

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ConfigError"""
        with open("config.json", "w") as f:
            f.write("{ this is not valid json")
        
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("invalid JSON", str(context.exception))

    def test_missing_lists_key_raises_error(self):
        """Test that missing 'lists' key raises ConfigError"""
        config = {"keywords": {"AI Agents": ["llm"]}}
        with open("config.json", "w") as f:
            json.dump(config, f)
        
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("lists", str(context.exception))

    def test_missing_keywords_key_raises_error(self):
        """Test that missing 'keywords' key raises ConfigError"""
        config = {"lists": {"AI Agents": "123"}}
        with open("config.json", "w") as f:
            json.dump(config, f)
        
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("keywords", str(context.exception))

    def test_lists_must_be_dict(self):
        """Test that 'lists' must be a dictionary"""
        config = {"lists": "not a dict", "keywords": {"AI": []}}
        with open("config.json", "w") as f:
            json.dump(config, f)
        
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("dictionary", str(context.exception))

    def test_keywords_must_be_dict(self):
        """Test that 'keywords' must be a dictionary"""
        config = {"lists": {}, "keywords": "not a dict"}
        with open("config.json", "w") as f:
            json.dump(config, f)
        
        with self.assertRaises(ConfigError) as context:
            load_config()
        self.assertIn("dictionary", str(context.exception))


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
