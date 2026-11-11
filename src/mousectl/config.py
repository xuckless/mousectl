"""~/.config/mousectl/config.json: the one source of truth (the mouse itself stores nothing)."""
from __future__ import annotations

import copy
import json
import logging
import os

from . import protocol as P

PATH = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "mousectl", "config.json")
log = logging.getLogger("mousectl")


def mtime() -> float | None:
    try:
        return os.stat(PATH).st_mtime
    except OSError:
        return None


def load(strict: bool = False) -> dict:
    try:
        with open(PATH) as f:
            raw = json.load(f)
    except FileNotFoundError:
        return P.validate(copy.deepcopy(P.DEFAULT_CONFIG))
    except ValueError as e:
        if strict:
            raise ValueError(f"{PATH}: {e}") from None
        log.error("%s is not valid JSON (%s); using defaults", PATH, e)
        return P.validate(copy.deepcopy(P.DEFAULT_CONFIG))
    try:
        return P.validate(raw if isinstance(raw, dict) else {})
    except (ValueError, TypeError, KeyError) as e:
        if strict:
            raise ValueError(str(e)) from None
        log.error("invalid settings in %s (%s); using defaults", PATH, e)
        return P.validate(copy.deepcopy(P.DEFAULT_CONFIG))


def save(cfg: dict) -> dict:
    clean = P.validate(cfg)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(clean, f, indent=2)
    os.replace(tmp, PATH)
    return clean
