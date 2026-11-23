"""Application configuration & security validation gate."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AppConfig(BaseModel):
    """Configuration for consolidation engine and web application."""
    project_root: Path = PROJECT_ROOT
    inputs_dir: Path = PROJECT_ROOT / "inputs"
    outputs_dir: Path = PROJECT_ROOT / "outputs"
    rules_dir: Path = PROJECT_ROOT / "rules"
    
    # AI settings
    gemini_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    gemini_model: str = "gemini-2.5-flash"
    ai_confidence_threshold: float = 0.85  # Dynamic threshold (0.0 to 1.0)
    
    # Intercompany settings
    ic_absolute_tolerance: float = 10000.0  # e.g., ₹10,000 / $100
    ic_percent_tolerance: float = 0.01      # 1%
    
    # Reporting period
    current_period: str = "31-Mar-2024"
    reporting_currency: str = "INR"

    def validate_api_key_strict(self) -> bool:
        """Strict Execution Prerequisite:

        Halts application if an active Google Gemini API key is not present.
        """
        key = self.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        if not key or not key.strip() or key.strip() == "YOUR_GEMINI_API_KEY":
            return False
        return True

    def require_active_api_key(self) -> None:
        """Raises a hard RuntimeError if API key is absent, blocking execution."""
        if not self.validate_api_key_strict():
            raise RuntimeError(
                "MANDATORY GATE VIOLATION: An active Google Gemini API key is required to run the consolidation engine. "
                "Please configure 'GEMINI_API_KEY' in your environment, .env file, or the Settings drawer."
            )

# Global singleton config
config = AppConfig()
