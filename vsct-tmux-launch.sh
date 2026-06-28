#!/bin/bash
# vsct-tmux-launch.sh — a "pre-attach" tmux session picker for the VS Code
# integrated terminal. Pure bash, no fzf / no external dependencies.
#
# Wire it into VS Code's terminal profile so that opening an integrated terminal
# shows an in-TTY menu *before* attaching to tmux:
#   * type a name   row 0 becomes "<new>: <name>"; ←→ move a block cursor,
#                   Backspace/Delete edit, deleting to empty -> auto name
#   * up / down     move between the input row and the existing sessions (you can
#                   still ↑↓ away after typing; the typed name is then ignored)
#   * Enter         input row  -> use the typed name (empty = disposable auto name
#                   "<prefix>-<pid>");  a session row -> attach to that session
#   * Esc           drop to a plain shell (no tmux)
# With no TTY / no existing sessions / on any error it falls back to a one-line
# prompt, so a terminal can never fail to open.
#
# Requires bash >= 4.3 (associative arrays + namerefs, for the i18n table).
# Env config:
#   VSCT_PREFIX      auto-name prefix (default "vsct")
#   VSCT_LANG        force a UI language code (e.g. en, zh); default = system locale
#   VSCT_FORCE_MENU  =1 forces the menu even without a TTY (for testing)
#
# Hard-won gotchas (do not re-break these):
#   * This script runs as  s="$(pick_session)"  so its stdout (fd 1) is ALWAYS a
#     pipe. Never use [ -t 1 ] to detect "interactive" — it is always false here
#     and the menu would never appear. The menu reads keys from stdin (fd 0) and
#     draws to stderr (fd 2); only the chosen name goes to stdout. Gate on fd0+fd2.
#   * $$ here is this process's PID — unique and never seen by VS Code's settings
#     parser, so it is safe (a literal $$ inside settings.json "args" gets folded
#     by VS Code into a single '$', which would collide every unnamed terminal).
#   * tmux's list-sessions -F does not echo raw control bytes verbatim, so fields
#     are delimited with ':' (tmux forbids ':' in session names, turning it into
#     '_'). The session name is the LAST field, so any ':' inside a path stays in
#     the path, not the name.

# --- i18n -------------------------------------------------------------------
# Add a language: copy MSG_en, translate the values, name it MSG_<code>, and add
# a pattern to detect_lang(). Force one with VSCT_LANG=<code>.
#   {name}          in [auto] is replaced by the auto-name.
#   [attached_pad]  must be spaces of the SAME display width as [attached]; it
#                   pads detached rows so the path column lines up.
declare -A MSG_en=(
  [hint]=" type = new tmux session · ↑↓ pick existing · ←→ move cursor · Enter confirm · Esc = plain shell"
  [auto]="auto name ({name})  · Enter to use (disposable)"
  [new]="new / attach: "
  [attached]="·attached"
  [attached_pad]="         "
  [prompt]="tmux name (empty = auto): "
)
declare -A MSG_zh=(
  [hint]=" 输名字新建 tmux 会话 · ↑↓ 选已有 · ←→ 移光标 · Enter 确认 · Esc 退普通 shell"
  [auto]="自动名 ({name})  · 回车即用 (用完即弃)"
  [new]="新建并接入: "
  [attached]="·已连"
  [attached_pad]="     "
  [prompt]="tmux name (empty = auto): "
)

detect_lang() {
  # Echo a language code that has a matching MSG_<code> table above.
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    zh[-_]*|zh) printf zh ;;
    *)          printf en ;;
  esac
}

PREFIX="${VSCT_PREFIX:-vsct}"
AUTO="${PREFIX}-$$"

# Select the catalog (unknown VSCT_LANG -> English) and flatten it to plain
# globals so the helper functions need not rely on nameref-in-function behaviour.
_lang="${VSCT_LANG:-$(detect_lang)}"
_lang="${_lang//[^A-Za-z0-9_]/}"                 # sanitize for use in a var name
declare -n _CAT="MSG_${_lang}" 2>/dev/null
[ "${#_CAT[@]}" -gt 0 ] 2>/dev/null || declare -n _CAT=MSG_en
HINT="${_CAT[hint]}"
_a="${_CAT[auto]}"; LBL_AUTO="${_a/\{name\}/$AUTO}"
LBL_NEW="${_CAT[new]}"
MARK_ATT="${_CAT[attached]}"
MARK_PAD="${_CAT[attached_pad]}"
PROMPT="${_CAT[prompt]}"
unset -n _CAT 2>/dev/null; unset _a _lang

# --- one-line fallback (no TTY / no sessions / error) -----------------------
classic_read() {
  local r
  read -rp "$PROMPT" r
  printf '%s' "${r:-$AUTO}"
}

