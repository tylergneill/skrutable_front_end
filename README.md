# Skrutable front end

Currently deployed at [skrutable.info](https://skrutable.info).

See documentation for [skrutable Python package](http://github.com/tylergneill/skrutable) for more info.

## Dockerfiles

- `Dockerfile`: Production image (port 5010, 4 workers/4 threads).
- `Dockerfile.stg`: Staging image (port 5011, 1 worker/4 threads) — full app, used for pre-release review.
- `Dockerfile.dev`: Dev image (port 5012, 1 worker) — full app, for local development builds.
- `Dockerfile.redirect`: Redirect-only image (port 5011) — runs `flask_redirect.py`, displays a "staging is offline" message and auto-redirects to prod after 15 s. Deploy this in place of staging when staging is shut down, so anyone hitting the staging URL lands on an informative page instead of an error.
- `flask_redirect.py`: Minimal Flask app used by `Dockerfile.redirect`. Catches all routes and renders `templates/redirect.html`. The prod URL is configured via the `PROD_URL` env var (default: `https://skrutable.info`).

Built and pushed via `build_and_push` from [kalpataru-grove](https://github.com/tylergneill/kalpataru-grove):

```bash
export APP_NAME=skrutable
export VERSION=X.Y.Z
build_and_push --stg          # staging → Dockerfile.stg
build_and_push --redirect     # redirect page → Dockerfile.redirect
```