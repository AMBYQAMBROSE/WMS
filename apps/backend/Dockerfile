# Same Python version as development (3.15: lazy annotation evaluation and other behavior differ from older versions; only ship what was tested).
# Pinned Debian release (trixie): Microsoft's ODBC driver repository is per release.

# ---- build dependencies: pyodbc has no prebuilt wheel for 3.15, so it needs a compiler and unixODBC headers ----
FROM python:3.15-slim-trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---- runtime image: no compiler ----
FROM python:3.15-slim-trixie

# Per current Microsoft docs: install packages-microsoft-prod.deb (repository and signing key for this release), then the ODBC 18 driver
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSL -o /tmp/packages-microsoft-prod.deb \
        "https://packages.microsoft.com/config/debian/$(. /etc/os-release && echo $VERSION_ID)/packages-microsoft-prod.deb" \
    && dpkg -i /tmp/packages-microsoft-prod.deb && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 TZ=Asia/Shanghai

WORKDIR /app
COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt && rm -rf /wheels
COPY . .

# Version last: changing only the version reuses all earlier layers from cache
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

RUN useradd --system --uid 10001 wms
USER wms

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1
# WEB_CONCURRENCY: number of processes, usually the CPU core count; endpoints are sync, each process also has a thread pool
# --timeout-graceful-shutdown: live event streams never end on their own; without it a stop waits for every browser to leave
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 5"]
