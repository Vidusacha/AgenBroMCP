"""AgenBroMCP Browser Driver package."""

from .config import DriverConfig, configure_tesseract, get_repo_root
from .protocol import ProtocolSessionPool, execute_action, execute_stream
from .safety import ActionLimitError, SafetyError
from .session import BrowserDriver

__all__ = [
    "ActionLimitError",
    "BrowserDriver",
    "DriverConfig",
    "ProtocolSessionPool",
    "SafetyError",
    "configure_tesseract",
    "execute_action",
    "execute_stream",
    "get_repo_root",
]
