# SPDX-License-Identifier: GPL-3.0-or-later
"""Process-local runtime settings configured before tools are registered."""

from __future__ import annotations

__all__ = ('agent_mode_enabled', 'configure', 'unrestricted_enabled', 'unsafe_python_enabled')

import os

_unsafe_python = os.environ.get("BLMCP_UNSAFE_PYTHON") == "1"
_unrestricted = os.environ.get("BLMCP_ENABLE_UNRESTRICTED") == "1"
_agent_mode = True


def configure(*, unsafe_python: bool, agent_mode: bool, unrestricted: bool = False) -> None:
    global _unsafe_python, _agent_mode, _unrestricted
    _unsafe_python = unsafe_python
    _agent_mode = agent_mode
    _unrestricted = unrestricted


def unsafe_python_enabled() -> bool:
    return _unsafe_python


def agent_mode_enabled() -> bool:
    return _agent_mode


def unrestricted_enabled() -> bool:
    """Whether ``execute_blender_code_unrestricted`` was enabled at startup."""
    return _unrestricted
