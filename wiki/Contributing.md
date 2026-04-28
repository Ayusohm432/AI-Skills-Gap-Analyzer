# Contributing

Thank you for your interest in contributing to the AI Skill Gap Analyzer!

---

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally.
3. Follow the [Getting Started](Getting-Started.md) guide to set up the dev environment.
4. Create a new branch for your feature or bug fix (see branching convention below).

---

## Branching Convention

| Branch pattern | Purpose |
|----------------|---------|
| `main` | Stable, production-ready code |
| `feature/<short-description>` | New features |
| `fix/<short-description>` | Bug fixes |
| `chore/<short-description>` | Maintenance, dependency updates, docs |
| `refactor/<short-description>` | Code refactoring without behavior change |

Example:
```bash
git checkout -b feature/github-profile-enrichment
```

---

## Development Workflow

```
fork → clone → branch → code → test → lint → commit → push → Pull Request
```

### Backend

```bash
cd backend
source venv/bin/activate

# Run tests
python -m pytest tests/ -v

# Lint (if configured)
flake8 . --max-line-length=120
```

### Frontend

```bash
cd frontend

# Lint
npm run lint

# Build (catch type / import errors)
npm run build
```

---

## Commit Message Style

Use concise, imperative-mood messages:

```
feat: add GitHub profile skill enrichment
fix: handle empty PDF text extraction gracefully
chore: upgrade pydantic to v2
docs: update API reference for /predict-role
```

---

## Pull Request Guidelines

1. Keep PRs focused — one feature or fix per PR.
2. Update or add tests for any changed behavior.
3. Update the relevant wiki page(s) if the change affects user-facing behavior or configuration.
4. Ensure `pytest` passes with no new failures.
5. Fill in the PR description: **what** changed and **why**.

---

## Reporting Bugs

Open a [GitHub Issue](https://github.com/Ayusohm432/AI-Skills-Gap-Analyzer/issues) with:

- A clear title.
- Steps to reproduce.
- Expected vs actual behavior.
- Relevant log output (redact any secrets).

---

## Requesting Features

Open a GitHub Issue with the **enhancement** label. Describe:

- The problem you are trying to solve.
- Your proposed solution.
- Any alternatives you considered.

---

## Code Style

### Python
- Follow [PEP 8](https://peps.python.org/pep-0008/) (max line length 120).
- Use type annotations for all function signatures.
- Async functions must be `async def`; avoid blocking I/O inside async routes.

### JavaScript / React
- Follow the ESLint config in `frontend/eslint.config.js`.
- Use functional components with hooks.
- Keep components small and focused.

---

## Project Structure Quick Reference

See [Architecture](Architecture.md) for a full folder-structure breakdown.

---

## License

This project is released under the terms described in the repository's `LICENSE` file.
