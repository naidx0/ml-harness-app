from __future__ import annotations

import html


GLASS_CSS = r"""
:root{
  --base:#0e0f13;
  --veil-1:rgba(255,255,255,.045); --veil-2:rgba(255,255,255,.07);
  --veil-3:rgba(255,255,255,.03);
  --edge:rgba(255,255,255,.09); --edge-2:rgba(255,255,255,.14);
  --ink:#f2f3f7; --ink-2:#b8bdcb; --ink-3:#7d8496;
  --accent:#8b7cf6; --accent-2:#c4b5fd; --accent-wash:rgba(139,124,246,.14);
  --fits:#5fd3a0; --spills:#f0b45f; --wont:#f47c7c; --unknown:#7d8496; --info:#6fb5e8;
  --r-xs:6px; --r-sm:8px; --r:14px; --r-lg:20px; --r-pill:999px;
  --s1:4px; --s2:8px; --s3:12px; --s4:18px; --s5:26px; --s6:40px;
  --blur:22px;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;
  --mono:ui-monospace,"Cascadia Mono","SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box;}
/* The washes belong to the viewport, not the text column. They used to sit on
   body, which is capped at 920px, so the lit ground stopped at the column edge
   and left a hard vertical seam against the flat html background. Every
   computed-style check passed - the three gradients really were applied - and
   only a screenshot showed the seam. */
html{
  color-scheme:dark;
  min-height:100%;
  background:
    radial-gradient(circle at 14% 8%,rgba(139,124,246,.18),transparent 34%),
    radial-gradient(circle at 88% 22%,rgba(111,181,232,.12),transparent 31%),
    radial-gradient(circle at 52% 92%,rgba(95,211,160,.08),transparent 38%),
    var(--base);
  background-attachment:fixed;
}
body{
  min-height:100vh;
  max-width:920px;
  margin:0 auto;
  padding:var(--s6) var(--s5);
  background:transparent;
  color:var(--ink-2);
  font-family:var(--sans);
  font-size:16px;
  line-height:1.65;
}
h1,h2,h3,h4,h5,h6{
  color:var(--ink);
  font-family:var(--sans);
  line-height:1.18;
  letter-spacing:-.025em;
}
h1{margin:0 0 var(--s5);font-size:clamp(2rem,6vw,3.5rem);}
h2{margin:var(--s6) 0 var(--s3);font-size:1.45rem;}
p{margin:0 0 var(--s4);}
.mono,code,pre{font-family:var(--mono);}
pre{
  overflow:auto;
  padding:var(--s4);
  border:1px solid var(--edge);
  border-radius:var(--r-sm);
  background:var(--veil-3);
  color:var(--ink-2);
}
code{border-radius:var(--r-xs);}
.glass{
  padding:var(--s5);
  border:1px solid var(--edge);
  border-radius:var(--r);
  background:var(--veil-1);
  backdrop-filter:blur(var(--blur));
  box-shadow:0 1px 0 var(--edge-2) inset, 0 18px 44px rgba(0,0,0,.34);
}
.vpill{
  display:inline-flex;
  align-items:center;
  padding:var(--s1) var(--s3);
  border:1px solid var(--edge-2);
  border-radius:var(--r-pill);
  background:var(--veil-2);
  color:var(--ink);
  font-family:var(--mono);
  font-size:.78rem;
  font-weight:700;
  letter-spacing:.08em;
}
.vpill.fits{border-color:color-mix(in srgb,var(--fits) 48%,transparent);background:color-mix(in srgb,var(--fits) 14%,transparent);color:var(--fits);}
.vpill.spills{border-color:color-mix(in srgb,var(--spills) 48%,transparent);background:color-mix(in srgb,var(--spills) 14%,transparent);color:var(--spills);}
.vpill.wont{border-color:color-mix(in srgb,var(--wont) 48%,transparent);background:color-mix(in srgb,var(--wont) 14%,transparent);color:var(--wont);}
/* UNKNOWN is grey, not amber. Amber would rank it as a bad answer; it is not an
   answer at all. docs/DESIGN_SYSTEM.md section 2.4. */
.vpill.unknown{border-color:color-mix(in srgb,var(--unknown) 48%,transparent);background:color-mix(in srgb,var(--unknown) 14%,transparent);color:var(--unknown);}
.budget{
  display:flex;
  width:100%;
  height:14px;
  overflow:hidden;
  border:1px solid var(--edge);
  border-radius:var(--r-pill);
  background:var(--veil-3);
}
.budget .seg{display:block;min-width:0;border-radius:var(--r-pill);}
.budget .weights{background:var(--accent);}
.budget .activations{background:var(--info);}
.budget .headroom{background:var(--veil-2);}
.chip{
  display:inline-flex;
  padding:var(--s1) var(--s2);
  border:1px solid var(--edge);
  border-radius:var(--r-pill);
  background:var(--veil-3);
  color:var(--ink-2);
  font-family:var(--mono);
  font-size:.78rem;
}
.chip.accent{border-color:var(--accent);background:var(--accent-wash);color:var(--accent-2);}
.dim{color:var(--ink-3);}
.sr-only{
  position:absolute;
  width:1px;
  height:1px;
  padding:0;
  margin:-1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
  border:0;
}
.composer{
  display:flex;
  align-items:center;
  gap:var(--s2);
  padding:var(--s2);
  border:1px solid var(--edge-2);
  border-radius:var(--r-pill);
  background:var(--veil-1);
  backdrop-filter:blur(var(--blur));
  box-shadow:0 1px 0 var(--edge-2) inset, 0 18px 44px rgba(0,0,0,.34);
}
.composer input{
  min-width:0;
  flex:1;
  padding:var(--s3) var(--s4);
  border:0;
  outline:0;
  background:transparent;
  color:var(--ink);
  font:inherit;
}
.composer input::placeholder{color:var(--ink-3);}
.composer .go{
  display:grid;
  width:44px;
  height:44px;
  flex:0 0 44px;
  place-items:center;
  border:0;
  border-radius:50%;
  background:var(--accent);
  color:var(--ink);
  cursor:pointer;
  font-size:1.25rem;
}
.intake-guidance{margin-bottom:var(--s5);}
.intake-helpers{margin:var(--s4) 0 0;padding-left:var(--s5);font-size:.9rem;}
.plan-summary{margin-bottom:var(--s6);}
.plan-summary .summary{margin:var(--s3) 0;color:var(--ink);font-weight:700;}
.budget-scale{display:flex;justify-content:space-between;gap:var(--s3);margin-top:var(--s2);color:var(--ink-3);font-size:.78rem;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
@supports not (backdrop-filter: blur(2px)){ .glass{background:rgba(30,32,40,.86);} }
@media (prefers-reduced-motion: reduce){ *{animation:none;transition:none;} }
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{GLASS_CSS}</style>"
        f"</head><body>{body}</body></html>"
    )
