# Purpose: Build a production-ready container for Docker and Home Assistant add-on deployments.
# Inputs: Python source code, dependency manifests, runtime environment variables, and add-on options.
# Outputs: One image that can initialize the database and serve the FastAPI application in both modes.
# Invariants: The image must remain reproducible and never contain hard-coded credentials.
# Debugging: Rebuild with `docker compose build --no-cache app` when dependencies or base packages change.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Why this section exists:
# The service needs a small set of base packages for health checks, DNS, and TLS.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential curl tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod a+x /app/run.sh

EXPOSE 8000

CMD ["/app/run.sh"]
