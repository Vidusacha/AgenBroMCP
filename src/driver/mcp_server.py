"""MCP Server wrapper for AgenBroMCP BrowserDriver."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from .config import DriverConfig
from .protocol import ProtocolSessionPool, execute_action

mcp = MCPServer("AgenBroMCP")
_pool: Optional[ProtocolSessionPool] = None


def get_session_pool() -> ProtocolSessionPool:
    """Return or initialize the global MCP session pool."""
    global _pool
    if _pool is None:
        _pool = ProtocolSessionPool(default_config=DriverConfig.from_file())
    return _pool


def reset_session_pool(config: Optional[DriverConfig] = None) -> ProtocolSessionPool:
    """Close existing sessions and re-initialize pool (useful for testing)."""
    global _pool
    if _pool is not None:
        _pool.close_all()
    _pool = ProtocolSessionPool(default_config=config or DriverConfig.from_file())
    return _pool


@mcp.tool()
def browser_open(url: str, session: str = "default") -> Dict[str, Any]:
    """Open a URL in the browser, capture HTML/PNG/OCR artifacts, and return the page manifest."""
    return execute_action({"op": "open", "target": url, "session": session}, pool=get_session_pool())


@mcp.tool()
def browser_read(session: str = "default") -> Dict[str, Any]:
    """Read structured content from the current page (headings, text, links, images with OCR, actionables)."""
    return execute_action({"op": "read", "session": session}, pool=get_session_pool())


@mcp.tool()
def browser_fill(selector: str, value: str, session: str = "default") -> Dict[str, Any]:
    """Fill an input or textarea identified by selector or actionable ID (e.g. 'act_1')."""
    return execute_action(
        {"op": "fill", "target": selector, "value": value, "session": session},
        pool=get_session_pool(),
    )


@mcp.tool()
def browser_select(selector: str, option: str, session: str = "default") -> Dict[str, Any]:
    """Select an option in a <select> dropdown."""
    return execute_action(
        {"op": "select", "target": selector, "value": option, "session": session},
        pool=get_session_pool(),
    )


@mcp.tool()
def browser_check(selector: str, checked: bool = True, session: str = "default") -> Dict[str, Any]:
    """Check or uncheck a checkbox or radio input."""
    return execute_action(
        {"op": "check" if checked else "uncheck", "target": selector, "value": checked, "session": session},
        pool=get_session_pool(),
    )


@mcp.tool()
def browser_click(
    selector: str,
    session: str = "default",
    danger: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Click a button, link, or interactive element and record transition artifacts."""
    return execute_action(
        {
            "op": "click",
            "target": selector,
            "session": session,
            "danger": danger,
            "confirm": confirm,
        },
        pool=get_session_pool(),
    )


@mcp.tool()
def browser_press(
    key: str = "Enter",
    selector: Optional[str] = None,
    session: str = "default",
) -> Dict[str, Any]:
    """Press a keyboard key (e.g. 'Enter') optionally focused on a selector."""
    return execute_action(
        {"op": "press", "target": selector, "value": key, "session": session},
        pool=get_session_pool(),
    )


@mcp.tool()
def browser_close_session(session: str = "default") -> Dict[str, Any]:
    """Save session state and close the browser context for the given session."""
    pool = get_session_pool()
    if session in pool.drivers:
        pool.drivers[session].close()
        del pool.drivers[session]
    return {"ok": True, "session": session, "closed": True}


def main() -> None:
    """Run the AgenBroMCP server over stdio."""
    try:
        mcp.run(transport="stdio")
    finally:
        if _pool is not None:
            _pool.close_all()


if __name__ == "__main__":
    main()
