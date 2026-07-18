"""Shared pytest fixtures and import path setup.

The ingest scripts import their siblings with bare module names (e.g.
``from health_api_client import HealthApiClient``) because they run as
standalone scripts, not as a package. Add each source directory to
``sys.path`` so the tests can import the modules the same way.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

for _sub in ("ingest", "scripts", "sqlmesh_project"):
    _path = str(_ROOT / _sub)
    if _path not in sys.path:
        sys.path.insert(0, _path)
