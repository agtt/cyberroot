"""Offline checks for cyber cve: scoring, KEV marks, filters and the stale-cache fallback."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cve  # noqa: E402

CVE = {"id": "CVE-2026-0001", "published": "2026-11-09T10:00:00.000", "vulnStatus": "Analyzed",
       "descriptions": [{"lang": "es", "value": "x"}, {"lang": "en", "value": "Command  injection\nin Foo"}],
       "weaknesses": [{"description": [{"value": "CWE-78"}, {"value": "NVD-CWE-noinfo"}]}],
       "metrics": {"cvssMetricV40": [{"type": "Secondary", "cvssData": {"baseScore": 9.3, "baseSeverity": "CRITICAL"}}],
                   "cvssMetricV31": [{"type": "Secondary", "cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}},
                                     {"type": "Primary", "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]},
       "references": [{"url": "https://example.com/a"}]}


class FakeFeed:
    def __init__(self, kev):
        self.kev = kev

    def get(self, url, ttl):
        return {"vulnerabilities": self.kev}


class CveTests(unittest.TestCase):
    def test_row_prefers_nvd_cvss31_and_marks_kev(self):
        r = cve.row(CVE, {"CVE-2026-0001": {"dateAdded": "2026-11-10", "knownRansomwareCampaignUse": "Known"}})
        self.assertEqual((r["score"], r["severity"]), (9.8, "CRITICAL"))
        self.assertEqual(r["description"], "Command injection in Foo")
        self.assertEqual(r["cwe"], ["CWE-78"])
        self.assertTrue(r["kev"] and r["ransomware"])
        self.assertEqual(cve.score({"metrics": {}}), (None, ""))

    def test_kev_recent_filters_by_date_and_keywords(self):
        today = dt.date.today()
        feed = FakeFeed([
            {"cveID": "CVE-1", "dateAdded": today.isoformat(), "vendorProject": "Cisco", "product": "IOS", "vulnerabilityName": "Cisco IOS RCE"},
            {"cveID": "CVE-2", "dateAdded": (today - dt.timedelta(days=40)).isoformat(), "vendorProject": "Cisco", "product": "ASA"},
            {"cveID": "CVE-3", "dateAdded": today.isoformat(), "vendorProject": "Google", "product": "Chromium"},
        ])
        self.assertEqual([r["id"] for r in cve.kev_recent(feed, 7, ["cisco"])], ["CVE-1"])
        self.assertEqual(len(cve.kev_recent(feed, 60, [])), 3)

    def test_unreachable_feed_uses_stale_cache(self):
        with tempfile.TemporaryDirectory() as cache:
            url = "https://127.0.0.1:9/feed.json"
            path = Path(cache, hashlib.sha1(url.encode()).hexdigest() + ".json")
            path.write_text(json.dumps({"ok": 1}))
            os.utime(path, (0, 0))
            self.assertEqual(cve.Feed(cache).get(url, 60), {"ok": 1})
            with self.assertRaises(SystemExit):
                cve.Feed(cache).get("https://127.0.0.1:9/other.json", 60)


if __name__ == "__main__":
    unittest.main()
