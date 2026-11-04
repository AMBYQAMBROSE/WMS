from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRETS = {"change-me", "change-me-to-a-random-secret"}


class Settings(BaseSettings):
    app_env: str = "development"
    # Written by a build argument when release images are built (see deploy/build-release.sh); "dev" in development
    app_version: str = "dev"
    database_url: str = (
        "mssql+pyodbc://sa:YourPassword123!@localhost:1433/wms"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # 5173 is the web admin dev server, 19006 the Expo web preview of the PDA app; the native PDA app is not subject to CORS.
    # In production nginx serves the web app and proxies /api on the same origin, so no CORS is needed; set as a JSON array, e.g. ["http://a","http://b"]
    cors_allow_origins: list[str] = ["http://localhost:5173", "http://localhost:19006"]
    # API docs at /docs; usually kept on in customer intranets for troubleshooting, can be disabled for security reviews
    enable_api_docs: bool = True
    # Database connection pool (per backend process). Sync FastAPI endpoints run in a thread pool of about 40 concurrent requests per process,
    # so the pool must be at least that large, otherwise requests queue for a connection until they time out (seen in load tests)
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    # Reports split "a day" using this time zone (all timestamps in the database are UTC)
    business_timezone: str = "Asia/Shanghai"
    # Integration worker: poll interval (seconds), retention days for events/jobs/logs
    integration_poll_seconds: float = 2.0
    integration_retention_days: int = 90

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def check_production(self) -> None:
        """Refuse to start in production with the default secret: it is public, so anyone could forge login tokens"""
        if not self.is_production:
            return
        if self.jwt_secret_key in _DEFAULT_SECRETS or len(self.jwt_secret_key) < 32:
            raise RuntimeError("In production JWT_SECRET_KEY must be a random string of at least 32 characters (the install script generates one)")


settings = Settings()
