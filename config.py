import os

# Load .env file (priority: .env < environment variables)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key not in os.environ:
                os.environ[key] = value

ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding")

DEFAULT_MODEL_MAP = {
    "opus-4.7": os.environ.get("ARK_REAL_MODEL", "glm-5.1"),
}

MODEL_MAP = DEFAULT_MODEL_MAP.copy()

LOCAL_PORT = int(os.environ.get("ARK_PROXY_PORT", "8000"))

THINKING_MODE = os.environ.get("ARK_THINKING_MODE", "auto")

THINKING_INFO = {
    "doubao-seed-2-0-code-preview-260215": False,
    "doubao-seed-2-0-pro-260215": True,
    "doubao-seed-2-0-lite-260215": True,
    "doubao-seed-2-0-lite-260428": True,
    "doubao-seed-2-0-mini-260215": False,
    "doubao-seed-2-0-mini-260428": False,
    "doubao-seed-code-preview-251028": False,
    "glm-5.1": True,
    "glm-4-7-251222": False,
    "glm-4-5-air-20250728": False,
    "minimax-m2-7": True,
    "minimax-m2-5": True,
    "kimi-k2-6": True,
    "kimi-k2-5": False,
    "deepseek-v3-2-251201": False,
    "qwen3-32b-20250429": False,
    "qwen3-14b-20250429": False,
    "qwen3-8b-20250429": False,
    "qwen3-0-6b-20250429": False,
    "qwen2-5-72b-20240919": False,
}

EXTRA_MODELS = [
    {"id": "glm-5.1", "name": "GLM-5.1", "domain": "LLM"},
    {"id": "minimax-m2-7", "name": "MiniMax-M2.7", "domain": "LLM"},
    {"id": "kimi-k2-6", "name": "Kimi-K2.6", "domain": "LLM"},
    {"id": "minimax-m2-5", "name": "MiniMax-M2.5", "domain": "LLM"},
    {"id": "kimi-k2-5", "name": "Kimi-K2.5", "domain": "LLM"},
]