"""Open the dashboard in a browser, handing it the engine token once.

The engine's API is authenticated, and a browser cannot attach an
`Authorization` header to a URL you type. Rendering the token into the page
would defeat the point - `GET /` needs no credential, so anything embedded
there is readable by any local process, including the one the token exists to
keep away from `POST /jobs`.

So the token travels exactly once, in the query string of a single navigation.
The page moves it into `sessionStorage` and strips it from the URL before
anything else runs. A later unauthenticated fetch of `/` discloses nothing.

Run the engine first:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8078
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import security


def main() -> int:
    published = security.read_portfile()
    if not published:
        print(f"no engine.json at {security.ENGINE_FILE}", file=sys.stderr)
        print("start the engine first:", file=sys.stderr)
        print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8078",
              file=sys.stderr)
        return 1

    url = f"{published['base_url']}/?{urlencode({'token': published['token']})}"
    print(f"opening {published['base_url']}/ (token passed once, then stripped)")
    webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
