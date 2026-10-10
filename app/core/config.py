from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CredNexa"
    app_version: str = "1.0.0.0"
    environment: Literal["development", "test", "production"] = "development"

    database_url: SecretStr

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "crednexa-api"
    jwt_audience: str = "crednexa-web"

    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    refresh_cookie_name: str = "crednexa_refresh"
    refresh_cookie_secure: bool | None = None
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None

    auth_rate_limit_window_seconds: int = 60
    login_rate_limit: int = 10
    register_rate_limit: int = 5
    otp_rate_limit: int = 5
    refresh_rate_limit: int = 20

    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_length: int = 6

    password_reset_token_expire_minutes: int = 10

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
        if secret.strip().lower() in {"secret", "changeme", "change-me", "password", "your-secret-key"}:
            raise ValueError("JWT_SECRET_KEY must not use a known placeholder")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_expiry(cls, value: int) -> int:
        if not 1 <= value <= 60:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 60")
        return value

    @field_validator("refresh_token_expire_days")
    @classmethod
    def validate_refresh_expiry(cls, value: int) -> int:
        if not 1 <= value <= 30:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 30")
        return value

    @field_validator(
        "auth_rate_limit_window_seconds",
        "login_rate_limit",
        "register_rate_limit",
        "otp_rate_limit",
        "refresh_rate_limit",
        "otp_max_attempts",
        "otp_length",
    )
    @classmethod
    def validate_positive_security_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Security limits must be positive integers")
        return value

    @property
    def trusted_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one trusted origin")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ALLOWED_ORIGINS must contain exact HTTP(S) origins without paths")
        return origins

    @model_validator(mode="after")
    def validate_cookie_settings(self) -> "Settings":
        _ = self.trusted_origins
        if self.refresh_cookie_samesite == "none" and self.refresh_cookie_secure is False:
            raise ValueError("SameSite=None refresh cookies require Secure")
        if self.environment == "production" and self.refresh_cookie_secure is False:
            raise ValueError("Refresh cookies must be Secure in production")
        if self.environment == "production" and self.cors_allowed_origins == "http://localhost:5173,http://127.0.0.1:5173":
            raise ValueError("Set CORS_ALLOWED_ORIGINS to the production frontend origins")
        if self.environment == "production" and any(urlsplit(origin).hostname in {"localhost", "127.0.0.1"} for origin in self.trusted_origins):
            raise ValueError("Localhost origins cannot be trusted in production")
        return self

    @property
    def use_secure_refresh_cookie(self) -> bool:
        return self.refresh_cookie_secure if self.refresh_cookie_secure is not None else self.environment == "production"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


settings = Settings()
