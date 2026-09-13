# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-local identity and revision state for agent operations."""

from .runtime import AgentRuntime, get_runtime, reset_runtime

__all__ = ("AgentRuntime", "get_runtime", "reset_runtime")
