from pydantic import Field, field_validator, model_validator
from sqlalchemy.engine import URL
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="RAG Chatbot Backend")
    app_version: str = Field(default="0.1.0")
    app_env: str = Field(default="development")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    api_v1_prefix: str = Field(default="/api/v1")

    postgres_db: str = Field(default="rag_chatbot")
    postgres_user: str = Field(default="rag_user")
    postgres_password: str = Field(default="rag_password")
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    db_echo: bool = Field(default=False)
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_recycle_seconds: int = Field(default=300, ge=0)
    vector_size: int = Field(default=384, ge=1)
    db_init_max_retries: int = Field(default=10)
    db_init_retry_delay: float = Field(default=2.0)
    chunk_size: int = Field(default=1000, ge=100)
    chunk_overlap: int = Field(default=200, ge=0)
    embedding_batch_size: int = Field(default=20, ge=1)
    default_text_filename: str = Field(default="text-input.txt")
    embedding_provider: str = Field(default="mock")
    provider_timeout_seconds: float = Field(default=30.0, gt=0)
    local_embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    local_embedding_device: str = Field(default="cpu")
    local_embedding_runtime: str = Field(default="sentence_transformers")
    local_embedding_batch_size: int = Field(default=64, ge=1)
    local_embedding_encode_batch_size: int = Field(default=32, ge=1)
    local_embedding_warmup_enabled: bool = Field(default=True)
    local_embedding_warmup_mode: str = Field(default="blocking")
    local_embedding_warmup_text: str = Field(default="Warm up the local embedding model.")
    local_embedding_onnx_model_dir: str = Field(default="")
    local_embedding_onnx_intra_op_threads: int = Field(default=0, ge=0)
    local_embedding_onnx_inter_op_threads: int = Field(default=0, ge=0)
    chat_max_output_tokens: int = Field(default=300, ge=1)
    chat_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-4.1-mini")
    gemini_api_key: str = Field(default="")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    gemini_embedding_model: str = Field(default="gemini-embedding-001")
    gemini_chat_model: str = Field(default="gemini-2.5-flash")
    groq_api_key: str = Field(default="")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")
    groq_chat_model: str = Field(default="llama-3.1-8b-instant")
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_chat_model: str = Field(default="openrouter/free")
    retrieval_top_k_default: int = Field(default=3, ge=1)
    retrieval_top_k_max: int = Field(default=10, ge=1)
    retrieval_mode: str = Field(default="exact")
    retrieval_candidate_k: int = Field(default=40, ge=1)
    retrieval_similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    chat_provider: str = Field(default="mock")
    chat_top_k_default: int = Field(default=3, ge=1)
    chat_top_k_max: int = Field(default=10, ge=1)
    chat_retrieval_fetch_k: int = Field(default=10, ge=1)
    chat_context_max_chars: int = Field(default=2400, ge=1)
    chat_context_max_chunks: int = Field(default=3, ge=1)
    chat_context_per_chunk_max_chars: int = Field(default=900, ge=1)
    chat_lexical_rescue_enabled: bool = Field(default=True)
    chat_lexical_rescue_k: int = Field(default=5, ge=0)
    chat_min_top_similarity_score: float = Field(default=0.45, ge=0.0, le=1.0)
    chat_high_confidence_top_similarity_score: float = Field(default=0.75, ge=0.0, le=1.0)
    chat_min_average_similarity_score: float = Field(default=0.4, ge=0.0, le=1.0)
    chat_average_similarity_top_n: int = Field(default=3, ge=1)
    chat_query_spelling_cutoff: float = Field(default=0.88, ge=0.0, le=1.0)
    chat_rrf_k: int = Field(default=60, ge=1)
    chat_summary_min_rrf_score: float = Field(default=0.03, ge=0.0, le=1.0)
    chat_summary_min_margin_rrf_score: float = Field(default=0.005, ge=0.0, le=1.0)
    chat_stream_chunk_words: int = Field(default=8, ge=1)
    chat_stream_delay_ms: int = Field(default=75, ge=0)
    chat_rerank_strategy_default: str = Field(default="hybrid")
    flashrank_enabled: bool = Field(default=True)
    flashrank_warmup_enabled: bool = Field(default=False)
    flashrank_model: str = Field(default="ms-marco-TinyBERT-L-2-v2")
    flashrank_neural_top_n: int = Field(default=15, ge=1)
    flashrank_hybrid_top_n: int = Field(default=10, ge=1)
    chat_no_context_response: str = Field(
        default=(
            "I don't have enough information to answer that right now."
        )
    )
    chat_clarification_response: str = Field(
        default="Could you say a bit more about what you want to know?"
    )
    chat_system_prompt: str = Field(
        default=(
            "You are a helpful assistant for a document-grounded RAG chatbot. "
            "Answer the user naturally using only the retrieved excerpts when possible. "
            "Do not mention internal retrieval mechanics, filenames, chunk numbers, source labels, "
            "section names, chapter names, or phrases like 'based on the provided context' in the answer. "
            "Do not add commentary about where the answer appears in the document. "
            "Do not tell the user to look at this document, a section, a chapter, or a page. "
            "Do not say things like 'in this document', 'see Section 5.3', or 'as described in Chapter 4'. "
            "For direct factual questions, give the answer and stop. "
            "For short factual answers drawn from tables, charts, or benefit rows, rewrite the answer as a complete "
            "natural sentence that uses the user's wording where possible. "
            "Do not start those answers with bare dollar amounts, numbers, or labels like 'From network providers:'. "
            "If the excerpts provide multiple directly relevant values for the same benefit, such as in-network and "
            "out-of-network amounts, include each of those values in the answer. "
            "Do not volunteer extra caveats, hypothetical missing factors, or speculation beyond the user's question. "
            "Do not add side notes about related details unless the user asked for them. "
            "If the excerpts are insufficient, reply exactly with: "
            "\"I don't have enough information to answer that right now.\" "
            "Do not mention excerpts, context, documents, or prior knowledge in that reply."
        )
    )
    cors_allowed_origins: str = Field(default="http://localhost:3000")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @field_validator("embedding_provider", mode="before")
    @classmethod
    def normalize_embedding_provider_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {
            "sentence-transformers": "local",
            "sentence_transformers": "local",
            "local_semantic": "local",
        }
        return aliases.get(normalized, normalized)

    @field_validator("local_embedding_runtime", mode="before")
    @classmethod
    def normalize_local_embedding_runtime(cls, value: str) -> str:
        normalized = value.strip().lower()
        aliases = {
            "sentence-transformers": "sentence_transformers",
            "torch": "sentence_transformers",
        }
        return aliases.get(normalized, normalized)

    @field_validator("local_embedding_warmup_mode", mode="before")
    @classmethod
    def normalize_local_embedding_warmup_mode(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("chat_provider", mode="before")
    @classmethod
    def normalize_chat_provider_name(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("chat_rerank_strategy_default", mode="before")
    @classmethod
    def normalize_chat_rerank_strategy_default(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("retrieval_mode", mode="before")
    @classmethod
    def normalize_retrieval_mode(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if self.retrieval_top_k_default > self.retrieval_top_k_max:
            raise ValueError("RETRIEVAL_TOP_K_DEFAULT must be smaller than or equal to RETRIEVAL_TOP_K_MAX.")
        if self.retrieval_candidate_k < self.retrieval_top_k_max:
            raise ValueError("RETRIEVAL_CANDIDATE_K must be greater than or equal to RETRIEVAL_TOP_K_MAX.")
        if self.chat_top_k_default > self.chat_top_k_max:
            raise ValueError("CHAT_TOP_K_DEFAULT must be smaller than or equal to CHAT_TOP_K_MAX.")
        allowed_log_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if self.log_level.upper() not in allowed_log_levels:
            raise ValueError("LOG_LEVEL must be one of: CRITICAL, ERROR, WARNING, INFO, DEBUG.")
        if not self.api_v1_prefix.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'.")
        allowed_embedding_providers = {"mock", "local_hash", "local", "sentence_transformers", "openai", "gemini"}
        if self.embedding_provider not in allowed_embedding_providers:
            raise ValueError(
                "EMBEDDING_PROVIDER must be one of: mock, local_hash, local, sentence_transformers, openai, gemini."
            )
        allowed_local_embedding_runtimes = {"sentence_transformers", "onnx"}
        if self.local_embedding_runtime not in allowed_local_embedding_runtimes:
            raise ValueError("LOCAL_EMBEDDING_RUNTIME must be one of: sentence_transformers, onnx.")
        allowed_local_embedding_warmup_modes = {"blocking", "background"}
        if self.local_embedding_warmup_mode not in allowed_local_embedding_warmup_modes:
            raise ValueError("LOCAL_EMBEDDING_WARMUP_MODE must be one of: blocking, background.")
        allowed_chat_providers = {"mock", "openai", "gemini", "groq", "openrouter"}
        if self.chat_provider not in allowed_chat_providers:
            raise ValueError("CHAT_PROVIDER must be one of: mock, openai, gemini, groq, openrouter.")
        allowed_rerank_strategies = {"fast", "hybrid", "neural"}
        if self.chat_rerank_strategy_default not in allowed_rerank_strategies:
            raise ValueError("CHAT_RERANK_STRATEGY_DEFAULT must be one of: fast, hybrid, neural.")
        allowed_retrieval_modes = {"exact", "ann_rerank"}
        if self.retrieval_mode not in allowed_retrieval_modes:
            raise ValueError("RETRIEVAL_MODE must be one of: exact, ann_rerank.")
        if self.flashrank_hybrid_top_n > self.flashrank_neural_top_n:
            raise ValueError("FLASHRANK_HYBRID_TOP_N must be smaller than or equal to FLASHRANK_NEURAL_TOP_N.")
        uses_openai = self.embedding_provider == "openai" or self.chat_provider == "openai"
        uses_gemini = self.embedding_provider == "gemini" or self.chat_provider == "gemini"
        uses_groq = self.chat_provider == "groq"
        uses_openrouter = self.chat_provider == "openrouter"
        if uses_openai and not self.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER or CHAT_PROVIDER is openai.")
        if uses_gemini and not self.gemini_api_key.strip():
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER or CHAT_PROVIDER is gemini.")
        if uses_groq and not self.groq_api_key.strip():
            raise ValueError("GROQ_API_KEY is required when CHAT_PROVIDER is groq.")
        if uses_openrouter and not self.openrouter_api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required when CHAT_PROVIDER is openrouter.")
        return self


settings = Settings()
