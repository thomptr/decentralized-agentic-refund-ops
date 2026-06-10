"""Console-script launcher for the Streamlit demo UI (``demo-ui`` entry point).

Runs ``streamlit run apps/demo_ui/app.py`` on the configured port (default 8200,
overridable via ``UI_PORT``) so the UI starts with a single ``uv run demo-ui``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    app_path = str(Path(__file__).with_name("app.py"))
    port = os.environ.get("UI_PORT", "8200")
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port",
        port,
        "--server.headless",
        "true",
    ]
    from streamlit.web import cli as stcli

    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
