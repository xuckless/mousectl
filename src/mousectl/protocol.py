"""Instant Microelectronics A704 gaming mouse (USB 30fa:1701): configuration protocol.

All commands are 8-byte HID feature reports with id 0x07 on interface 1 ("07 CC ..").
The mouse stores nothing: everything must be re-sent after every plug-in.

Sources
  * Instant-A704F-Mouse-Utilities SPECS.md + source (MIT, AmberIsFrozen / Kenny-Hui): buttons, DPI,
    scroll, fire, native lighting modes, key/media injection, button event reports.
  * OpenRGB InstantMouseController (GPL-2.0-or-later, Guimard Morgan): colour (07 14) and the
    extended lighting mode packet (07 13 ff ..).
  * Verified on this mouse 2026-11-10: native static (07 13 7f 16), colour + direct mode (solid red),
    feature-report readback, report rate 125 Hz (8 ms, hardware maximum: USB low-speed, bInterval 10).
"""
from __future__ import annotations

import os
import time

from .hidraw import DeviceError, Hidraw, find

VID, PID = 0x30FA, 0x1701
RID = 0x07

# ---------------------------------------------------------------- buttons
# physical button id (07 10 BT ..) == event code (06 F<id> ..) - 0xF0
BUTTONS = {
    "left": (0x01, "Left button"),
    "middle": (0x02, "Wheel click"),
    "right": (0x03, "Right button"),
    "side_front": (0x05, "Side button (front)"),
    "side_back": (0x04, "Side button (back)"),
    "top_front": (0x08, "Top button (front)"),
    "top_back": (0x06, "Top button (back)"),
}
BUTTON_BY_CODE = {code: name for name, (code, _) in BUTTONS.items()}

# actions the mouse performs itself
MOUSE_ACTIONS = {
    "left_click": (0x01, "Left click"),
    "middle_click": (0x02, "Middle click"),
    "right_click": (0x03, "Right click"),
    "back": (0x04, "Back"),
    "forward": (0x05, "Forward"),
    "dpi_cycle": (0x06, "DPI cycle"),
    "dpi_up": (0x0B, "DPI +"),
    "dpi_down": (0x0C, "DPI −"),
    "double_click": (0x08, "Double click"),
    "fire": (0x09, "Fire (auto-click)"),
    "show_desktop": (0x07, "Show desktop"),
}
HOST_ACTION = 0x00   # "key input": the mouse reports the press and we decide what happens

DEFAULT_BUTTONS = {
    "left": {"action": "left_click"}, "middle": {"action": "middle_click"}, "right": {"action": "right_click"},
    "side_front": {"action": "forward"}, "side_back": {"action": "back"},
    "top_front": {"action": "dpi_up"}, "top_back": {"action": "dpi_down"},
}

# ---------------------------------------------------------------- keys (HID usage page 0x07)
KEYS: dict[str, int] = {}
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    KEYS[c] = 0x04 + i
for i, c in enumerate("1234567890"):
    KEYS[c] = 0x1E + i
KEYS.update({
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C, "minus": 0x2D, "equal": 0x2E,
    "leftbrace": 0x2F, "rightbrace": 0x30, "backslash": 0x31, "semicolon": 0x33, "apostrophe": 0x34,
    "grave": 0x35, "comma": 0x36, "dot": 0x37, "slash": 0x38, "capslock": 0x39,
    **{f"f{i}": 0x3A + i - 1 for i in range(1, 13)}, **{f"f{i}": 0x68 + i - 13 for i in range(13, 25)},
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49, "home": 0x4A, "pageup": 0x4B,
    "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "menu": 0x65,
    "ctrl": 0xE0, "shift": 0xE1, "alt": 0xE2, "super": 0xE3,
    "rctrl": 0xE4, "rshift": 0xE5, "altgr": 0xE6, "rsuper": 0xE7,
})
MODIFIERS = {"ctrl", "shift", "alt", "super", "rctrl", "rshift", "altgr", "rsuper"}

