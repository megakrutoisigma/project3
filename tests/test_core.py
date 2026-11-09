import unittest

from pc_stats import fmt_bytes, quick_stats, folder_info
from features import diagnose
from reports import text_report, html_report


class MonitorTests(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(fmt_bytes(1024), "1.0 КБ")

    def test_quick_stats(self):
        s = quick_stats()
        for field in ("cpu", "ram", "disk"):
            self.assertGreaterEqual(s[field], 0)
            self.assertLessEqual(s[field], 100)

    def test_diagnosis(self):
        msgs = diagnose({"cpu": 96, "ram": 96, "disk": 96, "processes": 5})
        self.assertTrue(any("CPU" in text for _, text in msgs))

    def test_folder(self):
        d = folder_info("tests")
        self.assertGreaterEqual(d["files"], 1)


if __name__ == "__main__":
    unittest.main()
