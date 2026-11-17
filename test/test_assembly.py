import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "src" / "assemble-pages-site.sh"


class SiteAssemblyTests(unittest.TestCase):
    def test_preserves_previous_reports_and_generates_coverage_and_landing_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing"
            old_report = existing / "run-12"
            old_report.mkdir(parents=True)
            (old_report / "index.html").write_text("old report")
            coverage = root / "coverage"
            coverage.mkdir()
            (coverage / "coverage-summary.json").write_text(json.dumps({
                "overallPercent": 73.5,
                "generatedAt": "2026-11-17T09:00:00Z",
                "pages": [{"label": "Dashboard", "percent": 73.5, "coveredStatements": 147, "totalStatements": 200}],
            }))
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("current report")
            site = root / "site"
            env = os.environ.copy()
            env.update({
                "SITE_DIR": str(site),
                "EXISTING_SITE_DIR": str(existing),
                "REPORT_DIR": str(report),
                "COVERAGE_DIR": str(coverage),
                "GITHUB_RUN_NUMBER": "24",
                "GITHUB_RUN_URL": "https://github.com/owner/repo/actions/runs/24",
                "GITHUB_WORKFLOW_NAME": "CI",
                "GITHUB_SHA_VALUE": "abc123",
            })
            subprocess.run(["bash", str(SCRIPT)], check=True, env=env, capture_output=True, text=True)

            self.assertEqual((site / "run-12" / "index.html").read_text(), "old report")
            self.assertEqual((site / "run-24" / "index.html").read_text(), "current report")
            self.assertTrue((site / "coverage" / "coverage-summary.json").is_file())
            self.assertIn("73.50%", (site / "coverage" / "index.html").read_text())
            landing = (site / "index.html").read_text()
            self.assertIn("run-24", landing)
            self.assertIn("run-12", landing)
            self.assertTrue((site / ".nojekyll").is_file())
            self.assertTrue((site / "404.html").is_file())

    def test_creates_placeholder_when_report_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            env = os.environ.copy()
            env.update({
                "SITE_DIR": str(site),
                "EXISTING_SITE_DIR": str(root / "no-existing-site"),
                "REPORT_DIR": str(root / "missing-report"),
                "COVERAGE_DIR": str(root / "missing-coverage"),
                "GITHUB_RUN_NUMBER": "25",
                "GITHUB_RUN_URL": "https://github.com/owner/repo/actions/runs/25",
                "GITHUB_WORKFLOW_NAME": "CI",
                "GITHUB_SHA_VALUE": "def456",
            })
            subprocess.run(["bash", str(SCRIPT)], check=True, env=env, capture_output=True, text=True)
            placeholder = (site / "run-25" / "index.html").read_text()
            self.assertIn("Report not available", placeholder)
            self.assertIn("Coverage unavailable", (site / "coverage" / "index.html").read_text())
            not_found = (site / "404.html").read_text()
            self.assertIn("This report was removed to keep the site within its size limit.", not_found)
            self.assertIn('<a href="./..">all reports page</a>', not_found)
            self.assertIn("window.location.href='./..'", not_found)

    def test_prunes_oldest_run_when_site_exceeds_configured_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing"
            old_report = existing / "run-1"
            old_report.mkdir(parents=True)
            (old_report / "index.html").write_text("x" * 2048)
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("current")
            site = root / "site"
            env = os.environ.copy()
            env.update({
                "SITE_DIR": str(site),
                "EXISTING_SITE_DIR": str(existing),
                "REPORT_DIR": str(report),
                "COVERAGE_DIR": str(root / "missing-coverage"),
                "PAGES_SIZE_LIMIT_BYTES": "1000",
                "GITHUB_RUN_NUMBER": "2",
                "GITHUB_RUN_URL": "https://github.com/owner/repo/actions/runs/2",
                "GITHUB_WORKFLOW_NAME": "CI",
                "GITHUB_SHA_VALUE": "abc123",
            })
            subprocess.run(["bash", str(SCRIPT)], check=True, env=env, capture_output=True, text=True)
            self.assertFalse((site / "run-1").exists())
            self.assertTrue((site / "run-2" / "index.html").is_file())

    def test_does_not_publish_report_over_per_report_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing"
            old_current = existing / "run-26"
            old_current.mkdir(parents=True)
            (old_current / "index.html").write_text("previous attempt")
            report = root / "report"
            report.mkdir()
            (report / "index.html").write_text("too large")
            site = root / "site"
            env = os.environ.copy()
            env.update({
                "SITE_DIR": str(site),
                "EXISTING_SITE_DIR": str(existing),
                "REPORT_DIR": str(report),
                "COVERAGE_DIR": str(root / "missing-coverage"),
                "MAX_REPORT_SIZE_BYTES": "4",
                "GITHUB_RUN_NUMBER": "26",
                "GITHUB_RUN_URL": "https://github.com/owner/repo/actions/runs/26",
                "GITHUB_WORKFLOW_NAME": "CI",
                "GITHUB_SHA_VALUE": "abc123",
            })
            subprocess.run(["bash", str(SCRIPT)], check=True, env=env, capture_output=True, text=True)
            self.assertFalse((site / "run-26").exists())


if __name__ == "__main__":
    unittest.main()
