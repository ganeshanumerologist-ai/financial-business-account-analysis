"""Power BI-style visual gallery: contract, empty states and language labels."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import analytics, db, visuals
from app.demo import seed_demo


class VisualGalleryTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        seed_demo(self.conn)
        self.tenant = self.conn.execute(
            "SELECT * FROM tenant WHERE slug='arthivio-demo'").fetchone()

    def tearDown(self):
        self.conn.close()

    def test_catalogue_has_every_requested_visual(self):
        payload = visuals.gallery(self.conn, self.tenant,
                                  "2026-04-01", "2026-10-31", "en")
        groups = {group["key"]: group for group in payload["groups"]}
        self.assertEqual(set(groups), set(visuals.EXPECTED_VISUALS))
        present = {visual["key"] for group in payload["groups"]
                   for visual in group["visuals"]}
        expected = {key for keys in visuals.EXPECTED_VISUALS.values()
                    for key in keys}
        self.assertEqual(present, expected)
        self.assertTrue(payload["actuals_only"])
        self.assertFalse(payload["forecast_included"])
        self.assertGreaterEqual(len(visuals.chart_items(payload)), 20)

    def test_totals_reconcile_to_analytics_contract(self):
        payload = visuals.gallery(self.conn, self.tenant,
                                  "2026-04-01", "2026-10-31", "en")
        overview = analytics.overview(self.conn, self.tenant,
                                      "2026-04-01", "2026-10-31")
        self.assertEqual(payload["totals"]["revenue_paise"],
                         overview["metrics"]["revenue_paise"])
        self.assertEqual(payload["totals"]["expense_paise"],
                         overview["metrics"]["expense_paise"])
        self.assertEqual(payload["totals"]["profit_paise"],
                         overview["metrics"]["net_profit_paise"])

    def test_empty_period_still_lists_the_visual_types(self):
        payload = visuals.gallery(self.conn, self.tenant,
                                  "2020-01-01", "2020-01-31", "en")
        present = {visual["key"] for group in payload["groups"]
                   for visual in group["visuals"]}
        expected = {key for keys in visuals.EXPECTED_VISUALS.values()
                    for key in keys}
        self.assertEqual(present, expected)
        empty = [visual for group in payload["groups"]
                 for visual in group["visuals"] if visual.get("kind") == "empty"]
        self.assertGreaterEqual(len(empty), 10)
        self.assertIn("No posted actuals", empty[0]["note"])

    def test_hindi_titles_and_devanagari_safe_payload(self):
        payload = visuals.gallery(self.conn, self.tenant,
                                  "2026-04-01", "2026-10-31", "hi")
        titles = {visual["title"] for group in payload["groups"]
                  for visual in group["visuals"]}
        self.assertIn("क्लस्टर्ड कॉलम", titles)
        self.assertIn("स्मार्ट नैरेटिव", titles)
        self.assertTrue(payload["map"]["url"].endswith("india_states.geojson"))

    def test_map_series_uses_bundled_state_names(self):
        payload = visuals.gallery(self.conn, self.tenant,
                                  "2026-04-01", "2026-10-31", "en")
        map_visual = next(visual for group in payload["groups"]
                          for visual in group["visuals"]
                          if visual["key"] == "map")
        names = {item["name"] for item in
                 map_visual["option"]["series"][0]["data"]}
        self.assertTrue(names)
        self.assertTrue(names.issubset(set(visuals.STATE_NAMES.values())))


if __name__ == "__main__":
    unittest.main()
