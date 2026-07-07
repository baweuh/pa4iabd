"""Root entry point shim — delegates to :func:`src.main.main`.

Keeps the documented ``python main.py [--mode ...]`` commands working while the
real CLI lives in :mod:`src.main`.
"""

from src.main import main

if __name__ == "__main__":
    raise SystemExit(main())
