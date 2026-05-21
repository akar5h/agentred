# Coding standards

We optimise for readability and small diffs over cleverness. New code
should look like the surrounding code unless there is a written reason to
diverge.

## Python

- Format with `ruff format`, lint with `ruff check`. Both are pre-commit.
- Type annotations on public functions; `from __future__ import annotations`
  in every new module.
- Prefer `dataclasses` for plain data, Pydantic only when validation crosses
  a system boundary (HTTP request, queue payload).
- Tests in `tests/<module-path>/test_*.py`, mirroring the source tree.

## Reviews

- PRs under 400 lines unless you have flagged the size in advance
- One reviewer for typo/copy changes, two for anything touching auth,
  billing, or data migrations
- Squash on merge; the squash message becomes the changelog entry