# --- interactive picker -----------------------------------------------------
# Echoes the chosen session name on stdout. Returns 2 to mean "Esc -> plain shell".
pick_session() {
  # Gate on fd0 (read keys) + fd2 (draw); fd1 is the capturing pipe, never a tty.
  { [ -t 0 ] && [ -t 2 ]; } || [ -n "${VSCT_FORCE_MENU:-}" ] || { classic_read; return; }

  # Collect existing sessions, named ones first and "<prefix>-*" throwaways last.
  # Format "attached:path:name" with name LAST (see header note about ':').
  local nn=() nl=() tn=() tl=() line att path name lbl mark
  while IFS= read -r line; do
    att=${line%%:*}; line=${line#*:}
    name=${line##*:}; path=${line%:*}
    [ -z "$name" ] && continue
    [ "$att" = 1 ] && mark="$MARK_ATT" || mark="$MARK_PAD"
    lbl="$(printf '%-20s' "$name") $mark  $path"
    if [[ $name == "$PREFIX"-* ]]; then tn+=("$name"); tl+=("$lbl")
    else                                nn+=("$name"); nl+=("$lbl"); fi
  done < <(tmux list-sessions -F '#{?session_attached,1,0}:#{pane_current_path}:#{session_name}' 2>/dev/null)

  # Nothing to pick from -> one-line prompt (still lets you type a new name).
  if [ $(( ${#nn[@]} + ${#tn[@]} )) -eq 0 ]; then classic_read; return; fi

  # Row 0 is the input box; the rest are existing sessions (named, then throwaway).
  local opt_name=("$AUTO" "${nn[@]}" "${tn[@]}")
  local opt_label=("$LBL_AUTO" "${nl[@]}" "${tl[@]}")

  # State: query = typed new name, cpos = text cursor within query, sel =
  # highlighted row. They coexist: typing edits row 0 and focuses it, ↑↓ move
  # sel, Enter commits based on sel. Redraw uses DECSC/DECRC (\e7/\e8) + \e[J so
  # a wrapped long path cannot misalign the redraw.
  # query only ever receives printable ASCII ([[:print:]]), so ${query:n:1} char
  # slicing stays safe (multibyte names never reach here).
  local N=${#opt_name[@]} sel=0 key k2 k3 k4 query="" cpos=0
  printf '\e7' >&2                                    # save cursor at menu top
  draw_menu() {
    printf '%s\n' "$HINT" >&2
    local i txt b c a
    for ((i=0;i<N;i++)); do
      if [ "$i" -eq 0 ] && [ -n "$query" ]; then
        if [ "$sel" -eq 0 ]; then                     # focused input: block cursor at cpos
          b="${query:0:cpos}"; c="${query:cpos:1}"; a="${query:cpos+1}"; [ -z "$c" ] && c=' '
          printf ' ▶ %s%s\e[7m%s\e[0m%s\n' "$LBL_NEW" "$b" "$c" "$a" >&2
        else
          printf '   %s%s\n' "$LBL_NEW" "$query" >&2
        fi
      else
        [ "$i" -eq 0 ] && txt="$LBL_AUTO" || txt="${opt_label[i]}"
        if [ "$i" -eq "$sel" ]; then printf '\e[7m ▶ %s\e[0m\n' "$txt" >&2
        else                         printf '   %s\n' "$txt" >&2; fi
      fi
    done
  }
  draw_menu
  while true; do
    IFS= read -rsn1 key
    case $key in
      $'\x1b')  # ESC: bare Esc (exit) or an arrow / Delete sequence. Timeout = bare.
        read -rsn1 -t 0.3 k2
        if [ -z "$k2" ]; then
          printf '\e8\e[J' >&2; return 2              # bare Esc -> caller drops to a shell
        elif [ "$k2" = '[' ] || [ "$k2" = 'O' ]; then
          read -rsn1 -t 0.3 k3
          case $k3 in
            A) ((sel>0))           && ((sel--)) ;;     # up
            B) ((sel<N-1))         && ((sel++)) ;;     # down
            C) ((cpos<${#query}))  && ((cpos++)) ;;    # right
            D) ((cpos>0))          && ((cpos--)) ;;    # left
            3) read -rsn1 -t 0.3 k4                     # Delete (ESC[3~): drop char at cpos
               [ "$k4" = '~' ] && query="${query:0:cpos}${query:cpos+1}" ;;
          esac
        fi ;;
      '')  # Enter: row 0 -> typed name (empty = auto); other -> attach that session
        printf '\e8\e[J' >&2
        if [ "$sel" -eq 0 ]; then printf '%s' "${query:-$AUTO}"
        else                      printf '%s' "${opt_name[sel]}"; fi
        return ;;
      $'\x7f'|$'\x08')  # Backspace: delete char before cpos (empty -> auto name)
        if [ "$cpos" -gt 0 ]; then query="${query:0:cpos-1}${query:cpos}"; ((cpos--)); fi
        sel=0 ;;
      [[:print:]])  # printable: insert at cpos, advance the cursor, focus row 0
        query="${query:0:cpos}$key${query:cpos}"; ((cpos++)); sel=0 ;;
    esac
    printf '\e8\e[J' >&2                               # restore to menu top, clear, redraw
    draw_menu
  done
}

s="$(pick_session)"; rc=$?
[ "$rc" -eq 2 ] && exec "${SHELL:-/bin/bash}" -l       # Esc -> plain shell, no tmux
[ -z "$s" ] && s="$AUTO"

# Hand off to tmux:
#   1. OSC 633 marks so VS Code keeps its command decorations / cwd tracking
printf '\e]633;A\a\e]633;B\a\e]633;E;tmux new-session -A -s %s\a\e]633;C\a' "$s"
#   2. OSC 2 sets the session name as the terminal title -> VS Code tab name
printf '\e]2;%s\a' "$s"
#   3. inject VSCODE_* vars so `code <file>` works from inside tmux too
vars=(TERM_PROGRAM TERM_PROGRAM_VERSION VSCODE_IPC_HOOK_CLI VSCODE_IPC_HOOK VSCODE_PID VSCODE_CWD VSCODE_NLS_CONFIG VSCODE_GIT_IPC_HANDLE VSCODE_INJECTION VSCODE_SHELL_INTEGRATION)
eargs=(); for v in "${vars[@]}"; do eargs+=( -e "$v=${!v-}" ); done
#   4. attach if it exists else create, hide tmux's own status bar, attach
tmux new-session -dA -s "$s" -c "$PWD" "${eargs[@]}"
tmux set -t "$s" status off
exec tmux attach -t "$s"
