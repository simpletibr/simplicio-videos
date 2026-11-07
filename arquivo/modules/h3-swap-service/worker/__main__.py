"""Entry point: `python -m worker` (reads configuration from the environment)."""

from __future__ import annotations

import logging
import sys

from worker.config import Config
from worker.runner import run_forever


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        config = Config.from_env()
    except ValueError as exc:
        logging.error("configuration error: %s", exc)
        return 2
    run_forever(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
