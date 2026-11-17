# Test report publisher for GitHub Pages

This composite action assembles a caller-provided Pages site from the previously
published site, report and coverage artifacts. It maintains the recent-runs
landing page and size limit, stages static reports, and writes a `reports.html`
index. It does not deploy Pages; the caller should run one final deployment.

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
optional `max-reports` and `max-report-size-bytes` inputs enforce report-count and
per-report size limits. Set either to `0` to disable that limit.
`max-report-size-mb` is an optional MiB override; `0` uses the byte limit. The
action requires Bash and Python 3 on the runner.

Outputs are `report-path` and `report-url-path`. The action writes
`reports.html`, updates the root landing page, carries forward the existing
Pages directory, renders the browser-side coverage page, and prunes the oldest
`run-*` reports if the site exceeds `max-site-size-bytes`. The default total
site limit is 1,000,000,000 bytes. The default per-report limit is also
1,000,000,000 bytes. It creates a placeholder run page when no
report artifact is available. `max-site-size-bytes` can be set to `0` to disable
size-based pruning.

The `existing-site-directory` input defaults to `gh-pages-current`; check out
the current Pages branch there before calling the action to retain old reports
and statistics. The `coverage-directory` input defaults to
`downloaded-coverage` and should contain `coverage-summary.json` when coverage
is available.

## Permissions and deployment

The action only manipulates workspace files and does not request a token or
write to a branch. Grant `contents: write` only to the caller's deployment job.
Pin the action to a reviewed release tag or commit SHA.

## Local tests

```sh
python3 -m unittest discover -s test -v
```
