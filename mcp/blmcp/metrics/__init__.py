# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional local-only context-cost instrumentation."""

from .context import record_schema_tax, record_tool_call

__all__ = ("record_schema_tax", "record_tool_call")
