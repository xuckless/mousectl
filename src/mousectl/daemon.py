"""mousectl daemon: per-user service.

* Re-applies your settings whenever the mouse appears (it forgets everything when unplugged),
  and whenever the config file changes.
* Performs host actions (key combos, media keys, macros) for buttons bound to them: the mouse
  reports the press on interface 1, and we ask the mouse to type the keys (07 15 / 07 17).
* Writes a small status file the GUI reads (active DPI stage, last button, heartbeat).
"""
from __future__ import annotations

import json
import logging
import os
import select
import threading
import time

from . import config, protocol as P
from .hidraw import DeviceError

log = logging.getLogger("mousectl")


def status_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/mousectl-{os.getuid()}"
    os.makedirs(os.path.join(base, "mousectl"), mode=0o700, exist_ok=True)
    return os.path.join(base, "mousectl", "status.json")


def read_status() -> dict | None:
    try:
        with open(status_path()) as f:
            st = json.load(f)
        return st if time.time() - st.get("heartbeat", 0) < 6 else None
    except (OSError, ValueError):
        return None


class Daemon:
    def __init__(self):
        self.cfg = config.load()
        self.cfg_mtime = config.mtime()
        self.mouse: P.Mouse | None = None
        self.instance: str | None = None
        self.held: dict[str, list[int]] = {}
        self.status = {"connected": False, "active_dpi": None, "last_button": None, "pid": os.getpid()}
        self.send_lock = threading.Lock()

    def write_status(self) -> None:
        self.status["heartbeat"] = time.time()
        tmp = status_path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.status, f)
        os.replace(tmp, status_path())

    def connect(self) -> None:
        try:
            path = P.find_config_node()
        except DeviceError:
            if self.mouse:
                log.info("mouse unplugged")
            self.close()
            return
        inst = P.instance_id(path)
        if self.mouse and inst == self.instance:
            return
        self.close()
        try:
            m = P.Mouse(path)
            m.h.open()
        except DeviceError as e:
            log.warning("%s", e)
            return
        self.mouse, self.instance = m, inst
        log.info("mouse connected (%s), applying settings", inst)
        self.apply()

    def close(self) -> None:
        if self.mouse:
            self.mouse.h.close()
        self.mouse, self.instance = None, None
        self.held.clear()
        self.status.update(connected=False)

    def apply(self) -> None:
        if not self.mouse:
            return
        try:
            with self.send_lock:
                self.mouse.apply(self.cfg)
            self.status.update(connected=True, active_dpi=self.cfg["dpi"]["active"])
        except (OSError, DeviceError) as e:
            log.warning("apply failed: %s", e)
            self.close()

    def reload_if_changed(self) -> None:
        mt = config.mtime()
        if mt != self.cfg_mtime:
            self.cfg_mtime = mt
            try:
                self.cfg = config.load(strict=True)
                log.info("config changed, re-applying")
                self.apply()
            except ValueError as e:
                log.error("ignoring invalid config: %s", e)

    # ------------------------------------------------------------ host actions
    def on_button(self, name: str, pressed: bool) -> None:
        b = self.cfg["buttons"].get(name, {})
        a = b.get("action")
        m = self.mouse
        if not m:
            return
        with self.send_lock:
            if a == "keys":
                codes = P.key_codes(b["keys"])
                if pressed:
                    m.keys_down(codes)
                    self.held[name] = codes
                elif name in self.held:
                    m.keys_up(self.held.pop(name))
            elif a == "media" and pressed:
                m.media(P.MEDIA[b["key"]][0])
        if a == "macro" and pressed:
            threading.Thread(target=self.run_macro, args=(b["steps"],), daemon=True).start()

    def run_macro(self, steps: list[dict]) -> None:
        for st in steps:
            m = self.mouse
            if not m:
                return
            if "delay" in st:
                time.sleep(st["delay"] / 1000)
                continue
            with self.send_lock:
                if "keys" in st:
                    codes = P.key_codes(st["keys"])
                    m.keys_down(codes)
                    m.keys_up(codes)
                elif "media" in st:
                    m.media(P.MEDIA[st["media"]][0])

    def handle_report(self, data: bytes) -> None:
        if len(data) >= 3 and data[0] == 0x06:
            code, st = data[1] - 0xF0, data[2]
            name = P.BUTTON_BY_CODE.get(code)
            if not name:
                return
            pressed = st != 0x80
            if pressed:
                self.status.update(active_dpi=st, last_button={"name": name, "time": time.time()})
            self.on_button(name, pressed)

    # ------------------------------------------------------------ loop
    def run(self) -> None:
        last_scan = 0.0
        while True:
            now = time.monotonic()
            if now - last_scan > 1.0:
                last_scan = now
                self.connect()
                self.reload_if_changed()
                self.write_status()
            fd = self.mouse.h.fd if self.mouse else None
            if fd is None:
                time.sleep(0.5)
                continue
            try:
                r, _, _ = select.select([fd], [], [], 0.5)
                if r:
                    data = os.read(fd, 16)
                    if data:
                        self.handle_report(data)
            except OSError:          # unplugged mid-read
                self.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("mousectl daemon started (config %s)", config.PATH)
    try:
        Daemon().run()
    except KeyboardInterrupt:
        pass
