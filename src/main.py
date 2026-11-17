#!/usr/bin/env python3
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse


def remove_path(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def fail(message):
    print(f"test-report-gh-pages-action: {message}", file=sys.stderr)
    raise SystemExit(1)


def env(name, default=""):
    return os.environ.get(name, default)


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        json.dump(value, out, indent=2)
        out.write("\n")
        temp = Path(out.name)
    temp.replace(path)


def safe_manifest_path(site_dir, path_text):
    relative = Path(path_text)
    if relative.is_absolute() or not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        fail(f"manifest contains an unsafe report path: {path_text!r}")
    path = (site_dir / relative).resolve()
    if site_dir != path and site_dir not in path.parents:
        fail(f"manifest path resolves outside site-directory: {path_text!r}")
    return path


def main():
    report_directory = env("INPUT_REPORT_DIRECTORY")
    source = Path(report_directory).resolve() if report_directory else None
    site_dir = Path(env("INPUT_SITE_DIRECTORY", "site")).resolve()
    run_number = env("INPUT_RUN_NUMBER") or env("GITHUB_RUN_NUMBER", "0")
    destination = env("INPUT_DESTINATION") or f"run-{run_number}"
    report_type = env("INPUT_REPORT_TYPE", "Playwright")
    run_url = env("INPUT_RUN_URL") or (
        f"{env('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{env('GITHUB_REPOSITORY')}/actions/runs/{env('GITHUB_RUN_ID', '0')}"
    )

    if any("\n" in value or "\r" in value for value in (destination, run_number, report_type, run_url)):
        fail("destination, run-number, report-type, and run-url may not contain newlines")
    if source is not None and not source.is_dir():
        source = None
    if source is not None and not (source / "index.html").is_file():
        fail(f"report directory must contain index.html: {source}")
    if not re.fullmatch(r"[0-9]+", run_number):
        fail("run-number must contain only digits")
    relative = Path(destination)
    if relative.is_absolute() or not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        fail("destination must be a safe relative path within site-directory")
    if source is not None and any(path.is_symlink() for path in source.rglob("*")):
        fail("report directory may not contain symbolic links")
    try:
        max_reports = int(env("INPUT_MAX_REPORTS", "0"))
        max_report_age_days = int(env("INPUT_MAX_REPORT_AGE_DAYS", "7"))
        max_report_size_mb = int(env("INPUT_MAX_REPORT_SIZE_MB", "0"))
        max_report_size_bytes = int(env("INPUT_MAX_REPORT_SIZE_BYTES", "1000000000"))
        max_site_size_bytes = int(env("INPUT_MAX_SITE_SIZE_BYTES", "1000000000"))
    except ValueError:
        fail("report retention and size limits must be non-negative integers")
    if (
        max_reports < 0
        or max_report_age_days < 0
        or max_report_size_mb < 0
        or max_report_size_bytes < 0
        or max_site_size_bytes < 0
    ):
        fail("report retention and size limits must be non-negative integers")
    if max_report_size_mb:
        max_report_size_bytes = max_report_size_mb * 1024 * 1024
    source_size = (
        sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
        if source is not None else 0
    )
    skipped_oversize = max_report_size_bytes > 0 and source is not None and source_size > max_report_size_bytes
    if skipped_oversize:
        print(
            f"Skipping report ({source_size} bytes exceeds {max_report_size_bytes} bytes)",
            file=sys.stderr,
        )
        source = None
    parsed_url = urlparse(run_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        fail("run-url must be an absolute HTTP or HTTPS URL")

    site_dir.mkdir(parents=True, exist_ok=True)
    remove_path(site_dir / ".git")
    target = (site_dir / relative).resolve()
    if site_dir != target and site_dir not in target.parents:
        fail("destination resolves outside site-directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    if skipped_oversize:
        remove_path(target)

    if source is not None:
        staging = Path(tempfile.mkdtemp(prefix=".report-staging-", dir=target.parent))
        backup = target.with_name(target.name + ".previous")
        try:
            shutil.copytree(source, staging, dirs_exist_ok=True)
            if backup.exists():
                remove_path(backup)
            if target.exists():
                target.replace(backup)
            try:
                staging.replace(target)
            except OSError:
                if backup.exists() and not target.exists():
                    backup.replace(target)
                raise
            if backup.exists():
                remove_path(backup)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    manifest_path = site_dir / "reports.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(f"cannot read existing report manifest {manifest_path}: {exc}")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("reports"), list):
            fail(f"existing report manifest {manifest_path} must contain a reports array")
    else:
        manifest = {"reports": []}

    reports = []
    for entry in manifest["reports"]:
        if (
            not isinstance(entry, dict)
            or not re.fullmatch(r"[0-9]+", str(entry.get("run_number", "")))
            or not isinstance(entry.get("report_type"), str)
        ):
            fail(f"existing report manifest contains an invalid entry: {entry!r}")
        old_path = safe_manifest_path(site_dir, str(entry.get("path", "")))
        if old_path.is_dir() and (old_path / "index.html").is_file():
            if str(entry.get("run_number")) != run_number and entry.get("path") != relative.as_posix():
                reports.append(entry)
    if source is not None:
        reports.append({
            "run_number": run_number,
            "run_url": run_url,
            "report_type": report_type,
            "path": relative.as_posix(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    reports.sort(key=lambda item: int(item["run_number"]), reverse=True)
    if max_report_age_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_report_age_days)
        retained = []
        for entry in reports:
            created_at = entry.get("created_at")
            if created_at is None:
                retained.append(entry)
                continue
            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except ValueError:
                fail(f"existing report manifest contains an invalid created_at value: {created_at!r}")
            if created < cutoff:
                expired_path = safe_manifest_path(site_dir, entry["path"])
                remove_path(expired_path)
                landing_page = site_dir / "index.html"
                if landing_page.is_file() and re.fullmatch(r"run-[0-9]+", expired_path.name):
                    landing = landing_page.read_text(encoding="utf-8")
                    landing = re.sub(
                        rf'^.*href="\./{re.escape(expired_path.name)}/".*\n?',
                        "",
                        landing,
                        flags=re.MULTILINE,
                    )
                    landing_page.write_text(landing, encoding="utf-8")
            else:
                retained.append(entry)
        reports = retained
    if max_reports:
        for expired in reports[max_reports:]:
            remove_path(safe_manifest_path(site_dir, expired["path"]))
        reports = reports[:max_reports]
    def write_report_indexes():
        atomic_json(manifest_path, {"reports": reports})
        links = "\n".join(
            f'<li><a href="./{html.escape(entry["path"], quote=True)}/">'
            f'{html.escape(entry["report_type"])} — run #{html.escape(entry["run_number"])}</a></li>'
            for entry in reports
        ) or "<li>No reports published yet.</li>"
        index = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(report_type)} reports</title>"
            "<style>body{font:16px system-ui,sans-serif;max-width:50rem;margin:2rem auto;padding:0 1rem}"
            "li{margin:.5rem 0}a{color:#2563eb}</style></head><body>"
            f"<h1>{html.escape(report_type)} reports</h1><ul>{links}</ul>"
            f"<p>Current run: <a href=\"{html.escape(run_url, quote=True)}\">"
            f"#{html.escape(run_number)}</a></p></body></html>\n"
        )
        (site_dir / "reports.html").write_text(index, encoding="utf-8")

    write_report_indexes()

    def site_size_bytes():
        return sum(
            path.lstat().st_size
            for path in site_dir.rglob("*")
            if path.is_symlink() or not path.is_dir()
        )

    while max_site_size_bytes and site_size_bytes() > max_site_size_bytes:
        run_directories = sorted(
            (
                path for path in site_dir.iterdir()
                if path.is_dir() and re.fullmatch(r"run-[0-9]+", path.name)
            ),
            key=lambda path: int(path.name[4:]),
        )
        old_runs = [path for path in run_directories if path.resolve() != target]
        candidates = old_runs or ([target] if target.is_dir() else [])
        if not candidates:
            fail(
                f"Pages site exceeds max-site-size-bytes ({max_site_size_bytes}) "
                "after all report directories were removed"
            )
        expired = candidates[0]
        remove_path(expired)
        reports = [
            entry for entry in reports
            if safe_manifest_path(site_dir, entry["path"]) != expired.resolve()
        ]
        if expired.resolve() == target:
            source = None
        landing_page = site_dir / "index.html"
        if landing_page.is_file() and re.fullmatch(r"run-[0-9]+", expired.name):
            landing = landing_page.read_text(encoding="utf-8")
            landing = re.sub(
                rf'^.*href="\./{re.escape(expired.name)}/".*\n?',
                "",
                landing,
                flags=re.MULTILINE,
            )
            landing_page.write_text(landing, encoding="utf-8")
        write_report_indexes()

    output = env("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as out:
            out.write(f"report-path={target if source is not None else ''}\n")
            out.write(f"report-url-path={relative.as_posix() + '/' if source is not None else ''}\n")
            out.write(f"published={'true' if source is not None else 'false'}\n")
    if source is not None:
        print(f"Staged {report_type} report at {target}")
    else:
        print("No report artifact was staged; Pages site assembly completed.")


if __name__ == "__main__":
    main()
