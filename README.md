# Test report publisher for GitHub Pages

This composite action assembles a caller-provided Pages site from the previously
published site, report and coverage artifacts. It maintains the recent-runs
landing page and size limit, stages static reports, and writes a `reports.html`
index. It does not deploy Pages; the caller should run one final deployment.
The published site contains static files only; Git metadata and commit history
are removed.

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
`run-*` reports until the site fits `max-site-size-bytes`, keeping the newest
reports that fit. A report larger than its per-report limit is not published.
The default total site limit is 1,000,000,000 bytes. The default per-report
limit is also 1,000,000,000 bytes. It creates a placeholder run page when no
report artifact is available. `max-site-size-bytes` can be set to `0` to disable
size-based pruning.

The `existing-site-directory` input defaults to `gh-pages-current`; check out
the current Pages branch there before calling the action to retain old reports
and statistics. The `coverage-directory` input defaults to
`downloaded-coverage` and should contain `coverage-summary.json` when coverage
is available.

## Enable GitHub Pages and deploy from `gh-pages`

1. Create an initially empty `gh-pages` branch. For example, from a temporary
   directory (replace `OWNER/REPO` with your repository):

   ```sh
   mkdir gh-pages-init
   cd gh-pages-init
   git init -b gh-pages
   touch .nojekyll
   git add .nojekyll
   git -c user.name="GitHub Actions" \
       -c user.email="github-actions[bot]@users.noreply.github.com" \
       commit -m "Initialize Pages branch"
   git remote add origin https://github.com/OWNER/REPO.git
   git push -u origin gh-pages
   ```

   Authenticate with your normal GitHub Git credentials (for example, GitHub
   CLI); do not put a token in the repository.
2. In your repository, open **Settings → Pages**. Under **Build and
   deployment**, choose **Deploy from a branch**, then select `gh-pages` and
   `/(root)`.
3. Add a publishing job to the workflow that generates and uploads the
   `playwright-report` artifact. The example below assumes that job is named
   `test` and uses the artifact name shown:

   ```yaml
   jobs:
     publish:
       needs: test
       runs-on: ubuntu-latest
       permissions:
         contents: write
       steps:
         - name: Check out the current Pages site
           uses: actions/checkout@v4
           with:
             ref: gh-pages
             path: gh-pages-current
             fetch-depth: 1

         - name: Download the report
           uses: actions/download-artifact@v4
           with:
             name: playwright-report
             path: downloaded-report

         - name: Assemble the Pages site
           uses: raczeja/test-report-gh-pages-action@v1
           with:
             report-directory: downloaded-report
             existing-site-directory: gh-pages-current
             site-directory: site
             destination: run-${{ github.run_number }}
             run-number: ${{ github.run_number }}

         - name: Publish to gh-pages
           run: |
             git -C gh-pages-current switch --orphan pages-publish
             find gh-pages-current -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
             cp -a site/. gh-pages-current/
             git -C gh-pages-current add --all
             git -C gh-pages-current \
               -c user.name="github-actions[bot]" \
               -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
               commit -m "Publish test reports"
             git -C gh-pages-current push --force origin HEAD:gh-pages
   ```

   `contents: write` lets the workflow's checkout credentials push the site;
   no API key or personal access token is needed. The orphan commit replaces
   the branch's prior commit history while preserving the previous static site
   files long enough for the action to retain reports within the size limit.

## Permissions and deployment

The action only manipulates workspace files and does not request a token or
write to a branch. Grant `contents: write` only to the caller's deployment job.
Pin the action and other workflow actions to reviewed release tags or commit
SHAs.

## Local tests

```sh
python3 -m unittest discover -s test -v
```
