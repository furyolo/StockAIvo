from dotenv import load_dotenv

load_dotenv()

import uvicorn
from uvicorn.config import LOGGING_CONFIG

# Define a custom log config dictionary
LOG_CONFIG = LOGGING_CONFIG
LOG_CONFIG["formatters"]["default"]["fmt"] = "[%(asctime)s] %(levelname)s - %(message)s"
LOG_CONFIG["formatters"]["default"]["datefmt"] = "%H:%M:%S"
LOG_CONFIG["formatters"]["access"]["fmt"] = '[%(asctime)s] %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
LOG_CONFIG["formatters"]["access"]["datefmt"] = "%H:%M:%S"

# Configure the root logger to capture all application logs and apply the default formatter
LOG_CONFIG["loggers"][""] = {
    "handlers": ["default"], 
    "level": "INFO"
}
# Ensure uvicorn's own loggers are also set correctly
LOG_CONFIG["loggers"]["uvicorn"]["handlers"] = ["default"]
LOG_CONFIG["loggers"]["uvicorn.error"]["level"] = "INFO"
LOG_CONFIG["loggers"]["uvicorn.access"] = {
    "handlers": ["access"], 
    "level": "INFO", 
    "propagate": False
}


def dev():
    """Runs the development server with reload."""
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_config=LOG_CONFIG
    )

def start():
    """Runs the production server."""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3227,
        log_config=LOG_CONFIG
    )