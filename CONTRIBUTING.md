# Contributing to Azuregos

## Branching & merging

- Branch off `main` for every change (`feat/…`, `fix/…`, `ci/…`, `docs/…`).
- Open a PR into `main`. CI (lint, tests, smoke) must pass.
- PRs are **squash-merged**; the **PR title becomes the commit subject** on
  `main`, and the merged branch is deleted automatically.

## Conventional Commits

The **PR title must follow [Conventional Commits](https://www.conventionalcommits.org/)**,
because it becomes the squash commit that drives automated semantic versioning
on merge to `main`. A CI check (`PR Title`) enforces this.

```
<type>[optional scope][!]: <description>
```

**Types** and their effect on the next release version:

| Type | Example | Version bump |
|------|---------|--------------|
| `feat` | `feat: add saved filters to the ticket queue` | **minor** (x.**Y**.0) |
| `fix` | `fix: correct area-path validation for nested areas` | **patch** (x.y.**Z**) |
| `feat!` / `fix!` / any `!` | `feat!: require SSO for admin login` | **major** (**X**.0.0) |
| `docs`, `chore`, `ci`, `build`, `refactor`, `perf`, `test`, `style`, `revert` | `docs: document backup steps` | patch (default) |

A breaking change can also be signalled with a `BREAKING CHANGE:` footer in the
PR body.

### Guidelines
- Keep the subject imperative and lowercase, no trailing period
  (e.g. `fix: handle empty area path`, not `Fixed the bug.`).
- Use a scope when it helps: `feat(portals): …`, `fix(ci): …`.

## Releases

On merge to `main`, CI computes the next `vX.Y.Z` from the PR title, tags it,
creates a GitHub release, and builds/signs/attests the container images
(`latest`, `X.Y.Z`, `X.Y`, `sha-<short>`). See the README's **CI / releases**
section.