# Consumer page usages, sent with 07 17 hi lo
MEDIA = {
    "volume_up": (0x00E9, "Volume up"), "volume_down": (0x00EA, "Volume down"), "mute": (0x00E2, "Mute"),
    "play_pause": (0x00CD, "Play / pause"), "next": (0x00B5, "Next track"), "previous": (0x00B6, "Previous track"),
    "stop": (0x00B7, "Stop"), "browser": (0x0223, "Web browser"), "browser_back": (0x0224, "Browser back"),
    "browser_forward": (0x0225, "Browser forward"), "browser_refresh": (0x0227, "Browser refresh"),
    "calculator": (0x0192, "Calculator"), "mail": (0x018A, "Mail"), "media_player": (0x0183, "Media player"),
}

# ---------------------------------------------------------------- lighting
# kind "native": 07 13 7f CF (A704 app), "orgb": 07 13 ff ... (OpenRGB). verified = seen working here.
LIGHT_MODES = {
    "off": {"name": "Off", "kind": "native", "color": False, "speed": False, "verified": True},
    "static": {"name": "Static colour", "kind": "orgb", "value": 0x0A, "color": True, "speed": False, "verified": True},
    "rainbow_breathing": {"name": "Rainbow breathing", "kind": "native", "color": False, "speed": True, "verified": True},
    "breathing": {"name": "Breathing", "kind": "orgb", "value": 0x08, "color": True, "speed": True, "verified": False},
    "spectrum": {"name": "Colour cycle", "kind": "orgb", "value": 0x06, "color": False, "speed": True, "verified": False},
}
SPEED_MAX = 5           # 0 = slowest (6 s cycle) .. 5 = fastest (1 s)
BRIGHTNESS_MAX = 7

# ---------------------------------------------------------------- DPI
DPI_STEP, DPI_MIN, DPI_MAX = 200, 200, 3000   # 4-bit value x 200
DPI_STAGES = 4

SCROLL = {"normal": (0x00, 0x00), "volume": (0x01, 0x00), "reversed": (0x02, 0x02)}

DEFAULT_CONFIG = {
    "lighting": {"mode": "rainbow_breathing", "color": "#ff0000", "speed": 0, "brightness": 7},
    "dpi": {"stages": [{"dpi": 600, "enabled": True}, {"dpi": 800, "enabled": True},
                       {"dpi": 1200, "enabled": True}, {"dpi": 2400, "enabled": True}], "active": 1},
    "buttons": DEFAULT_BUTTONS,
    "scroll": "normal",
    "fire_rate": 4,
}


def _rgb(s: str) -> tuple[int, int, int]:
    s = str(s).strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"bad colour {s!r}, expected #rrggbb")
    v = bytes.fromhex(s)
    return v[0], v[1], v[2]


def _keys(names) -> list[int]:
    if not isinstance(names, list) or not 1 <= len(names) <= 6:
        raise ValueError("a key combo needs 1..6 keys")
    out = []
    for n in names:
        k = str(n).lower()
        if k not in KEYS:
            raise ValueError(f"unknown key {n!r}")
        out.append(KEYS[k])
    return out


def validate_binding(name: str, b: dict) -> dict:
    a = b.get("action")
    if a in MOUSE_ACTIONS:
        return {"action": a}
    if a == "keys":
        _keys(b.get("keys"))
        return {"action": "keys", "keys": [str(k).lower() for k in b["keys"]]}
    if a == "media":
        if b.get("key") not in MEDIA:
            raise ValueError(f"unknown media key {b.get('key')!r}")
        return {"action": "media", "key": b["key"]}
    if a == "macro":
        steps = b.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
            raise ValueError("a macro needs 1..32 steps")
        clean = []
        for st in steps:
            if "keys" in st:
                _keys(st["keys"])
                clean.append({"keys": [str(k).lower() for k in st["keys"]]})
            elif "delay" in st:
                d = int(st["delay"])
                if not 0 <= d <= 5000:
                    raise ValueError("macro delays must be 0..5000 ms")
                clean.append({"delay": d})
            elif "media" in st:
                if st["media"] not in MEDIA:
                    raise ValueError(f"unknown media key {st['media']!r}")
                clean.append({"media": st["media"]})
            else:
                raise ValueError("macro steps are {keys}, {media} or {delay}")
        return {"action": "macro", "steps": clean, "name": str(b.get("name", ""))[:40]}
    if a == "disabled":
        return {"action": "disabled"}
    raise ValueError(f"{name}: unknown action {a!r}")


