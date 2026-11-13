"""DigiCert credential must come from this backend directory’s .env file."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

class DigiCertKeyConfigurationTests(unittest.TestCase):
    def test_uses_only_dotenv_value(self):
        from app.core.config import Settings

        with patch.dict(os.environ, {"DIGICERT_API_KEY": "process-value"}), patch(
            "app.core.config.dotenv_values",
            return_value={"DIGICERT_API_KEY": "file-value"},
        ) as read_dotenv:
            self.assertEqual(Settings().digicert_api_key, "file-value")
            self.assertEqual(read_dotenv.call_args.args[0],
                             Path(__file__).resolve().parents[1] / ".env")
            self.assertFalse(read_dotenv.call_args.kwargs["interpolate"])

    def test_missing_dotenv_key_has_no_fallback(self):
        from app.core.config import Settings

        with patch.dict(os.environ, {"DIGICERT_API_KEY": "process-value"}), patch(
            "app.core.config.dotenv_values", return_value={},
        ):
            self.assertEqual(Settings().digicert_api_key, "")


if __name__ == "__main__":
    unittest.main()
