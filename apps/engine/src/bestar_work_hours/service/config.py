from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    service_secret: str
    environment: str = "production"
    max_upload_bytes: int = 3_000_000
    max_response_bytes: int = 4_000_000

    def validate(self):
        if len(self.service_secret) < 32:
            raise ValueError("API_SERVICE_SECRET must have at least 32 characters")
        if self.database_url.startswith("sqlite"):
            if self.environment not in {"development", "test"} or os.getenv("VERCEL"):
                raise ValueError("SQLite is permitted only for explicit local development/tests")
        elif not self.database_url.startswith(("postgresql", "postgres://")):
            raise ValueError("A PostgreSQL DATABASE_URL is required")
        return self

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            service_secret=os.getenv("API_SERVICE_SECRET", ""),
            environment=os.getenv("APP_ENV", "production"),
        ).validate()
