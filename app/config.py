"""Shared runtime configuration for ML Harness clients."""

import os


DEFAULT_PORT = 8078
PORT = int(os.environ.get("MLH_PORT", str(DEFAULT_PORT)))

#: Loopback only, and not configurable. There is no deployment of this product
#: that wants a listener on a LAN interface: it is a local engine that holds a
#: provider API key and reads the user's data. A `MLH_HOST` environment
#: variable would exist mainly to be set to `0.0.0.0` by somebody debugging a
#: container at midnight, so there isn't one.
HOST = "127.0.0.1"

BASE_URL = f"http://{HOST}:{PORT}"
