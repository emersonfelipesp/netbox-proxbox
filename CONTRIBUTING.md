# Contributing to Proxbox

Thanks for helping improve `netbox-proxbox`. This page is shown inside the plugin UI at `/plugins/proxbox/contributing/`, so it is kept practical and up to date with the current codebase and CI workflows.

## Where to get help

- Open a discussion in the repository discussions area for questions and design ideas.
- Use issues for actionable bugs and feature requests.
- For bug reports, include:
  - NetBox version
  - plugin version
  - exact reproduction steps
  - traceback/log snippets
  - expected vs actual behavior

## Development workflow (current)

1. Create or confirm an issue before coding.
2. Branch from the active development branch.
3. Make focused changes with tests.
4. Run local checks before pushing.
5. Open a PR referencing the issue (`Closes #<id>` when appropriate).

## Local checks to run before push

```bash
# netbox-proxbox
python -m compileall netbox_proxbox tests
rtk ruff check .
rtk pytest tests/
```

If your change touches `proxbox-api`, run that repo's checks as well.

## CI and automation (current state)

The project currently uses GitHub Actions for:

- `CI` (linting, formatting checks, compile/import checks, and tests)
- `docs` (build/deploy docs)
- Docker image workflows and release validation workflows
- scheduled schema refresh tooling

Before requesting review, make sure your branch is green in CI and that any failing check is either fixed or explicitly explained in the PR.

## Pull request expectations

- Keep PRs scoped to one feature or fix.
- Add/update tests for behavior changes.
- Prefer simple, incremental changes over large refactors.
- Update docs when user-visible behavior changes.

## Support the maintainer

If Proxbox helps your team, consider supporting continued development:

- GitHub Sponsors: [emersonfelipesp](https://github.com/sponsors/emersonfelipesp)