def validate(cfg: dict) -> dict:
    base = DEFAULT_CONFIG
    out: dict = {}
    li = {**base["lighting"], **(cfg.get("lighting") or {})}
    if li["mode"] not in LIGHT_MODES:
        raise ValueError(f"unknown lighting mode {li['mode']!r}")
    _rgb(li["color"])
    sp, br = int(li["speed"]), int(li["brightness"])
    if not 0 <= sp <= SPEED_MAX or not 0 <= br <= BRIGHTNESS_MAX:
        raise ValueError(f"speed 0..{SPEED_MAX}, brightness 0..{BRIGHTNESS_MAX}")
    out["lighting"] = {"mode": li["mode"], "color": "#" + "".join(f"{c:02x}" for c in _rgb(li["color"])),
                       "speed": sp, "brightness": br}

    dp = cfg.get("dpi") or base["dpi"]
    stages = dp.get("stages") or base["dpi"]["stages"]
    if len(stages) != DPI_STAGES:
        raise ValueError(f"exactly {DPI_STAGES} DPI stages")
    clean = []
    for s in stages:
        d = int(s["dpi"])
        if not DPI_MIN <= d <= DPI_MAX or d % DPI_STEP:
            raise ValueError(f"DPI must be {DPI_MIN}..{DPI_MAX} in steps of {DPI_STEP}")
        clean.append({"dpi": d, "enabled": bool(s.get("enabled", True))})
    if not any(s["enabled"] for s in clean):
        raise ValueError("at least one DPI stage must be enabled")
    active = int(dp.get("active", 0))
    if not 0 <= active < DPI_STAGES or not clean[active]["enabled"]:
        active = next(i for i, s in enumerate(clean) if s["enabled"])
    out["dpi"] = {"stages": clean, "active": active}

    btn = {**base["buttons"], **(cfg.get("buttons") or {})}
    out["buttons"] = {n: validate_binding(n, btn[n]) for n in BUTTONS}
    if not any(b["action"] == "left_click" for b in out["buttons"].values()):
        raise ValueError("at least one button must stay a left click (otherwise you can't click anything)")

    sc = cfg.get("scroll", base["scroll"])
    if sc not in SCROLL:
        raise ValueError(f"scroll must be one of {', '.join(SCROLL)}")
    out["scroll"] = sc
    fr = int(cfg.get("fire_rate", base["fire_rate"]))
    if not 0 <= fr <= 255:
        raise ValueError("fire rate 0..255")
    out["fire_rate"] = fr
    return out


# ---------------------------------------------------------------- device
def report_rate() -> int | None:
    """Actual polling rate the host uses (from the endpoint descriptor)."""
    for d in find(VID, PID):
        # .../usb1/1-1/1-1:1.0/0003:30FA:1701.000B -> the USB interface dir is the parent
        intf = os.path.dirname(os.path.realpath(f"/sys/class/hidraw/{os.path.basename(d)}/device"))
        for ep in os.listdir(intf):
            if ep.startswith("ep_8"):
                try:
                    ms = int(open(os.path.join(intf, ep, "interval")).read().strip().rstrip("ms"))
                except (OSError, ValueError):
                    continue
                # xHCI rounds full/low-speed intervals down to a power of two
                p = 1
                while p * 2 <= ms:
                    p *= 2
                return round(1000 / p)
    return None


def find_config_node() -> str:
    """The hidraw node of interface 1 (vendor feature report 7 + button events)."""
    for path in find(VID, PID):
        node = os.path.basename(path)
        try:
            uevent = open(f"/sys/class/hidraw/{node}/device/uevent").read()
        except OSError:
            continue
        if "HID_PHYS=" in uevent and uevent.split("HID_PHYS=")[1].split("\n")[0].endswith("/input1"):
            return path
    raise DeviceError("Mouse not found (USB 30fa:1701). Is it plugged in?")


