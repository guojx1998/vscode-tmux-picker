#!/bin/bash
# Installer for the OPTIONAL session-persistence add-on (vsct-persist.py).
# Same philosophy as install.sh: copy the script, then PRINT the cron line and
# systemd unit for you to wire up yourself — we don't edit your crontab or
# enable units behind your back.
#
# Override the destination with VSCT_PERSIST_DEST=/some/path/vsct-persist.py
set -e

here="$(cd "$(dirname "$0")" && pwd)"
src="$here/vsct-persist.py"
dest="${VSCT_PERSIST_DEST:-$HOME/.local/bin/vsct-persist.py}"

mkdir -p "$(dirname "$dest")"
cp "$src" "$dest"
chmod +x "$dest"
echo "installed: $dest"

unit_dir="$HOME/.config/systemd/user"

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
1) Snapshot every 2 minutes — add to your crontab (crontab -e):

   3-59/2 * * * * $dest snapshot >> \$HOME/.local/state/vsct/snapshot.log 2>&1

2) Restore at boot — install the user unit and enable lingering:

   cp "$here/vsct-restore.service.example" "$unit_dir/vsct-restore.service"
   systemctl --user daemon-reload
   systemctl --user enable vsct-restore
   loginctl enable-linger "\$USER"

3) Optional config — ~/.config/vsct/persist.conf:

   # sessions to leave alone (e.g. owned by a service that resumes itself)
   exclude = my-service-session
   # relaunch via a personal wrapper when an allowlisted env var matches:
   # cmdmap = CLAUDE_CONFIG_DIR : */.claude-alt : my-claude-alt : 2

Try it now:   $dest snapshot --force
Dry-run:      $dest restore --dry-run
Kill switch:  touch ~/.local/state/vsct/restore-disabled
──────────────────────────────────────────────────────────────────────────────
EOF
