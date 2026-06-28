#!/bin/bash
# Installer for vscode-tmux-picker.
# Copies the launcher to ~/.local/bin and prints the VS Code settings + the
# recommended ~/.tmux.conf snippets to merge by hand (we don't auto-edit your
# settings.json — it is JSONC and merging blindly is risky).
#
# Override the destination with VSCT_DEST=/some/path/vsct-tmux-launch.sh
set -e

here="$(cd "$(dirname "$0")" && pwd)"
src="$here/vsct-tmux-launch.sh"
dest="${VSCT_DEST:-$HOME/.local/bin/vsct-tmux-launch.sh}"

mkdir -p "$(dirname "$dest")"
cp "$src" "$dest"
chmod +x "$dest"
echo "installed: $dest"

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
1) VS Code settings  (Remote machine settings, or User settings)
   Merge into "terminal.integrated.*":

  "terminal.integrated.profiles.linux": {
    "tmux-tab": { "path": "/bin/bash", "args": ["-c", "exec $dest"] }
  },
  "terminal.integrated.defaultProfile.linux": "tmux-tab",
  "terminal.integrated.tabs.title": "\${sequence}",
  "terminal.integrated.automationProfile.linux": {
    "path": "/bin/bash", "args": ["-lc", "exec \$SHELL -l"]
  }

2) Recommended ~/.tmux.conf  (scroll / copy / paste)

  set -g mouse on
  set -g set-clipboard on
  set -g allow-passthrough on
  set -g terminal-features 'xterm*:clipboard'
  set -g focus-events on
  set -g set-titles on
  set -g set-titles-string '#S'
  unbind -T root MouseDown3Pane

3) VS Code: right-click = paste

  "terminal.integrated.rightClickBehavior": "paste"

Then run  "Developer: Reload Window"  and open a new terminal.
──────────────────────────────────────────────────────────────────────────────
EOF
