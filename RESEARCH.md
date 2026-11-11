# "INSTANT USB GAMING MOUSE" (30fa:1701) on Linux: research notes

## Hardware
- USB `30fa:1701`, manufacturer string "INSTANT", product "USB GAMING MOUSE", bcdDevice 1.00
- 30FA is **Instant Microelectronics**, a sensor/MCU vendor sold under many budget brands
  (Anko/Kmart, AntEsports, Advanced GTA, and others).
- Two HID interfaces, `/dev/hidraw0` (mouse) and `/dev/hidraw1` (keyboard + vendor).
  Both are currently **root-only** (`crw------- root root`), so a udev rule is needed.

## Interface 1 report descriptor
| Report ID | Usage page | Kind | Size | Meaning |
|---|---|---|---|---|
| 3 | keyboard | input | 8 B | keys the mouse can emit (macros, remaps) |
| 2 | consumer | input | 2 B | media keys |
| **6** | 0xFF00 | input | 2 B | button events / active DPI slot |
| **7** | 0xFF01 | **feature** | 7 B (+ID) | **configuration channel** |
| 8 | system control | input | 3 bits | power/sleep/wake |

This matches the Instant-chip mice documented below, so the protocol is very likely the same.

## Prior work
1. **OpenRGB `InstantMouseController`** (code in `reference/`, GPL-2.0-or-later)
   - Supports PIDs `1030`, `1040`, `1440`, `1540`. **Not `1701`**, which is why OpenRGB ignores this mouse.
   - `07 13 FF MS DN 0B M0 00` sets the mode: M = mode, S = speed 0-5, D = direction, N = LED mask, B = brightness (0 full … 7 off)
   - Modes: Direct 0x0A, Off 0xFF, Multicolor breathing 0x01, Fill/drain 0x03, Loop 0x04,
     Spectrum 0x06, Rainbow wave 0x07, Breathing 0x08/0x09, Flicker 0xB8, Star trek 0xB9,
     Ripple 0xBA, Enraptured 0xBB
   - `07 14 XG RB 00 00 00 00` sets the color: 4 bits per channel, **inverted** (0xF − value/16), X = DPI slot
     (the color is sent once per slot, 0..A step 2)
2. **Blog: "Reverse Engineering an USB mouse"** (Amber, 2024-05-13),
   https://blog.lx862.com/blog/2024-05-13-reverse-engineering-a-mouse/
   - `07 09 AD DP 0F ..` DPI stages (4 slots, enable mask, DPI codes 200…4800)
   - `07 10 BT AT ..` button remap (Left/Right/Middle/Side fwd/back/extra → click, DPI±, double-click, fire, show desktop, or software action)
   - `07 11 SM ..` scroll mode (normal / volume)
   - `07 12 00 FR ..` "fire" (auto-click) rate
   - `07 15 k1..k6` / `07 17 hi lo` emit keyboard / media keys (used for software macros)
   - On that model, **settings are not stored in the mouse**; the vendor software re-sends them on startup.
     Needs checking on this one.
3. OpenRGB issue #3551 (Anko 30FA:1440) has a USB capture and vendor-software screenshots.

## What a Linux tool can likely match from the Windows app
- Lighting modes, color, speed, brightness, direction: **likely** (OpenRGB packets)
- DPI stages and the active stage: **likely** (blog packets)
- Button remapping, fire button, scroll mode: **likely** (blog packets)
- Key/media macros: yes, but needs a small background service (the mouse asks the host to send them)
- Polling rate, lift-off distance: **unknown**, not documented anywhere; needs a capture from the Windows app
- If settings don't persist, a small autostart service re-applies them at login/hotplug

## Unverified (needs testing on the real mouse)
- Whether 1701 accepts all the same packets (very likely, same descriptor shape)
- How many LEDs / zones it has, and which modes its firmware implements
- Whether writes persist across unplugging

## Verified on this mouse (2026-11-10)
- It's an **Instant A704** (exactly the `30fa:1701` that Instant-A704F-Mouse-Utilities supports). Plain 8-byte feature reports `07 …` on interface 1 work; the utility's 16-byte "fake setup header" wrapping isn't needed.
- Lighting: native static `07 13 7f 16` works. OpenRGB's colour `07 14` ×6 slots + direct mode `07 13 ff a0 0b 08 00` gives solid red, so **custom colours work**.
- GET_FEATURE 7 returns `07 00 80 08 72 28 02 xx`; the last byte follows the lighting state (1b → 10 → 2b). Not decoded further.
- Button event codes (06 Fx state, state 0x80 = release): top front f8, top back f6, side front f5, side back f4. These match the physical ids in `07 10`.
- Host actions: a button bound to 00 reports press/release, and `07 17` media injection works (volume up/down), including after a re-plug via the user service.
- **Polling rate: 125 Hz** (8 ms measured). Low-speed USB 1.1, bInterval 10. `usbhid.mousepoll=1` made no difference (the endpoint stays at 10 ms on xHCI). Not changeable without kernel/firmware changes.
- Defaults the tool sets: DPI 600/800/1200/2400 (active 800); top buttons DPI+ (0b) / DPI− (0c) as in the working utility (the spec's 0a/0b looks off by one).

## Not yet verified
- Key-combo injection (`07 15`) and holding, OpenRGB breathing (0x08) and colour cycle (0x06), true DPI values, fire rate timing.
