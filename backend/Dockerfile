# syntax=docker/dockerfile:1.7
# Needs the private ulai-api SDK as the named build context "ulai_sdk"
# (docker-compose.yml points it at ../ulai-cloud-python-sdk; override with ULAI_SDK_PATH).

FROM python:3.11-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
WORKDIR /src

COPY --from=ulai_sdk pyproject.toml README.md /sdk/
COPY --from=ulai_sdk ulai_api /sdk/ulai_api
RUN pip install /sdk

COPY pyproject.toml ./
COPY app ./app
RUN pip install .


FROM python:3.11-slim
RUN useradd --system --uid 10001 --home /app studio
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
USER studio
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# Migrations run on every start; they're no-ops when the schema is current.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
