"""
conftest.py — Pre-import mocking for test infrastructure.

Mocks heavy/external dependencies (fastmcp, lakebase, WorkspaceClient)
so that frontend_gradio.py and movie_mcp_server.py can be imported in the
Databricks Serverless test environment without the full MCP server stack.
"""

import sys
import types
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Mock `fastmcp` before any test module tries to import it
# ---------------------------------------------------------------------------
_fastmcp_mock = types.ModuleType('fastmcp')

class _FastMCPMock:
    """Minimal stand-in for fastmcp.FastMCP"""
    def __init__(self, *args, **kwargs):
        self.name = args[0] if args else 'mock'

    def tool(self, *args, **kwargs):
        """Decorator that passes the function through unchanged."""
        if args and callable(args[0]):
            return args[0]
        def decorator(func):
            return func
        return decorator

    def run(self, *args, **kwargs):
        pass

    def get_tools(self):
        return {}

_fastmcp_mock.FastMCP = _FastMCPMock
sys.modules.setdefault('fastmcp', _fastmcp_mock)

# Also mock fastmcp submodules that may be imported
for _sub in ['fastmcp.settings', 'fastmcp.exceptions', 'fastmcp.server']:
    sys.modules.setdefault(_sub, types.ModuleType(_sub))

# ---------------------------------------------------------------------------
# 2. Mock `lakebase` (requires psycopg2 + Databricks secrets at import time)
# ---------------------------------------------------------------------------
_lakebase_mock = types.ModuleType('lakebase')

def _mock_run_query(*args, **kwargs):
    return []

def _mock_run_write(*args, **kwargs):
    return None

def _mock_get_connection(*args, **kwargs):
    return MagicMock()

_lakebase_mock.run_query = _mock_run_query
_lakebase_mock.run_write = _mock_run_write
_lakebase_mock.get_connection = _mock_get_connection
sys.modules.setdefault('lakebase', _lakebase_mock)

# ---------------------------------------------------------------------------
# 3. Mock `databricks.sdk.WorkspaceClient` so module-level `w = WorkspaceClient()`
#    doesn't attempt real authentication during test collection.
# ---------------------------------------------------------------------------
_mock_wc = MagicMock()
_mock_wc.config.host = 'https://test.databricks.com'
_mock_wc.config.authenticate.return_value = {'Authorization': 'Bearer test-token'}

patch('databricks.sdk.WorkspaceClient', return_value=_mock_wc).start()
