"""Regenerate analytics-demo.html from the spike's output.

    .venv/bin/python plan/spike_analytics_yfinance.py   # fetch live data -> analytics.json
    .venv/bin/python plan/build_demo.py                 # inject it into the template

Kept separate so the page can be restyled without re-hitting a rate-limited endpoint.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent


def main() -> None:
    data = json.loads((HERE / "analytics.json").read_text())
    tpl = (HERE / "analytics-demo.template.html").read_text()
    # A literal </script> inside the payload would terminate the host <script> block.
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    dest = REPO / "analytics-demo.html"
    dest.write_text(tpl.replace("/*__ANALYTICS_JSON__*/", blob))
    print(f"wrote {dest}  ({dest.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
