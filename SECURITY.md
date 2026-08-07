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

- Store Xplora account and API client credentials only in `.env`, the masked Home
  Assistant app fields, or your secret manager.
- Limit API, PostgreSQL, and MQTT exposure to trusted networks.
- Rotate credentials if they were committed or access logs suggest misuse. Removing a
  value from the current tree does not remove it from Git history.
