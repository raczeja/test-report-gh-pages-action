import os
from pathlib import Path
import runpy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_age_retention_removes_reports_older_than_configured_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("new report")
            site = root / "site"
            old = site / "run-1"
            old.mkdir(parents=True)
            (old / "index.html").write_text("old report")
            recent = site / "run-2"
            recent.mkdir()
            (recent / "index.html").write_text("recent report")
            old_date = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            recent_date = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
            (site / "reports.json").write_text(
                '{"reports":['
                '{"run_number":"1","run_url":"https://example.test/1",'
                f'"report_type":"Playwright","path":"run-1","created_at":"{old_date}"'
                '},{"run_number":"2","run_url":"https://example.test/2",'
                f'"report_type":"Playwright","path":"run-2","created_at":"{recent_date}"'
                '}]}'
            )
            landing = site / "index.html"
            landing.write_text('<a href="./run-1/">run-1</a>\n<a href="./run-2/">run-2</a>\n')
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(site),
                "INPUT_DESTINATION": "run-3",
                "INPUT_RUN_NUMBER": "3",
                "INPUT_RUN_URL": "https://example.test/3",
            })
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertNotIn("run-1", landing.read_text())
            self.assertIn("run-2", landing.read_text())
            self.assertNotIn("run-1", (site / "reports.html").read_text())

    def test_zero_age_limit_disables_age_pruning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("new report")
            site = root / "site"
            old = site / "run-1"
            old.mkdir(parents=True)
            (old / "index.html").write_text("old report")
            old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            (site / "reports.json").write_text(
                '{"reports":[{"run_number":"1","run_url":"https://example.test/1",'
                f'"report_type":"Playwright","path":"run-1","created_at":"{old_date}"'
                '}]}'
            )
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(site),
                "INPUT_DESTINATION": "run-2",
                "INPUT_RUN_NUMBER": "2",
                "INPUT_RUN_URL": "https://example.test/2",
                "INPUT_MAX_REPORT_AGE_DAYS": "0",
            })
            self.assertTrue(old.exists())

    def test_size_retention_removes_old_reports_until_site_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("new report")
            site = root / "site"
            old = site / "run-1"
            old.mkdir(parents=True)
            (old / "index.html").write_text("x" * 2048)
            old_current = site / "run-4"
            old_current.mkdir()
            (old_current / "index.html").write_text("previous attempt")
            newer = site / "run-2"
            newer.mkdir()
            (newer / "index.html").write_text("newer report")
            (site / "reports.json").write_text(
                '{"reports":[{"run_number":"1","run_url":"https://example.test/1",'
                '"report_type":"Playwright","path":"run-1"},'
                '{"run_number":"2","run_url":"https://example.test/2",'
                '"report_type":"Playwright","path":"run-2"}]}'
            )
            (site / ".git").mkdir()
            (site / ".git" / "history").write_text("commit history")
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(site),
                "INPUT_DESTINATION": "run-3",
                "INPUT_RUN_NUMBER": "3",
                "INPUT_RUN_URL": "https://example.test/3",
                "INPUT_MAX_SITE_SIZE_BYTES": "2000",
            })
            self.assertFalse(old.exists())
            self.assertTrue((site / "run-2/index.html").is_file())
            self.assertTrue((site / "run-3/index.html").is_file())
            self.assertFalse((site / ".git").exists())
            self.assertLessEqual(
                sum(path.lstat().st_size for path in site.rglob("*") if not path.is_dir()),
                2000,
            )
            self.assertNotIn("run-1", (site / "reports.html").read_text())

    def test_report_over_limit_is_not_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("too large")
            output = root / "output"
            self.run_action({
                "INPUT_REPORT_DIRECTORY": str(report),
                "INPUT_SITE_DIRECTORY": str(root / "site"),
                "INPUT_DESTINATION": "run-4",
                "INPUT_RUN_NUMBER": "4",
                "INPUT_RUN_URL": "https://example.test/4",
                "INPUT_MAX_REPORT_SIZE_BYTES": "4",
                "GITHUB_OUTPUT": str(output),
            })
            self.assertFalse((root / "site/run-4").exists())
            self.assertIn("published=false", output.read_text())


if __name__ == "__main__":
    unittest.main()
