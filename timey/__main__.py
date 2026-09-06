"""Allow running as ``python -m timey``."""

import sys

from .app import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
