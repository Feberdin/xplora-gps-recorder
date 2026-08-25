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

## Public Xplora application-client constants

The two application-client constants in `app/xplora_client.py` and the packaged
add-on copy are not an individual user's account credentials. They are identical
to the constants published by the MIT-licensed `Ludy87/pyxplora_api` project in
upstream commit `3689e9778255701b74be8eef8c86b24975c1c841` and remain public in
that project's current source.

Gitleaks therefore contains exact fingerprint exceptions for those four known
findings. The exception intentionally does not allow the files, paths, rule, or
an arbitrary value pattern. New or moved credential-like values must still fail
the scan and receive an explicit security review.

These shared application credentials are still operationally sensitive: abuse
could consume vendor quotas or cause the shared client identity to be revoked.
Never confuse them with, log, or commit an Xplora username, password, session
token, refresh token, watch identifier, or location data.
