from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Certificate Automation"
    api_prefix: str = "/api/v1"
    jwt_secret: str = ""
    bootstrap_admin_password: str = ""
    pfx_password: str = ""
    access_token_minutes: int = 720
    database_path: str = "./certificate_automation.db"
    artifacts_directory: str = "./artifacts"

    digicert_mode: str = "real"
    digicert_api_base: str = "https://www.digicert.com/services/v2"
    digicert_timeout_seconds: int = 60
    digicert_max_retries: int = 3
    digicert_retry_backoff_seconds: float = 1.0
    digicert_poll_seconds: int = 3
    digicert_poll_attempts: int = 20
    digicert_server_platform_id: int = 2
    digicert_default_product_name_id: str = "ssl_plus"
    # Set this to an existing, validated CertCentral organization ID before ordering.
    digicert_default_organization_id: int = 0
    digicert_default_validity_days: int = 199

    issuance_check_enabled: bool = True
    issuance_check_interval_seconds: int = 60
    issuance_check_tick_seconds: int = 10
    issuance_check_max_failures: int = 5
    issuance_check_max_backoff_seconds: int = 3600

    iis_dry_run: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def digicert_api_key(self) -> str:
        """Read the DigiCert key only from this backend directory’s .env file."""
        env_path = Path(__file__).resolve().parents[2] / ".env"
        return (dotenv_values(env_path, interpolate=False).get("DIGICERT_API_KEY") or "").strip()

    @property
    def database_url(self) -> str:
        absolute_path = Path(self.database_path).resolve()
        return f"sqlite:///{absolute_path}"


settings = Settings()
Path(settings.artifacts_directory).mkdir(parents=True, exist_ok=True)
