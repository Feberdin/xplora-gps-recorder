# Contributing

Thanks for improving `xplora-gps-recorder`.

## Development setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

## Expected workflow

1. Create a focused branch.
2. Make small, reviewable changes.
3. Run tests and lint before opening a pull request.
4. Update the README or examples if operator behavior changes.

## Quality checks

```bash
ruff check .
pytest
```

## Coding guidelines

- Prefer readability over cleverness.
- Keep modules small and responsibilities clear.
- Add comments that explain why a block exists, especially around API normalization and analytics logic.
- Fail fast with actionable error messages.

## Pull request checklist

- Tests cover the new behavior.
- Existing behavior stays backward-compatible unless documented.
- Configuration and migration changes are reflected in the docs.
- No secrets were added to the repository.

