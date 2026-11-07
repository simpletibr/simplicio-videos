"""HTTP for the swap adapters and the openverse client: standard library only (urllib).

The client lives in `simplicio_video.rede` (`request`, `Response`, `NetworkError`, `NoRedirect`); this name stays for the swap adapters
(`from . import http`) and for the tests that replace `swap_providers.http.request`. It is not a copy and not a list of re-exported
names: importing it makes `swap_providers.http` BE the module `rede` (the same object), so replacing `request` here replaces it for every
caller of `rede.request`, Openverse included, exactly as it did when both used this file. The one name this file had and `rede` does
not (`_NoRedirect`, the old private name of `rede.NoRedirect`) is added to `rede` here, because a test still reads it.
"""
from __future__ import annotations

import sys

from .. import rede

rede._NoRedirect = rede.NoRedirect  # the old private name; tests/test_openverse.py still reads `http._NoRedirect`
sys.modules[__name__] = rede
