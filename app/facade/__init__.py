"""OpenCode's server protocol, spoken by this engine under `/oc`.

See `docs/PHASE-4-FACADE.md` for why the engine speaks their protocol rather
than their client being rewritten to speak ours, and `router.py` for the
routes. Their OpenAPI document, the contract every response here is tested
against, is `openapi.json` beside this file (upstream `ad1a4a6`, MIT).
"""

from app.facade.router import router

__all__ = ["router"]