def instance_id(path: str) -> str:
    """Changes every time the mouse is re-plugged (e.g. '0003:30FA:1701.000C')."""
    return os.path.basename(os.path.realpath(f"/sys/class/hidraw/{os.path.basename(path)}/device"))


class Mouse:
    def __init__(self, path: str | None = None):
        self.path = path or find_config_node()
        self.h = Hidraw(self.path)

    def __enter__(self):
        self.h.open()
        return self

    def __exit__(self, *a):
        self.h.close()

    def cmd(self, *b: int) -> None:
        pkt = bytes([RID, *b]) + b"\x00" * (7 - len(b))
        self.h.set_feature(pkt[:8])
        time.sleep(0.012)    # the vendor app spaces commands ~12 ms apart

    def status(self) -> bytes:
        return self.h.get_feature(RID, 8)

    # -- lighting
    def lighting(self, li: dict) -> None:
        m = LIGHT_MODES[li["mode"]]
        if li["mode"] == "off":
            self.cmd(0x13, 0x7F, 0x17)
        elif li["mode"] == "rainbow_breathing":
            self.cmd(0x13, 0x7F, 0x10 | (li["speed"] & 0x0F))
        else:
            r, g, b = _rgb(li["color"])
            # scale brightness into the colour too, so it also works where the brightness nibble is ignored
            R, G, B = (0xF - c // 16 for c in (r, g, b))
            for slot in range(0, 0xB, 2):
                self.cmd(0x14, (slot << 4) | G, (R << 4) | B)
            v = m["value"]
            speed = li["speed"] if m["speed"] else 0
            self.cmd(0x13, 0xFF, ((v << 4) & 0xF0) | speed, 0x0B, 0xF - li["brightness"], v & 0xF0)

    # -- the rest
    def dpi(self, dp: dict) -> None:
        mask = sum(1 << i for i, s in enumerate(dp["stages"]) if s["enabled"])
        for i, s in enumerate(dp["stages"]):
            self.cmd(0x09, dp["active"], ((s["dpi"] // DPI_STEP) << 4) | (0x08 + i), mask)

    def buttons(self, bt: dict) -> None:
        for name, b in bt.items():
            code = BUTTONS[name][0]
            act = MOUSE_ACTIONS[b["action"]][0] if b["action"] in MOUSE_ACTIONS else HOST_ACTION
            self.cmd(0x10, code, act)

    def scroll(self, mode: str) -> None:
        self.cmd(0x11, *SCROLL[mode])

    def fire_rate(self, v: int) -> None:
        self.cmd(0x12, 0x00, v)

    def apply(self, cfg: dict, parts=("lighting", "scroll", "fire", "buttons", "dpi")) -> None:
        if "lighting" in parts:
            self.lighting(cfg["lighting"])
        if "scroll" in parts:
            self.scroll(cfg["scroll"])
        if "fire" in parts:
            self.fire_rate(cfg["fire_rate"])
        if "buttons" in parts:
            self.buttons(cfg["buttons"])
        if "dpi" in parts:
            self.dpi(cfg["dpi"])

    # -- injected input (the mouse types these for us)
    def keys_down(self, codes: list[int]) -> None:
        held: list[int] = []
        for c in sorted(codes, key=lambda c: c < 0xE0):   # modifiers first
            held.append(c)
            self.cmd(0x15, *held)

    def keys_up(self, codes: list[int]) -> None:
        held = sorted(codes, key=lambda c: c < 0xE0)
        while held:
            held.pop()
            self.cmd(0x15, *held)

    def media(self, usage: int) -> None:
        self.cmd(0x17, usage >> 8, usage & 0xFF)
        time.sleep(0.02)
        self.cmd(0x17, 0x00, 0x00)


def key_codes(names: list[str]) -> list[int]:
    return _keys(names)
