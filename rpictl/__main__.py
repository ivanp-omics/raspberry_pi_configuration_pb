"""Ulazna tocka:  python -m rpictl  [--config config.yaml]"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from .config import load_config


def main() -> None:
    ap = argparse.ArgumentParser(prog="rpictl")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s  %(levelname)-7s %(name)-22s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    cfg = load_config(args.config)
    from .app import create_app

    uvicorn.run(
        create_app(args.config),
        host=cfg.server.host,
        port=cfg.server.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
