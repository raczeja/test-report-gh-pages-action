import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[1] / "src" / "main.py"


class ReportActionTests(unittest.TestCase):
    def run_action(self, env):
        with patch.dict(os.environ, env, clear=True):
            runpy.run_path(str(SOURCE), run_name="__main__")

    def test_stages_static_report_and_indexes_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "allure"
            report.mkdir()
            (report / "index.html").write_text("<h1>Allure</h1>")
            output = root / "output"
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(root / "site"),
                "INPUT_REPORT_TYPE": "Allure",
                "INPUT_DESTINATION": "run-42",
                "INPUT_RUN_NUMBER": "42",
                "INPUT_RUN_URL": "https://example.test/run/42",
                "GITHUB_OUTPUT": str(output),
            })
            self.assertEqual((root / "site/run-42/index.html").read_text(), "<h1>Allure</h1>")
            index = (root / "site/reports.html").read_text()
            self.assertIn("Allure reports", index)
            self.assertIn("run-42", index)
            self.assertIn("report-url-path=run-42/", output.read_text())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").touch()
            with self.assertRaises(SystemExit):
                self.run_action({
                    "INPUT_REPORT_DIRECTORY": str(report),
                    "INPUT_SITE_DIRECTORY": str(root / "site"),
                    "INPUT_DESTINATION": "../escape",
                    "INPUT_RUN_NUMBER": "2",
                })

    def test_count_retention_removes_oldest_published_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("new report")
            site = root / "site"
            old = site / "run-1"
            old.mkdir(parents=True)
            (old / "index.html").write_text("old report")
            (site / "reports.json").write_text(
                '{"reports":[{"run_number":"1","run_url":"https://example.test/1",'
                '"report_type":"Playwright","path":"run-1"}]}'
            )
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(site),
                "INPUT_DESTINATION": "run-2",
                "INPUT_RUN_NUMBER": "2",
                "INPUT_RUN_URL": "https://example.test/2",
                "INPUT_MAX_REPORTS": "1",
                "INPUT_MAX_REPORT_SIZE_MB": "0",
            })
            self.assertFalse(old.exists())
            self.assertTrue((site / "run-2/index.html").is_file())
            self.assertNotIn("run-1", (site / "reports.html").read_text())


if __name__ == "__main__":
    unittest.main()
