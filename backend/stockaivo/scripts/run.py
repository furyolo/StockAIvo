from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import uvicorn

from stockaivo.logging_config import build_logging_config, configure_logging

configure_logging()
LOG_CONFIG = build_logging_config()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_RELOAD_EXCLUDES = [
    "logs",
    "logs/*",
    "logs/**/*",
    "*.log",
    str((PROJECT_ROOT / "logs").resolve()),
]
RELOAD_DIRS = [
    str((PROJECT_ROOT / "stockaivo").resolve()),
    str((PROJECT_ROOT / "database_migrations").resolve()),
    str((PROJECT_ROOT / "tests").resolve()),
]


def dev():
    """Runs the development server with reload."""
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_config=LOG_CONFIG,
        reload_excludes=LOG_RELOAD_EXCLUDES,
        reload_dirs=RELOAD_DIRS,
    )

def start():
    """Runs the production server."""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3224,
        log_config=LOG_CONFIG
    )
