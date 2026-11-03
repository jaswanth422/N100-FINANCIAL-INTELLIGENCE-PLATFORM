# Security Policy

## Supported versions

This project is pre-1.0. Only the `main` branch receives security fixes.

| Version | Supported |
|---------|-----------|
| `main`  | yes       |
| others  | no        |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Email a description of the issue and reproduction steps to:

- **katurijaswanth422@gmail.com**

Include:

- A clear description of the vulnerability
- Steps to reproduce (minimal PoC where possible)
- Impact assessment (data exposure, RCE, auth bypass, injection, etc.)
- Suggested remediation if you have one

You should receive an acknowledgement within **5 business days**. Confirmed
reports typically receive a patch within **30 days** and credit in the
release notes (unless you prefer to remain anonymous).

## Scope

In-scope:

- All code under `src/` (ETL, analytics, screener, NLP, dashboard, API, reports)
- The GitHub Actions workflow in `.github/workflows/`
- The SQLite schema in `db/`
- The test harness

Out-of-scope:

- Vulnerabilities in third-party dependencies (report upstream — we track
  these via Dependabot)
- Issues that require physical access to a developer's machine
- Attacks against the bundled Excel source data

## Hardening practices

- Dependencies are updated weekly by Dependabot (`pip` + `github-actions`).
- No secrets are committed. `.gitignore` covers `.env*`, `*.pem`, `*.key`,
  `secrets.json`, `credentials.json`, `service-account*.json`.
- CI runs `ruff` + `pytest` with coverage on every push and PR
  (`.github/workflows/ci.yml`).
- The project-local `.claude/settings.json` adds preflight hooks that
  refuse agent-driven writes to secret-shaped file paths.
