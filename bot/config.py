from dataclasses import dataclass
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    token: str = ""
    internal_token: str = ""
    api_url: str = "http://127.0.0.1:8000/api/bot"
    redis_url: str = ""
    environment: str = "development"
    default_locale: str = "ru"
    templates_directory: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            token=os.getenv("BOT_TOKEN", ""),
            internal_token=os.getenv("BOT_INTERNAL_TOKEN", ""),
            api_url=os.getenv("BOT_API_URL", "http://127.0.0.1:8000/api/bot"),
            redis_url=os.getenv("REDIS_URL", ""),
            environment=os.getenv("APP_ENV", "development"),
            default_locale=os.getenv("BOT_DEFAULT_LOCALE", "ru"),
            templates_directory=os.getenv("BOT_TEMPLATES_DIRECTORY", ""),
        )

    def validate(self) -> None:
        if len(self.internal_token) < 32:
            raise ValueError("BOT_INTERNAL_TOKEN must contain at least 32 characters when BOT_TOKEN is set")
        if self.environment not in {"development", "demo", "test", "production"}:
            raise ValueError("APP_ENV must be development, demo, test or production")
        if self.environment == "production" and not self.redis_url:
            raise ValueError("REDIS_URL is required in production")
        if self.default_locale not in {"ru", "uk"}:
            raise ValueError("BOT_DEFAULT_LOCALE must be ru or uk")
        parsed = urlparse(self.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            raise ValueError("BOT_API_URL must be an HTTP(S) URL without credentials")
        if self.environment == "production" and parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "backend", "api"}:
            raise ValueError("Use HTTPS for a remote production backend")
