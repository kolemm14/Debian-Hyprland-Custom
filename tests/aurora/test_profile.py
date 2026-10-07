import unittest
import tempfile
import os
import sys

# Add the root directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.aurora.profile import AuroraProfileManager

class TestAuroraProfile(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = AuroraProfileManager(config_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_profile(self):
        self.assertEqual(self.manager.get_current_profile(), "balanced")

    def test_set_profile(self):
        self.manager.set_profile("lite")
        self.assertEqual(self.manager.get_current_profile(), "lite")
        
        active_conf = os.path.join(self.temp_dir.name, "hypr", "profiles", "active.conf")
        self.assertTrue(os.path.exists(active_conf))
        with open(active_conf, 'r') as f:
            content = f.read()
            self.assertIn("enabled = false", content) # Lite turns off animations/blur

    def test_eco_mode(self):
        self.manager.set_profile("ultra")
        self.manager.toggle_eco(True)
        active_conf = os.path.join(self.temp_dir.name, "hypr", "profiles", "active.conf")
        with open(active_conf, 'r') as f:
            content = f.read()
            self.assertIn("enabled = false", content) # Eco overrides ultra
