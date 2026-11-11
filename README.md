# mousectl

**Buttons, DPI and lighting for the "INSTANT USB GAMING MOUSE" (USB `30fa:1701`, Instant Microelectronics A704) on Linux.**
This is a generic mouse sold or given away under many names; check `lsusb` for `30fa:1701`.

> Unofficial. GPL-2.0-or-later. Protocol from [Instant-A704F-Mouse-Utilities](https://github.com/Kenny-Hui/Instant-A704F-Mouse-Utilities)
> (MIT) and OpenRGB's InstantMouseController (GPL-2.0+), and checked on this mouse.

## Features
| | |
|---|---|
| **Buttons** | Remap all 7 (left, right, wheel click, 2 side, 2 top DPI buttons) to: any mouse action (clicks, back/forward, DPI ±/cycle, double-click, auto-fire, show desktop), **any key combo** (held while you hold the button), **media keys**, **macros** (keys + media + delays), or disabled. Quick picks for useful shortcuts. |
| **DPI** | 4 stages, 200–3000 DPI in steps of 200, each can be switched off; pick the active stage. |
| **Lighting** | Off, static colour (any colour), rainbow breathing (6 speeds); breathing in a colour and colour cycle are untested on this mouse. |
| **Scroll** | Normal, reversed, or volume knob. |
| **Fire** | Auto-click interval for buttons set to "Fire". |
| **Polling rate** | Shown: 125 Hz is this mouse's hardware maximum (USB low-speed, 10 ms interval; the kernel's `mousepoll` override doesn't apply on USB 3 controllers — measured). |

The mouse remembers **nothing** when unplugged, so a small per-user service (`mousectl.service`) re-applies
your settings every time it appears, and performs key/media/macro actions (the mouse tells us a button was
pressed; we ask the mouse to type the keys, so no extra permissions are needed).

## Install
```sh
./install.sh      # user install; asks for sudo only once, for the udev rule
mousectl gui      # or "Mouse Settings" in the app menu
```

## Command line
```sh
mousectl show
mousectl dpi 800 1600 2400 3000 --active 1
mousectl bind top_front media volume_up
mousectl bind top_back keys super pagedown
mousectl bind side_back back
mousectl light static --color '#00aaff'
mousectl light rainbow_breathing --speed 2
mousectl scroll reversed
```
Buttons: `left middle right side_front side_back top_front top_back`.

## Safety
At least one button must stay a left click. If something goes wrong, unplug and re-plug the mouse:
without the service it boots into its factory behaviour.

Settings live in `~/.config/mousectl/config.json`. Remove with `./uninstall.sh`.
