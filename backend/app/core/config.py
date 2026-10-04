from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/ → backend/app/ → backend/ → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    TEST_DATABASE_URL: str = ""

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_HOURS: int = 12

    # Gemini / ADK
    GEMINI_API_KEY: str = ""
    GOOGLE_GENAI_USE_VERTEXAI: bool = False
    GEMINI_MODEL_FAST: str = ""
    GEMINI_MODEL_SMART: str = ""
    MAX_LLM_CALLS_PER_STAGE: int = 8

    # Knowledge
    KNOWLEDGE_AGEING_DAYS: int = 90
    KNOWLEDGE_STALE_DAYS: int = 180
    KNOWLEDGE_TOP_K: int = 5

    # Vertex AI Search
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    VERTEX_SEARCH_LOCATION: str = "global"
    VERTEX_SEARCH_DATA_STORE_ID: str = ""

    # Docs MCP server
    DOCS_SERVICE_ACCOUNT_EMAIL: str = ""
    DOCS_SHARE_WITH: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
