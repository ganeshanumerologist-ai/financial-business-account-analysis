"""English/Hindi shell dictionary and language preference fallbacks."""
from __future__ import annotations

import unittest

from app import i18n, server


class I18nTest(unittest.TestCase):
    def test_translation_and_safe_fallback(self):
        self.assertEqual(i18n.t("hi", "Dashboard"), "डैशबोर्ड")
        self.assertEqual(i18n.t("hi", "Not a translated key"), "Not a translated key")
        self.assertEqual(i18n.t("en", "Dashboard"), "Dashboard")
        self.assertEqual(i18n.normalize_language("HI"), "hi")
        self.assertEqual(i18n.normalize_language("fr"), "en")
        self.assertEqual(i18n.normalize_language(None), "en")

    def test_hindi_navigation_and_shell(self):
        nav = server.nav_html("", "hi")
        for text in ("डैशबोर्ड", "लेन-देन", "रिपोर्ट्स", "सेटिंग्स",
                     "चालान", "बिक्री", "खाता"):
            self.assertIn(text, nav)

        user = {"full_name": "Test User", "language": "hi"}
        tenant = {"name": "Test Co"}
        page = server.layout("Dashboard", "<p>body</p>", "", user, tenant)
        self.assertIn('<html lang="hi"', page)
        self.assertIn("डैशबोर्ड", page)
        self.assertIn("साइन आउट", page)
        self.assertIn('href="/language?lang=en"', page)
        self.assertIn("राशियाँ INR में", page)

    def test_old_user_without_language_column_falls_back(self):
        self.assertEqual(i18n.language_for({"full_name": "Old User"}), "en")
        self.assertEqual(i18n.language_for(None), "en")


if __name__ == "__main__":
    unittest.main()
