# Contributing

1. Find your section in [docs/sections](docs/sections/README.md). Only edit the paths your section owns; for anything else, open a PR and request that owner's review.
2. Branch from `main` using `feat/<short-name>`, `fix/<short-name>` or `docs/<short-name>` (e.g. `feat/firms-connector`).
3. One focused change per PR. Keep PRs small, and explain any large generated changes.
4. No direct pushes to `main`. Every PR needs at least one approving review.
5. Changes to `contracts/**` or `apps/worker/config/providers.yaml` need the `contract-change` label and the lead's review.
6. Don't mix formatting rewrites with feature work.
7. Never commit secrets. Use `.env` (ignored) and `.env.example` (committed, empty values).

A PR is ready to merge when it meets the definition of done in the PR template.
