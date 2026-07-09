[English](README.md) | [中文](README.zh-CN.md)

# vscode-tmux-picker

A tiny **pre-attach tmux session picker** for the VS Code integrated terminal.
Pure bash, zero dependencies: no fzf, no Go binary.

Open a terminal and, *before* it attaches to tmux, you get an in-terminal menu:
type a name to create a new session, or arrow-pick an existing one (with its
attached state and working directory shown). Every terminal runs *transparently*
in tmux, so what's running survives window reloads. It shines over
**Remote-SSH**, where the work lives on the remote, not your laptop: quit VS Code
or shut your laptop down, reconnect later from any machine, everything still
running. (Locally it's still a handy session picker.)

![demo](demo-en.gif)

The UI follows your system locale. Chinese locale → Chinese interface:

![demo zh](demo-zh.gif)

## Why

VS Code does not keep remote terminal processes alive across reconnects or
window reloads. The highest-voted, still-open request on the VS Code remote
backlog is [vscode-remote-release#3096][3096] (open for years). The usual
workaround is to run every integrated terminal *transparently* inside a **tmux**
session, so a window reload, SSH drop, or VS Code server restart doesn't kill
what's running. Reload the window, quit VS Code, shut your laptop down, reconnect
days later from a different machine, and your shells, builds, and REPLs are still
running on the server.

Once you do that, you need a way to say *which* tmux session a new terminal
attaches to. tmux's own `choose-tree` only works once you're already inside a
session; this tool moves that choice to the moment the terminal opens, and adds
type-to-create, with no extra dependency.

[3096]: https://github.com/microsoft/vscode-remote-release/issues/3096

## Features

- **Pick before attach**: the menu shows up in the TTY as the terminal opens.
- **Type to create**: row 0 is an input box with a movable block cursor
  (`←`/`→` to move, `Backspace`/`Delete` to edit). Empty = a disposable auto
  name `vsct-<pid>`.
- **Arrow-pick existing**: `↑`/`↓` through live sessions, each showing whether
  it is already attached and its current directory. Text you typed is kept if
  you arrow away and back.
- **`Esc`** drops to a plain shell (no tmux).
- **Localizable UI** with a small i18n table that follows the system locale.
  English and Chinese ship by default; adding a language is one copy-paste block
  (contributions welcome).
- **Zero dependencies**, ~190 lines of bash, with a safe fallback to a one-line
  prompt when there is no TTY, no sessions, or anything goes wrong, so a
  terminal can never fail to open.

## Requirements

- bash ≥ 4.3 and tmux ≥ 3.3 **on the machine where the terminals actually run**,
  i.e. the remote host in a Remote-SSH setup. Your local client OS does not
  matter (a macOS laptop driving a Linux remote is fine).
- A Linux VS Code integrated terminal (Remote-SSH, or local Linux). The
  persistence payoff is for **Remote-SSH**; on a local box it is still a session
  picker.

## Install

```sh
./install.sh
```

It copies `vsct-tmux-launch.sh` to `~/.local/bin/` and prints the VS Code
settings and recommended `~/.tmux.conf` snippets to merge. Or do it by hand:

1. Put `vsct-tmux-launch.sh` somewhere on the box and `chmod +x` it.
2. In VS Code **Remote (machine) settings** (or User settings) add a terminal
   profile that runs it:

   ```jsonc
   {
     "terminal.integrated.profiles.linux": {
       "tmux-tab": {
         "path": "/bin/bash",
         "args": ["-c", "exec $HOME/.local/bin/vsct-tmux-launch.sh"]
       }
     },
     "terminal.integrated.defaultProfile.linux": "tmux-tab",
     "terminal.integrated.tabs.title": "${sequence}",
     "terminal.integrated.automationProfile.linux": {
       "path": "/bin/bash",
       "args": ["-lc", "exec $SHELL -l"]
     }
   }
   ```

3. Run **Developer: Reload Window**, then open a new terminal.

> `automationProfile` keeps tasks / debuggers on a plain shell (they never see
> the menu). `tabs.title=${sequence}` makes the VS Code tab show the session
> name (the script emits it as the terminal title).

## Recommended tmux config (scroll / copy / paste)

The picker only chooses the session. For a good tmux experience (mouse-wheel
scrollback, drag-to-copy, right-click paste), add these to `~/.tmux.conf`:

```tmux
set -g mouse on
set -g set-clipboard on
set -g allow-passthrough on
set -g terminal-features 'xterm*:clipboard'
set -g focus-events on
set -g set-titles on
set -g set-titles-string '#S'
unbind -T root MouseDown3Pane          # hand right-click back to VS Code
```

plus one VS Code setting so right-click pastes:

```jsonc
"terminal.integrated.rightClickBehavior": "paste"
```

## Configuration

| env | default | meaning |
|---|---|---|
| `VSCT_PREFIX` | `vsct` | prefix for disposable auto-names `<prefix>-<pid>` |
| `VSCT_LANG`   | system locale | force the UI language (`en`, `zh`, …) |

The UI follows the system locale: a Chinese locale gets the Chinese interface,
**everything else (and any unrecognized `VSCT_LANG`) falls back to English**.
(`vsct` = **VSCode Terminal**, the prefix the transparent-tmux terminals use.)

## Session persistence across reboots (optional add-on)

tmux dies with the host, so a reboot normally wipes every session. The
`vsct-persist.py` add-on brings them back:

- a cron job snapshots the live sessions (names, windows/panes, cwd, and the
  command each pane runs) to `~/.local/state/vsct/snapshot.json` every 2 min;
- a systemd **user** unit recreates them **under the same names** at boot;
  the picker then attaches to the restored sessions as if nothing happened;
- panes that were running **Claude Code** (plain `claude` or wrapped in
  [`happy`](https://github.com/slopus/happy)) are relaunched with
  `--resume <session-id>`, so the *conversation* survives the reboot;
- any other long-running command is **pre-typed but not executed** (auto-rerunning
  arbitrary commands at boot is not a thing this tool will do), and plain
  shells just come back at their old cwd.

The Claude session id is recovered from, in order: the pane map maintained by
the optional [statusline hook](#statusline-integration-recommended-exact-ids-for-every-pane)
below (exact, survives `/clear`); `--resume` flags already in the process
tree; the actively-written transcript under `<config-dir>/projects/`, trusted
only when the pane is the sole id-less Claude in its config-dir+cwd (a lone
active transcript among same-cwd siblings could belong to any of them); the
previous snapshot (while pid+starttime match). If none of those pins an id,
the command is pre-typed with a bare `--resume`: Enter opens Claude's own
session picker. **It never guesses**: resuming the wrong conversation would be
worse than not resuming.

```bash
./install-persist.sh    # copies the script, prints the cron line + unit setup
```

Safety properties: restore only *creates* sessions (never kills or replaces);
`touch ~/.local/state/vsct/restore-disabled` disables it; disposable
`<prefix>-*` sessions are only persisted while a Claude-family process runs
inside; env capture is a strict allowlist (`CLAUDE_CONFIG_DIR` only; secrets
in wrapper environments are never read or stored); after a reboot, snapshots
are paused until restore has run, so a half-restored boot can't overwrite the
pre-reboot state.

Optional `~/.config/vsct/persist.conf`:

```ini
# sessions to leave alone (e.g. owned by a systemd service that resumes itself)
exclude = my-service-session
# relaunch via a personal wrapper function when an allowlisted env var matches
# (for wrappers that must re-source private env this tool refuses to capture):
cmdmap = CLAUDE_CONFIG_DIR : */.claude-alt : my-claude-alt : 2
```

### Statusline integration (recommended): exact ids for every pane

The argv/transcript heuristics cannot tell same-cwd sibling sessions apart,
and they never see a fresh session started without `--resume` (or one that
renewed its id with `/clear`). Claude Code's statusline can: on every refresh
it receives the current `session_id` on stdin, and it runs inside the pane, so
it knows `$TMUX_PANE`. Append this to your statusline script, after it prints
its line, and every pane gets an exact, always-current id:

```bash
# vsct: record pane -> session-id for vsct-persist.py (no secrets, silent on failure)
if [ -n "${TMUX_PANE:-}" ]; then
    vsid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    if [ -n "$vsid" ]; then
        vdir="$HOME/.local/state/vsct/pane-sid"
        { mkdir -p "$vdir" &&
          printf '{"pane":"%s","sid":"%s","ppid":%s,"ts":%s}\n' \
              "$TMUX_PANE" "$vsid" "${PPID:-0}" "$(date +%s)" > "$vdir/.tmp.$$" &&
          mv -f "$vdir/.tmp.$$" "$vdir/${TMUX_PANE#%}"; } 2>/dev/null || true
    fi
fi
```

Here `$input` is the JSON payload your statusline already reads from stdin
(`input=$(cat)`). If you have no statusline yet, a script containing just that
line plus the block above works; point `statusLine.command` at it in
`~/.claude/settings.json`. If you moved the state dir via `VSCT_STATE_DIR`,
adjust `vdir` to match.

The snapshot trusts a map entry only when it can prove the entry belongs to
the process currently in the pane (the writer's parent pid is that process or
a descendant, or the file was written after the process started), so stale
entries left by a pane's previous occupant are ignored. Entries idle for a
week are cleaned up automatically.

Known limits: sessions created in the last ≤2 min before an abrupt power loss
are lost; scrollback text is not restored (for Claude panes the conversation
itself comes back, which is the part that matters).

## Adding a language

UI strings live in associative-array catalogs near the top of the script. Copy
`MSG_en`, translate the values, name it `MSG_<code>`, and add a pattern to
`detect_lang()`. `{name}` in `[auto]` is replaced by the auto-name;
`[attached_pad]` must be spaces of the same display width as `[attached]`.

## How it works

The terminal profile runs `vsct-tmux-launch.sh`, which draws the menu to
**stderr**, reads keys from **stdin**, and echoes the chosen name on
**stdout**; the parent then `tmux new-session -A`s into it (attach-or-create),
preserving VS Code's shell-integration marks and tab title. `Esc` returns a
sentinel exit code so the parent `exec`s a plain shell instead.

## Limitations

- Many sessions can overflow a short terminal (the menu does not scroll yet).
- Interactive editing/rendering needs a real TTY; without one it falls back to a
  one-line prompt.
- Needs bash 4.3+ on the host that runs it. In Remote-SSH that is the **remote**,
  so a macOS client is fine; it only matters if you run the script on a local
  macOS box (bash 3.2 there; `brew install bash`).
- Only a reboot of the remote host itself ends a session (tmux dies with it),
  unless you enable the [persistence add-on](#session-persistence-across-reboots-optional-add-on).

## License

MIT &copy; guojx1998
