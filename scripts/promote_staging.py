from __future__ import annotations

from diagnostic_reasoning.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["promote-staging", *(__import__("sys").argv[1:])]))
