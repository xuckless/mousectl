#!/bin/sh
# Install mousectl for your user. Re-run to update.
#   ~/.local/lib/mousectl, ~/.local/bin/mousectl, systemd --user service, app launcher,
#   and (sudo, once) the udev rule that lets you talk to the mouse.
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" -eq 0 ] && { echo "Run as your normal user."; exit 1; }

if ! cmp -s packaging/70-instant-mouse.rules /etc/udev/rules.d/70-instant-mouse.rules 2>/dev/null; then
  echo "==> Installing udev rule (sudo)"
  sudo install -m644 packaging/70-instant-mouse.rules /etc/udev/rules.d/70-instant-mouse.rules
  sudo udevadm control --reload
  sudo udevadm trigger --subsystem-match=hidraw --action=change
fi

echo "==> Installing for $(id -un)"
LIB="$HOME/.local/lib/mousectl"
rm -rf "$LIB.new" && mkdir -p "$LIB.new" && cp -r src/mousectl "$LIB.new/" && cp README.md LICENSE "$LIB.new/"
find "$LIB.new" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$LIB" && mv "$LIB.new" "$LIB"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/mousectl" <<EOS
#!/bin/sh
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "$LIB"); from mousectl.cli import main; main()' "\$@"
EOS
chmod 755 "$HOME/.local/bin/mousectl"
mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
install -m644 packaging/mousectl.service "$HOME/.config/systemd/user/mousectl.service"
install -m644 packaging/mousectl.desktop "$HOME/.local/share/applications/mousectl.desktop"
systemctl --user daemon-reload
systemctl --user enable --now mousectl.service
systemctl --user restart mousectl.service
sleep 2
if systemctl --user is-active --quiet mousectl; then echo "✓ background service running"; else echo "! service failed: journalctl --user -u mousectl -n 30"; fi
echo "✓ Done. Open 'Mouse Settings' from the app menu, or run: mousectl gui"
