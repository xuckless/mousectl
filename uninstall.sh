#!/bin/sh
set -eu
systemctl --user disable --now mousectl.service 2>/dev/null || true
rm -rf "$HOME/.local/lib/mousectl" "$HOME/.local/bin/mousectl" "$HOME/.config/systemd/user/mousectl.service" "$HOME/.local/share/applications/mousectl.desktop"
systemctl --user daemon-reload
echo "Removed. Settings kept in ~/.config/mousectl. The mouse returns to its defaults when re-plugged."
echo "Udev rule left in place; remove with: sudo rm /etc/udev/rules.d/70-instant-mouse.rules"
