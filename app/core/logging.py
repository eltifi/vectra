"""
@file logging.py
@brief Centralized logging configuration
@details
Configures application logging with support for file and stdout output.
Safely handles log directory creation.

@author Vectra Project
@date 2025-12-15
@version 1.0
@license AGPL-3.0
"""

import logging
import sys
import os

def setup_logging() -> logging.Logger:
    """
    @brief Configure and return the root logger
    @details
    Sets up logging based on LOG_OUTPUT env var:
    - 'file': Write to logs/app.log
    - 'stdout': Write to console
    - 'both': Write to both (default)
    """
    # Determine log directory
    LOG_DIR = os.getenv("LOG_DIR", None)
    if LOG_DIR is None:
         # Try /app/logs first (production), fall back to local logs/ (development)
        try:
            _app_logs = "/app/logs"
            if not os.path.exists(_app_logs):
                # Only try to create if we think we might have permissions or it's empty
                # In many container setups /app might be read-only but logs volume mounted
                if os.access(os.path.dirname(_app_logs), os.W_OK):
                     os.makedirs(_app_logs, exist_ok=True)
            
            if os.path.exists(_app_logs) and os.access(_app_logs, os.W_OK):
                LOG_DIR = _app_logs
        except (OSError, PermissionError):
            pass

    if LOG_DIR is None:
        # Fall back to local logs directory relative to this file
        # this file is in app/core/, so back 2 levels is app root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        LOG_DIR = os.path.join(base_dir, "logs")
        if not os.path.exists(LOG_DIR):
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
            except (OSError, PermissionError):
                # If we can't create logs dir, fallback to just stdout
                LOG_DIR = None

    LOG_OUTPUT = os.getenv("LOG_OUTPUT", "both").lower()
    
    handlers = []
    
    # Stdout handler
    if LOG_OUTPUT in ("stdout", "both"):
        handlers.append(logging.StreamHandler(sys.stdout))
        
    # File handler
    if LOG_OUTPUT in ("file", "both") and LOG_DIR:
        try:
            handlers.append(logging.FileHandler(f"{LOG_DIR}/app.log"))
        except (OSError, PermissionError):
            # If file logging fails, ensure we at least have stdout
            if not any(isinstance(h, logging.StreamHandler) for h in handlers):
                handlers.append(logging.StreamHandler(sys.stdout))

    # Safety net
    if not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers
    )
    
    return logging.getLogger("vectra")
