"""One-command runner for the Enterprise Financial Consolidation Web Portal."""

import os
import sys
import uvicorn
from fs_conso.config import config

def main():
    print("=" * 60)
    print("   ENTERPRISE FINANCIAL CONSOLIDATION PORTAL (Ind AS 110)")
    print("   Built on LangGraph & Google Gemini with 100% Formula Provenance")
    print("=" * 60)

    # Check active API Key
    has_key = config.validate_api_key_strict()
    if has_key:
        print("[OK] Google Gemini API Key: Active")
    else:
        print("[GATE NOTICE] GEMINI_API_KEY not found in environment.")
        print("             Execution will remain blocked until configured in Settings Drawer.")

    print(f"[OK] Workspace Root: {config.project_root}")
    print("[OK] Starting Web Portal at: http://127.0.0.1:8000")
    print("=" * 60)

    uvicorn.run("fs_conso.web.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()
