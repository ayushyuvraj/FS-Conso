"""Application configuration & security validation gate."""

import os
import re
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent

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

    def set_api_key_secure(self, new_key: str) -> None:
        """Sanitizes, validates, and synchronizes API key across config and environment."""
        if not new_key:
            self.gemini_api_key = ""
            os.environ.pop("GEMINI_API_KEY", None)
            return

        cleaned = new_key.strip()
        if any(c in cleaned for c in ["\r", "\n", "\0", "\t"]):
            raise ValueError("API Key contains illegal control or newline characters.")

        if not cleaned.startswith("AIzaSy") and not API_KEY_REGEX.match(cleaned):
            raise ValueError("Invalid Google Gemini API Key format. Must start with 'AIzaSy'.")

        self.gemini_api_key = cleaned
        os.environ["GEMINI_API_KEY"] = cleaned

    def validate_api_key_strict(self) -> bool:
        """Strict Execution Prerequisite: Halts application if an active key is missing/invalid."""
        key = (self.gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not key or key == "YOUR_GEMINI_API_KEY":
            return False
        if any(c in key for c in ["\r", "\n", "\0", "\t"]):
            return False
        return bool(API_KEY_REGEX.match(key)) or (key.startswith("AIzaSy") and len(key) >= 20)

    def require_active_api_key(self) -> None:
        """Raises a hard RuntimeError if API key is absent, blocking execution."""
        if not self.validate_api_key_strict():
            raise RuntimeError(
                "MANDATORY GATE VIOLATION: An active Google Gemini API key is required to run the consolidation engine. "
                "Please configure 'GEMINI_API_KEY' in your environment, .env file, or the Settings drawer."
            )

# Global singleton config
config = AppConfig()
