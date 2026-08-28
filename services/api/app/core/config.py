"""Application configuration via environment variables (pydantic-settings).

Secrets are NEVER hard-coded. Everything is read from the environment (or a
local `.env` file, which is git-ignored). Sensible development defaults keep the
zero-config SQLite path working out of the box for the hackathon demo, while
production values are supplied via the environment.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identity / environment -------------------------------------------
    app_name: str = "LEGALMET AI"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # --- Database ----------------------------------------------------------
    # SQLite default keeps dev + tests zero-config; production overrides with
    # a PostgreSQL URL (postgresql+psycopg2://...).
    database_url: str = "sqlite:///./legalmet.db"

    # --- Security ----------------------------------------------------------
    secret_key: str = "dev-only-insecure-change-me"
    access_token_expire_minutes: int = 480
    jwt_algorithm: str = "HS256"

    # --- CORS (comma-separated) -------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Storage -----------------------------------------------------------
    storage_backend: str = "local"
    storage_dir: str = "./storage"
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_image_mime_types: str = "image/jpeg,image/png,image/webp"

    # --- Image intake (Prompt 3) ------------------------------------------
    # Real physical-package image ingestion limits, kept distinct from the
    # generic base64 `max_upload_bytes` above so the multipart intake path can
    # be tuned independently. Read from the environment (upper-snake names).
    max_image_size: int = 15 * 1024 * 1024
    max_batch_files: int = 20
    min_image_width: int = 400
    min_image_height: int = 400
    processed_max_dimension: int = 2000

    # --- Real perception (Prompt 4) ----------------------------------------
    # OCR backend behind the perception pipeline. "paddle" runs the real local
    # PaddleOCR engine; "mock" falls back to the seeded demo stub (dev only —
    # clearly-labelled, never used for real-image analysis).
    perception_ocr_backend: str = "paddle"
    # Comma-separated PaddleOCR language codes. Only configured languages are
    # claimed. Available script models include: en, devanagari (Hindi/Marathi),
    # tamil, telugu — see docs/ocr.md.
    perception_ocr_langs: str = "en"
    # Hard ceiling for one OCR inference call (seconds).
    perception_ocr_timeout_seconds: float = 180.0
    # Candidate confidence below this marks a field REVIEW_REQUIRED.
    perception_field_review_threshold: float = 0.6
    # OCR derivative conditioning (see PillowOcrPreprocessor).
    perception_ocr_min_long_edge: int = 1000
    perception_ocr_max_long_edge: int = 2400

    # --- Demo seeding (DEMO ONLY) -----------------------------------------
    seed_demo_data: bool = True
    demo_admin_email: str = "admin@legalmet.local"
    demo_admin_password: str = "changeme-admin"
    demo_inspector_email: str = "inspector@legalmet.local"
    demo_inspector_password: str = "changeme-inspector"

    # --- Regulatory intelligence seed (Prompt 5) ---------------------------
    # Idempotent seed of the researched Legal Metrology dataset at startup.
    # Distinct from seed_demo_data: this is real (research-grade, UNVERIFIED)
    # content with full provenance — not fiction. Set False to manage the
    # regulatory layer purely via import/API.
    seed_regulatory_data: bool = True

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # --- Derived helpers ---------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_image_mime_list(self) -> list[str]:
        return [m.strip() for m in self.allowed_image_mime_types.split(",") if m.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def using_insecure_secret(self) -> bool:
        return self.secret_key == "dev-only-insecure-change-me"

    @property
    def perception_ocr_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.perception_ocr_langs.split(",") if lang.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Use `get_settings.cache_clear()` in tests."""
    return Settings()
