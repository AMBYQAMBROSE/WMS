FROM python:3.12-slim

# pyodbc 需要系统层的 msodbcsql18 驱动。这段按微软现行(非 apt-key，已废弃)的 Debian 12 安装方式写的，
# 但这台开发机没有 Docker，没能实际跑一次 build 验证，正式用之前请在有 Docker 的机器上先跑通一次。
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg2 unixodbc-dev ca-certificates \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list \
        | sed 's#\[arch=amd64,armhf,arm64\]#[arch=amd64,armhf,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg]#' \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
