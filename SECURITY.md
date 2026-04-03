# Security Policy

## Supported versions

The latest `main` branch is the supported release target.

## Reporting a vulnerability

Please do not open a public issue for sensitive vulnerabilities.

Instead:

1. Prepare a short reproduction with impact description.
2. Share the affected version or commit hash.
3. Send the report privately to the project maintainer.

## Hardening guidance

- Store secrets only in `.env` or your secret manager.
- Limit API, PostgreSQL, and MQTT exposure to trusted networks.
- Rotate Xplora credentials if access logs suggest misuse.

