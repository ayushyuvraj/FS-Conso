"""Application configuration & security validation gate."""

import os
import re
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment from .env file if present (project root or user home directory)
ENV_PATH = PROJECT_ROOT / ".env"
HOME_ENV_PATH = Path.home() / ".env"

def _load_env_file(path: Path) -> None:
    """Loads key-value pairs from .env into os.environ with zero third-party dependencies."""
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

def _save_env_var(path: Path, key_name: str, value_to_set: str) -> None:
    """Updates, adds, or clears a variable in .env file with zero external dependencies."""
    try:
        lines = []
        found = False
        if path.exists():
            content = path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith(f"{key_name}=") or stripped.startswith(f"export {key_name}="):
                    if value_to_set:
                        lines.append(f"{key_name}='{value_to_set}'")
                    found = True
                else:
                    lines.append(line)
        if not found and value_to_set:
            lines.append(f"{key_name}='{value_to_set}'")

        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except Exception:
        pass

# Attempt loading from .env
if ENV_PATH.exists():
    _load_env_file(ENV_PATH)
elif HOME_ENV_PATH.exists():
    _load_env_file(HOME_ENV_PATH)

try:
    import dotenv
    dotenv.load_dotenv(dotenv_path=ENV_PATH, override=False)
except ImportError:
    pass

# Standard Google API Key pattern (starts with AIzaSy)
API_KEY_REGEX = re.compile(r"^AIzaSy[A-Za-z0-9_-]{15,50}$")


class AppConfig(BaseModel):
    """Hardened configuration for consolidation engine and web application."""
    project_root: Path = PROJECT_ROOT
    inputs_dir: Path = PROJECT_ROOT / "inputs"
    outputs_dir: Path = PROJECT_ROOT / "outputs"
    rules_dir: Path = PROJECT_ROOT / "rules"
    
    # AI settings - repr=False prevents credential dump in logs/repr
    gemini_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""),
        repr=False
    )
    gemini_model: str = "gemini-2.5-flash"
    ai_confidence_threshold: float = 0.85  # Dynamic threshold (0.0 to 1.0)
    
    # Intercompany settings
    ic_absolute_tolerance: float = 10000.0  # e.g., ₹10,000 / $100
    ic_percent_tolerance: float = 0.01      # 1%
    
    # Reporting period
    current_period: str = "31-Mar-2024"
    reporting_currency: str = "INR"

    def get_masked_api_key(self) -> str:
        """Returns safely masked representation of the API Key (e.g. AIzaSy...****)."""
        key = (self.gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not key or key == "YOUR_GEMINI_API_KEY":
            return "[NOT CONFIGURED]"
        if len(key) <= 10:
            return "********"
        return f"{key[:6]}...{key[-4:]}"

    def set_api_key_secure(self, new_key: str, persist_to_env: bool = True) -> None:
        """Sanitizes, validates, and synchronizes API key across config, environment, and .env file."""
        if not new_key:
            self.gemini_api_key = ""
            os.environ.pop("GEMINI_API_KEY", None)
            if persist_to_env and ENV_PATH.exists():
                _save_env_var(ENV_PATH, "GEMINI_API_KEY", "")
            return

        cleaned = new_key.strip()
        if any(c in cleaned for c in ["\r", "\n", "\0", "\t"]):
            raise ValueError("API Key contains illegal control or newline characters.")

        if not API_KEY_REGEX.match(cleaned):
            raise ValueError("Invalid Google Gemini API Key format. Must match standard pattern 'AIzaSy...'.")

        self.gemini_api_key = cleaned
        os.environ["GEMINI_API_KEY"] = cleaned

        if persist_to_env:
            _save_env_var(ENV_PATH, "GEMINI_API_KEY", cleaned)

    def validate_api_key_strict(self) -> bool:
        """Strict Execution Prerequisite: Halts application if an active key is missing/invalid."""
        if self.gemini_api_key is not None:
            key = self.gemini_api_key.strip()
        else:
            key = os.getenv("GEMINI_API_KEY", "").strip()

        if not key or key == "YOUR_GEMINI_API_KEY":
            return False
        if any(c in key for c in ["\r", "\n", "\0", "\t"]):
            return False
        return bool(API_KEY_REGEX.match(key))

    def require_active_api_key(self) -> None:
        """Raises a hard RuntimeError if API key is absent, blocking execution."""
        if not self.validate_api_key_strict():
            raise RuntimeError(
                "MANDATORY GATE VIOLATION: An active Google Gemini API key is required to run the consolidation engine. "
                "Please configure 'GEMINI_API_KEY' in your environment, .env file, or the Settings drawer."
            )

# Global singleton config
config = AppConfig()
