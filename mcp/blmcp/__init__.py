# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
MCP server for Blender.

Provides tools for LLM's, connecting to Blender via a bridge-server.
All tools send code to the add-on to run.
"""

__all__ = (
    "create_server",
    "main",
)

import argparse
import importlib
import os
import pkgutil

import yaml
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module

from blmcp.agent_ops import _registry
from blmcp.profiles import PROFILE_NAMES, agent_modules, official_modules, pack_modules
from blmcp.settings import configure
from blmcp.state import reset_runtime
from blmcp.metrics import record_schema_tax

# NOTE(@ideasman42): this was written to support LLAMA-C++'s Web UI,
# which is one of the nicer ways to run this locally.
# It is not full HTTP support because there looks to be many options for this protocol.
# This could be disabled if it no longer serves its purpose - as most agents wont use STDIO.
_USE_HTTP_SUPPORT = True

_TRANSPORTS = ("stdio", *(("http",) if _USE_HTTP_SUPPORT else ()))

_AGENT_INSTRUCTIONS = """\
Prefer structured Blender tools over generated Python. Query only state needed for
the next decision. Use a screenshot when visual verification matters. Search API
or manual docs before guessing unsupported APIs. Use execute_blender_code only
when no structured operation can perform the task. After visually sensitive or
uncertain changes, verify before continuing.\
"""


def _tool_module_names() -> tuple[str, ...]:
    """Find upstream tools without registering their implementation modules."""
    import blmcp.tools as tools_pkg

    names: list[str] = []
    for _importer, modname, _ispkg in pkgutil.iter_modules(tools_pkg.__path__):
        if modname.endswith("_toolcode") or modname.startswith("_template_"):
            continue
        names.append(modname)
    return tuple(names)


def create_server(profile: str = "core", unsafe_python: bool = False, enable_unrestricted: bool = False) -> FastMCP:
    """Build a fixed-profile MCP server, primarily for the entry point and tests."""
    if profile not in PROFILE_NAMES:
        raise ValueError("Unknown profile {!r}".format(profile))
    configure(unsafe_python=unsafe_python, agent_mode=profile != "official", unrestricted=enable_unrestricted)
    reset_runtime()
    _registry.reset_registry()

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    with open(os.path.join(data_dir, "prompts.yml"), encoding="utf-8") as fh:
        prompts = yaml.safe_load(fh)
    instructions = str(prompts["initial_instructions"]) if profile == "official" else _AGENT_INSTRUCTIONS
    mcp = FastMCP("blender-mcp" if profile == "official" else "super-blender-mcp-next", instructions=instructions)

    for modname in official_modules(profile, _tool_module_names()):
        mod = importlib.import_module("blmcp.tools.{:s}".format(modname))
        if hasattr(mod, "register"):
            mod.register(mcp)
    for modname in agent_modules(profile):
        mod = importlib.import_module("blmcp.agent_ops.{:s}".format(modname))
        mod.register(mcp)
    for modname in pack_modules(profile):
        mod = importlib.import_module("blmcp.providers.{:s}".format(modname))
        mod.register(mcp)
    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP server for Blender.")
    parser.add_argument(
        "--transport", "-t",
        choices=_TRANSPORTS,
        default="stdio",
        help="Transport protocol (default: stdio).",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default=os.environ.get("BLMCP_PROFILE", "core"),
        help="Fixed tool profile at startup (default: core).",
    )
    parser.add_argument(
        "--unsafe-python",
        action="store_true",
        default=os.environ.get("BLMCP_UNSAFE_PYTHON") == "1",
        help="Disable AST validation for execute_blender_code. Use only in a trusted local session.",
    )
    parser.add_argument(
        "--enable-unrestricted",
        action="store_true",
        default=os.environ.get("BLMCP_ENABLE_UNRESTRICTED") == "1",
        help="Register execute_blender_code_unrestricted (no safety policy). Only for trusted developer sessions.",
    )
    if _USE_HTTP_SUPPORT:
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host to bind to for HTTP transports (default: 127.0.0.1).",
        )
        parser.add_argument(
            "--port", "-p",
            type=int,
            default=8000,
            help="Port to bind to for HTTP transports (default: 8000).",
        )
    args = parser.parse_args()

    mcp = create_server(profile=args.profile, unsafe_python=args.unsafe_python, enable_unrestricted=args.enable_unrestricted)
    record_schema_tax(mcp, args.profile)

    transport = args.transport
    if _USE_HTTP_SUPPORT and transport == "http":
        # pylint: disable-next=import-error,no-name-in-module
        from mcp.server.fastmcp.server import TransportSecuritySettings  # type: ignore[attr-defined]
        from starlette.applications import Starlette
        from starlette.middleware.cors import CORSMiddleware

        transport = "streamable-http"

        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = "/"
        mcp.settings.stateless_http = True
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )

        # Add CORS middleware so browser-based clients
        # (e.g. llama.cpp web UI) can connect without preflight failures.
        _orig = mcp.streamable_http_app

        def _app_with_cors() -> Starlette:
            app = _orig()
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
            return app

        mcp.streamable_http_app = _app_with_cors  # type: ignore[method-assign]

    mcp.run(transport=transport)
    return 0
