import os
from typing import List

from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("PORT", "3001"))
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

        self.CORS_ORIGINS: List[str] = []
        self.CORS_ALLOW_ORIGIN_REGEX: str = ""
        if self.ENVIRONMENT == "production":
            origins = os.getenv("CORS_ORIGINS", "")
            self.CORS_ORIGINS = [item.strip() for item in origins.split(",") if item.strip()]
        else:
            self.CORS_ALLOW_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$"

        self.OLLAMA_API_BASE: str = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
        self.DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_API_BASE: str = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
        self.KIMI_API_KEY: str = os.getenv("KIMI_API_KEY", "")
        self.KIMI_API_BASE: str = os.getenv("KIMI_API_BASE", "https://api.moonshot.cn/v1").rstrip("/")
        self.KIMI_MODELS: str = os.getenv("KIMI_MODELS", "")

        self.ENTROFLOW_CLI_COMMAND: str = os.getenv("ENTROFLOW_CLI_COMMAND", "entroflow").strip()
        self.ENTROFLOW_CLI_TIMEOUT: int = int(os.getenv("ENTROFLOW_CLI_TIMEOUT", "120"))

        self.SYSTEM_PROMPT: str = os.getenv(
            "SYSTEM_PROMPT",
            "You are Robomix, a concise assistant that can chat, reason with tools, and control EntroFlow devices.",
        ).strip()
        self.DEVELOPER_PROMPT: str = os.getenv("DEVELOPER_PROMPT", "").strip()
        self.DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "deepseek-v4-flash").strip()

        self.CONTEXT_MAX_USER_TURNS: int = int(os.getenv("CONTEXT_MAX_USER_TURNS", "8"))
        self.CONTEXT_BUDGET_RATIO: float = float(os.getenv("CONTEXT_BUDGET_RATIO", "0.75"))
        self.CONTEXT_TOKEN_BUDGET: int = int(os.getenv("CONTEXT_TOKEN_BUDGET", "0"))
        self.CONTEXT_TOOL_RESULT_MAX_CHARS: int = int(os.getenv("CONTEXT_TOOL_RESULT_MAX_CHARS", "2000"))
        self.DEEPSEEK_CONTEXT_WINDOW: int = int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", "128000"))
        self.KIMI_CONTEXT_WINDOW: int = int(os.getenv("KIMI_CONTEXT_WINDOW", "256000"))
        self.OLLAMA_CONTEXT_WINDOW: int = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "32768"))


settings = Settings()
