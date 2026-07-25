# sanad-api — slim, non-root, uv-locked. Built by ci.yml; scanned (Trivy) + SBOM + cosign.
FROM ghcr.io/astral-sh/uv:0.7-python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

FROM python:3.12-slim-bookworm
# Bookworm (not trixie) so the runtime glibc matches the uv builder stage above; apply the
# distro's available security updates so Trivy's fixable-CVE gate has nothing to report.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -r sanad && useradd -r -g sanad sanad
WORKDIR /app
COPY --from=build --chown=sanad:sanad /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER sanad
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c \
    "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["uvicorn", "sanad_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
