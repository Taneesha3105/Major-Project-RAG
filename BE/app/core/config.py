"""Application configuration loaded from environment variables / `.env`."""

from functools import cached_property
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "DealLens M&A Due Diligence"
    app_version: str = "1.0.0"
    app_env: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- Security ----------------------------------------------------------
    jwt_secret_key: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=480, ge=5)
    default_signup_role: str = "analyst"
    admin_email: str = "admin@deallens.local"
    admin_password: str = "Admin@12345"
    admin_full_name: str = "Platform Administrator"

    # --- Database ----------------------------------------------------------
    postgres_db: str = "mna_diligence"
    postgres_user: str = "mna_app"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    db_echo: bool = False
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)

    # --- File storage ------------------------------------------------------
    storage_dir: str = "storage/uploads"
    max_upload_mb: int = Field(default=50, ge=1)

    # --- Document processing -----------------------------------------------
    chunk_size: int = Field(default=1200, ge=200)
    chunk_overlap: int = Field(default=200, ge=0)
    ocr_enabled: bool = True
    ocr_engine: str = "rapidocr"  # rapidocr | gemini
    ocr_min_chars_per_page: int = Field(default=40, ge=0)
    ocr_render_scale: float = Field(default=2.0, gt=0.5, le=4.0)
    ingestion_concurrency: int = Field(default=1, ge=1, le=4)
    auto_summarize_documents: bool = True

    # --- Embeddings (open source, local) ------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "

    # --- Retrieval ---------------------------------------------------------
    retrieval_vector_k: int = Field(default=30, ge=1)
    retrieval_lexical_k: int = Field(default=30, ge=1)
    retrieval_rrf_k: int = Field(default=60, ge=1)
    retrieval_rerank_candidates: int = Field(default=24, ge=1)
    retrieval_final_k: int = Field(default=6, ge=1, le=20)
    reranker_enabled: bool = True
    reranker_model: str = "ms-marco-MiniLM-L-12-v2"
    model_cache_dir: str = ".cache/models"

    # --- LLM (Gemini) ------------------------------------------------------
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_analysis_model: str = ""
    gemini_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    gemini_max_output_tokens: int = Field(default=2048, ge=128)
    chat_history_turns: int = Field(default=6, ge=0)

    @field_validator("ocr_engine", "default_signup_role", mode="before")
    @classmethod
    def lowercase(cls, value: str) -> str:
        return str(value).strip().lower()

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password or None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def analysis_model(self) -> str:
        return self.gemini_analysis_model or self.gemini_chat_model

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @cached_property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        return path if path.is_absolute() else BASE_DIR / path

    @cached_property
    def model_cache_path(self) -> Path:
        path = Path(self.model_cache_dir)
        return path if path.is_absolute() else BASE_DIR / path


settings = Settings()
