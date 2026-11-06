"""Server configuration; .env is local, ignored, and never served to browsers."""
from dataclasses import dataclass, field
import os
import re
from dotenv import load_dotenv


@dataclass(frozen=True)
class OpenAISettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    response_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"

    def __post_init__(self):
        for model in (self.response_model, self.embedding_model):
            if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,100}", model):
                raise ValueError("Invalid server model identifier")
        if len(self.api_key) > 1000 or any(c.isspace() for c in self.api_key):
            raise ValueError("Invalid API key configuration")

    @classmethod
    def from_env(cls):
        # Does not evaluate shell expressions and never overrides process env.
        load_dotenv(dotenv_path=".env", override=False)
        return cls(enabled=os.environ.get("DSS_OPENAI_ENABLED", "false").lower() == "true",
                   api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                   response_model=os.environ.get("OPENAI_RESPONSE_MODEL", "gpt-4.1-mini"),
                   embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
