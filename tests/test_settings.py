import unittest

from luna.settings import Settings, SettingsError, load_settings

VALID = {
    "BOT_TOKEN": "123456:ABC-def_ghi",
    "ARQ_API_KEY": "key",
    "ARQ_API_URL": "https://arq.example",
    "API_ID": "6",
    "API_HASH": "hash",
}


class SettingsTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            load_settings(VALID),
            Settings(bot_token="123456:ABC-def_ghi", api_id=6, api_hash="hash",
                     arq_api_url="https://arq.example", arq_api_key="key"),
        )

    def test_every_problem_at_once(self):
        with self.assertRaises(SettingsError) as caught:
            load_settings({"API_ID": "six"})
        message = str(caught.exception)
        for name in ("BOT_TOKEN is missing", "ARQ_API_KEY is missing", "ARQ_API_URL is missing",
                     "API_ID must be a number", "API_HASH is missing"):
            self.assertIn(name, message)

    def test_bad_token_is_not_echoed(self):
        with self.assertRaises(SettingsError) as caught:
            load_settings({**VALID, "BOT_TOKEN": "secret-token"})
        self.assertIn("BOT_TOKEN does not look like a bot token", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    def test_url_needs_a_scheme(self):
        with self.assertRaises(SettingsError) as caught:
            load_settings({**VALID, "ARQ_API_URL": "arq.example"})
        self.assertIn("ARQ_API_URL must start with https://", str(caught.exception))

    def test_blank_is_missing(self):
        with self.assertRaises(SettingsError) as caught:
            load_settings({**VALID, "ARQ_API_KEY": "   "})
        self.assertIn("ARQ_API_KEY is missing", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
