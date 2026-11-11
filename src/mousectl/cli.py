"""mousectl command line."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, config, daemon, protocol as P
from .hidraw import DeviceError


def _apply(cfg, parts=None):
    clean = config.save(cfg)
    try:
        with P.Mouse() as m:
            m.apply(clean, parts or ("lighting", "scroll", "fire", "buttons", "dpi"))
        print("Applied and saved.")
    except DeviceError as e:
        print(f"Saved (not applied: {e})")


def main(argv=None):
    p = argparse.ArgumentParser(prog="mousectl", description="Instant A704 gaming mouse (30fa:1701) on Linux")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("gui", help="open the editor in your browser")
    g.add_argument("--port", type=int, default=0)
    g.add_argument("--no-browser", action="store_true")
    sub.add_parser("show", help="current settings")
    sub.add_parser("apply", help="re-send saved settings to the mouse")
    sub.add_parser("daemon", help="run the background service (used by systemd --user)")
    l = sub.add_parser("light", help="lighting")
    l.add_argument("mode", choices=list(P.LIGHT_MODES))
    l.add_argument("--color")
    l.add_argument("--speed", type=int, choices=range(0, P.SPEED_MAX + 1), metavar=f"0-{P.SPEED_MAX}")
    l.add_argument("--brightness", type=int, choices=range(0, P.BRIGHTNESS_MAX + 1), metavar=f"0-{P.BRIGHTNESS_MAX}")
    d = sub.add_parser("dpi", help="DPI stages, e.g. dpi 800 1600 2400 3000 --active 1")
    d.add_argument("values", nargs="+", type=int)
    d.add_argument("--active", type=int, default=None, help="stage index 0-3")
    b = sub.add_parser("bind", help="bind a button, e.g. bind top_front keys ctrl c | media volume_up | dpi_up")
    b.add_argument("button", choices=list(P.BUTTONS))
    b.add_argument("action", choices=[*P.MOUSE_ACTIONS, "keys", "media", "disabled"])
    b.add_argument("args", nargs="*")
    s = sub.add_parser("scroll", help="scroll wheel mode")
    s.add_argument("mode", choices=list(P.SCROLL))
    a = p.parse_args(argv)
    try:
        if a.cmd == "gui":
            from .gui import serve
            serve(a.port, not a.no_browser)
        elif a.cmd == "daemon":
            daemon.main()
        elif a.cmd in (None, "show"):
            cfg = config.load()
            st = daemon.read_status()
            print(json.dumps(cfg, indent=2))
            print(f"report rate: {P.report_rate() or '?'} Hz | background service: {'running' if st else 'NOT running'}")
        elif a.cmd == "apply":
            _apply(config.load())
        else:
            cfg = config.load()
            if a.cmd == "light":
                li = cfg["lighting"]
                li["mode"] = a.mode
                for k in ("color", "speed", "brightness"):
                    if getattr(a, k) is not None:
                        li[k] = getattr(a, k)
                _apply(cfg, ("lighting",))
            elif a.cmd == "dpi":
                vals = (a.values + [a.values[-1]] * 4)[:4]
                cfg["dpi"]["stages"] = [{"dpi": v, "enabled": i < len(a.values)} for i, v in enumerate(vals)]
                if a.active is not None:
                    cfg["dpi"]["active"] = a.active
                _apply(cfg, ("dpi",))
            elif a.cmd == "bind":
                if a.action == "keys":
                    bind = {"action": "keys", "keys": a.args}
                elif a.action == "media":
                    bind = {"action": "media", "key": a.args[0] if a.args else ""}
                else:
                    bind = {"action": a.action}
                cfg["buttons"][a.button] = bind
                _apply(cfg, ("buttons",))
                if a.action in ("keys", "media") and not daemon.read_status():
                    print("! key/media bindings need the background service: systemctl --user enable --now mousectl")
            elif a.cmd == "scroll":
                cfg["scroll"] = a.mode
                _apply(cfg, ("scroll",))
    except (DeviceError, ValueError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
