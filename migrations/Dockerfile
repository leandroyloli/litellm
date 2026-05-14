ARG LITELLM_BUILD_IMAGE=cgr.dev/chainguard/wolfi-base@sha256:31da6565f35af6401031c1d7aa91dc84ac76c5c48edd17fb90f0ed9e3173c7a9
ARG LITELLM_RUNTIME_IMAGE=cgr.dev/chainguard/wolfi-base@sha256:31da6565f35af6401031c1d7aa91dc84ac76c5c48edd17fb90f0ed9e3173c7a9
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a

FROM $UV_IMAGE AS uvbin

# ---------- Builder ----------
#
# Minimal install for `prisma migrate deploy`. We deliberately skip the heavy
# `proxy-runtime` (otel, sentry, ddtrace, pypdf, google-genai, anthropic-vertex,
# ...) and `semantic-router` extras that the gateway/backend pull in — the
# migration engine doesn't need them. We DO install `--extra proxy` so the
# DB-URL helper from `litellm.proxy.auth.rds_iam_token` is importable, which
# is how the gateway and backend assemble `DATABASE_URL` at pod startup when
# `IAM_TOKEN_DB_AUTH=true` (see backend/main.py:17, gateway/main.py:22). And
# `--extra extra_proxy` provides the `prisma` CLI + the secret-manager
# backends `litellm.secret_managers.main` lazily imports.
#
# We also deliberately do NOT run `prisma generate` — the generated Python
# client is only required by the runtime proxy. `prisma migrate deploy` /
# `migrate diff` / `migrate resolve` / `db execute` only need the Prisma
# engine binaries, which we pre-fetch with `prisma py fetch` (no client code).
FROM $LITELLM_BUILD_IMAGE AS builder

WORKDIR /app
USER root

COPY --from=uvbin /uv /uvx /usr/local/bin/

RUN apk add --no-cache bash gcc python3 python3-dev openssl openssl-dev libsndfile

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:${PATH}"

# Stage 1 — install third-party deps only (cached by pyproject.toml/uv.lock).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=enterprise/pyproject.toml,target=enterprise/pyproject.toml \
    --mount=type=bind,source=litellm-proxy-extras/pyproject.toml,target=litellm-proxy-extras/pyproject.toml \
    uv sync --frozen --no-install-project --no-install-workspace --no-default-groups --no-editable \
        --extra proxy \
        --extra extra_proxy \
        --python python3

# Stage 2 — copy source and install the project + workspace members.
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-editable \
        --extra proxy \
        --extra extra_proxy \
        --python python3

COPY migrations/run.py /app/run.py

# Pre-fetch the Prisma binaries into ~/.cache/prisma-python so the Job pod
# doesn't reach the internet on first start. `prisma py fetch` downloads
# ONLY the engines — unlike `prisma generate`, it does not generate the
# Python client (we don't need it; the migration engine reads schema.prisma
# directly via the Node CLI).
RUN mkdir -p /home/nonroot && \
    HOME=/home/nonroot prisma py fetch && \
    chown -R nonroot:nonroot /home/nonroot/.cache

# ---------- Runtime ----------
FROM $LITELLM_RUNTIME_IMAGE AS runtime

USER root

RUN apk add --no-cache bash openssl tzdata python3 libsndfile

# wolfi-base ships an unprivileged `nonroot` account (UID/GID 65532). The
# Prisma engine binaries are dynamically linked against libssl/libcrypto, so
# openssl stays in the runtime layer.
WORKDIR /app
ENV HOME=/home/nonroot \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder --chown=nonroot:nonroot /app /app
COPY --from=builder --chown=nonroot:nonroot /home/nonroot/.cache /home/nonroot/.cache

USER nonroot

ENTRYPOINT ["python3", "/app/run.py"]
