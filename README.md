# Test report publisher for GitHub Pages

This composite action stages a static report directory into a caller-provided
Pages site and writes a small `reports.html` index. It does not deploy the site:
the caller should assemble all content and run a single Pages deployment.

## Usage

```yaml
- name: Download Playwright report
  uses: actions/download-artifact@v4
  with:
    name: playwright-report
    path: downloaded-report

- name: Stage report
  id: report
  uses: raczeja/test-report-gh-pages-action@v1
  with:
    report-directory: downloaded-report
    site-directory: site
    report-type: Playwright
    destination: run-${{ github.run_number }}
    run-number: ${{ github.run_number }}
```

The initial contract is intentionally format-neutral: any static HTML report
directory with a top-level `index.html` can be staged. For future Allure support,
generate the Allure static site before calling the action, then pass that output
directory and set `report-type: Allure`. No Playwright-specific parsing or
report generation is performed here.

The destination must be a safe relative path. The source must not contain
symbolic links. Existing reports at the same destination are replaced. The
optional `max-reports` and `max-report-size-mb` inputs enforce report-count and
per-report size limits; `0` disables each limit. The action requires Python 3
on the runner.

Outputs are `report-path` and `report-url-path`. The action writes
`reports.html`; callers with an existing landing page can link to that page or
use the staged report path directly.

## Permissions and deployment

The action only manipulates workspace files and does not request a token or
write to a branch. Grant `contents: write` only to the caller's deployment job.
Pin the action to a reviewed release tag or commit SHA.

## Local tests

```sh
python3 -m unittest discover -s test -v
```
