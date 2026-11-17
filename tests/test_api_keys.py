"""Settings-page API keys: validation, override of .env, masking; no network calls."""

import io
import json
import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from fastapi.testclient import TestClient
from backend import api_keys
from backend.app import app

FAKE = "sk-synthetic-test-key-1234"


def rejected(*_args, **_kwargs):
    raise HTTPError("https://example.test", 401, "Unauthorized", {}, io.BytesIO())


class ApiKeySettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.file = Path(self.tmp.name) / "api_keys.json"
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-dotenv-0000"})
        self.env.start()
        patch.object(api_keys, "API_KEYS_FILE", self.file).start()
        patch.object(api_keys, "load_dotenv", lambda: None).start()
        patch.object(api_keys, "_forget_checks", lambda: None).start()
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        api_keys.load()
        self.client = TestClient(app)

    def tearDown(self):
        patch.stopall()
        self.env.stop()
        self.tmp.cleanup()

    def test_valid_key_is_saved_privately_and_overrides_env(self):
        with patch.object(api_keys, "urlopen", MagicMock()):
            response = self.client.put(
                "/api/settings/keys/openai", json={"api_key": FAKE}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(os.environ["OPENAI_API_KEY"], FAKE)
        self.assertEqual(json.loads(self.file.read_text()), {"openai": FAKE})
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)
        openai = response.json()[0]
        self.assertEqual((openai["source"], openai["hint"]), ("settings", "…1234"))
        self.assertNotIn(FAKE, response.text)

    def test_rejected_key_is_not_saved(self):
        with patch.object(api_keys, "urlopen", rejected):
            response = self.client.put(
                "/api/settings/keys/anthropic", json={"api_key": FAKE}
            )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.file.exists())
        self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

    def test_removing_saved_key_restores_env_fallback(self):
        with patch.object(api_keys, "urlopen", MagicMock()):
            self.client.put("/api/settings/keys/openai", json={"api_key": FAKE})
        statuses = self.client.delete("/api/settings/keys/openai").json()
        self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-from-dotenv-0000")
        self.assertEqual(statuses[0]["source"], "env")
        self.assertIsNone(statuses[1]["source"])

    def test_saved_keys_apply_at_startup(self):
        self.file.write_text(json.dumps({"google": FAKE}))
        api_keys.load()
        self.assertEqual(os.environ["GOOGLE_API_KEY"], FAKE)

    def test_unknown_provider_is_rejected(self):
        response = self.client.put("/api/settings/keys/other", json={"api_key": FAKE})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
