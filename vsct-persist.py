#!/usr/bin/env python3
# vsct-persist.py — optional session-persistence add-on for vscode-tmux-picker.
#
#   snapshot   Dump the live tmux sessions (names / windows / panes / cwd and
#              the command running in each pane) to a JSON state file. Meant to
#              run from cron every couple of minutes.
#   restore    After a reboot, recreate the snapshotted sessions under the same
#              names. Panes that were running Claude Code (plain `claude` or
#              wrapped in `happy`) are relaunched with `--resume <session-id>`
#              so the conversation continues where it left off. Anything else
#              is pre-typed into the pane but NOT executed.
#
# How the Claude session id is recovered, in order of trust:
#   pane     the pane -> session-id map written by a statusline hook (see
#            "Statusline integration" in the README): exact, survives /clear,
#            works for fresh sessions and same-cwd siblings. Trusted only if
#            it provably belongs to the process currently in the pane.
#   argv     any `--resume/--session-id <uuid>` in the pane's process tree —
#            covers every session that was itself started with --resume, which
#            after one restore cycle is all of them (steady state).
#   jsonl    the single actively-written (mtime < 10 min) transcript
#            `<uuid>.jsonl` under <config-dir>/projects/<munged-cwd>/ that is
#            not already claimed by another process's argv — only trusted when
#            this (config-dir, cwd) has exactly ONE id-less claude pane;
#            with siblings the lone active transcript could belong to any of
#            them and pinning it would resume the wrong conversation.
#   carried  the id recorded by a previous snapshot for the same pane while
#            (pid, starttime) are unchanged — keeps the id once the session
#            goes idle.
# If no id can be established the command is pre-typed with a trailing
# `--resume` and NO Enter: pressing Enter opens Claude Code's own session
# picker. The tool never guesses — resuming the wrong conversation is worse
# than not resuming.
#
# Guarantees:
#   * restore only CREATES sessions; existing ones are never killed/replaced.
#   * kill switch: `touch <state-dir>/restore-disabled` skips restore entirely.
#   * `<prefix>-*` disposable sessions (see VSCT_PREFIX in the picker) are
#     snapshotted only when a Claude-family process runs inside; a bare
#     throwaway shell is not worth resurrecting.
#   * fresh-boot guard: after a reboot, cron snapshots are refused until
#     restore has stamped the current boot id (or 30 min of uptime pass), so a
#     half-restored boot can never overwrite the pre-reboot state file.
#   * env capture is a strict allowlist (CLAUDE_CONFIG_DIR only) — tokens or
#     other secrets in a wrapper's environment are never read, never stored.
#
# Config (optional): ~/.config/vsct/persist.conf, `key = value` lines.
#   exclude = name1, name2      sessions to leave alone entirely (e.g. ones
#                               owned by a systemd service that resumes itself)
#   cmdmap  = VAR : glob : head [: skip-args]
#                               if the captured env var VAR matches glob,
#                               rebuild the command as `head <args[skip:]>`
#                               instead of the generic form. Use this when the
#                               pane was launched via a personal shell function
#                               that must re-source private env (tokens etc.)
#                               that this tool refuses to capture. Example:
#                               cmdmap = CLAUDE_CONFIG_DIR : */.claude-alt : my-claude-alt : 2
# Env: VSCT_PREFIX (same as the picker, default "vsct"),
#      VSCT_PERSIST_CONF (config path), VSCT_STATE_DIR (state dir).
#
# Wire-up (see install-persist.sh output and README "Session persistence"):
#   cron:     3-59/2 * * * * <path>/vsct-persist.py snapshot >> <state>/snapshot.log 2>&1
#   systemd:  vsct-restore.service (user) running `vsct-persist.py restore` at
#             boot; `loginctl enable-linger` so it starts without a login.

import json, os, re, subprocess, sys, time
from fnmatch import fnmatch

STATE_DIR   = os.path.expanduser(os.environ.get("VSCT_STATE_DIR", "~/.local/state/vsct"))
SNAP        = os.path.join(STATE_DIR, "snapshot.json")
SNAP_BAK    = os.path.join(STATE_DIR, "snapshot.json.bak")
BOOT_STAMP  = os.path.join(STATE_DIR, "restored-boot-id")
KILL_SWITCH = os.path.join(STATE_DIR, "restore-disabled")
LOG         = os.path.join(STATE_DIR, "snapshot.log")
CONF_PATH   = os.path.expanduser(os.environ.get("VSCT_PERSIST_CONF",
                                                "~/.config/vsct/persist.conf"))
PREFIX      = os.environ.get("VSCT_PREFIX", "vsct") + "-"
UUID_RE     = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHELLS      = {"bash", "-bash", "sh", "zsh", "-zsh", "fish"}
ENV_ALLOW   = ("CLAUDE_CONFIG_DIR",)   # strict allowlist; never widen to tokens
ACTIVE_WIN  = 600                      # a jsonl counts as "active" this long (s)
# happy (npm: happy, formerly happy-coder) wraps claude and passes --resume through
HAPPY_RE    = re.compile(r"/happy(-coder)?/(bin|dist)/[^/]+\.mjs$")

def load_conf():
    conf = {"exclude": set(), "cmdmap": []}
    try:
        lines = open(CONF_PATH).read().splitlines()
    except OSError:
        return conf
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        key, _, val = ln.partition("=")
        key, val = key.strip().lower(), val.strip()
        if key == "exclude":
            conf["exclude"] |= {s.strip() for s in val.split(",") if s.strip()}
        elif key == "cmdmap":
            p = [s.strip() for s in val.split(":")]
            if len(p) >= 3:
                conf["cmdmap"].append(dict(
                    var=p[0], glob=p[1], head=p[2],
                    skip=int(p[3]) if len(p) > 3 and p[3].isdigit() else 0))
    return conf

CONF = load_conf()

def sh(args):
    return subprocess.run(args, capture_output=True, text=True)

def tmux(args):
    return sh(["tmux"] + args)

# ---------- /proc helpers ----------
def proc_tree():
    """{ppid: [pid, ...]} for all live processes."""
    out = sh(["ps", "-eo", "pid=,ppid="]).stdout
    tree = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) == 2:
            tree.setdefault(int(f[1]), []).append(int(f[0]))
    return tree

def descendants(pid, tree):
    got, todo = [], [pid]
    while todo:
        p = todo.pop()
        for c in tree.get(p, []):
            got.append(c); todo.append(c)
    return got

def cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [t.decode("utf-8", "replace") for t in f.read().split(b"\0") if t]
    except OSError:
        return []

def starttime(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            rest = f.read().rsplit(")", 1)[1].split()
        return int(rest[19])           # field 22 of /proc/<pid>/stat
    except (OSError, IndexError, ValueError):
        return 0

def environ_allowed(pid):
    """Allowlisted env vars only — this tool must never touch secrets."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read().split(b"\0")
    except OSError:
        return {}
    out = {}
    for t in raw:
        s = t.decode("utf-8", "replace")
        for k in ENV_ALLOW:
            if s.startswith(k + "="):
                out[k] = s.split("=", 1)[1]
    return out

# ---------- command classification / id extraction ----------
def classify(argv):
    """(family, base_args)  family in {happy, claude, other}"""
    for i, tok in enumerate(argv):
        if HAPPY_RE.search(tok):
            return "happy", argv[i + 1:]
    a0 = argv[0] if argv else ""
    if os.path.basename(a0) == "claude" or "/claude/versions/" in a0:
        return "claude", argv[1:]
    return "other", argv

def extract_sid(argv):
    for i, tok in enumerate(argv):
        if tok in ("--resume", "--session-id") and i + 1 < len(argv) \
           and UUID_RE.match(argv[i + 1]):
            return argv[i + 1]
    return None

def strip_session_flags(args):
    """Drop old resume/continue/session-id flags; restore re-appends its own."""
    out, skip = [], False
    for i, tok in enumerate(args):
        if skip:
            skip = False; continue
        if tok in ("--resume", "--session-id"):
            if i + 1 < len(args) and UUID_RE.match(args[i + 1]):
                skip = True
            continue
        if tok in ("--continue", "-c", "--fork-session"):
            continue
        out.append(tok)
    return out

MAP_DIR = os.path.join(STATE_DIR, "pane-sid")

def pane_map_sid(pane_id, cand, tree):
    """Exact pane -> session-id mapping maintained by the statusline hook.
    Trusted only when it provably belongs to the process now in the pane:
    the writer's parent must be that process (or one of its descendants),
    or the file must have been written after the process started — a stale
    map from a previous occupant of the pane fails both checks."""
    if not pane_id:
        return None
    path = os.path.join(MAP_DIR, pane_id.lstrip("%"))
    try:
        with open(path) as f:
            m = json.load(f)
        mtime = os.path.getmtime(path)
    except (OSError, ValueError):
        return None
    sid = str(m.get("sid", ""))
    if m.get("pane") != pane_id or not UUID_RE.match(sid):
        return None
    if m.get("ppid") == cand or m.get("ppid") in descendants(cand, tree):
        return sid
    try:
        with open("/proc/uptime") as f:
            boot_epoch = time.time() - float(f.read().split()[0])
        hz = os.sysconf("SC_CLK_TCK") or 100
    except (OSError, ValueError):
        return None
    if mtime > boot_epoch + starttime(cand) / hz:
        return sid
    return None

def proj_dir(cwd, config_dir=None):
    base = config_dir or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects", re.sub(r"[^A-Za-z0-9]", "-", cwd))

def active_jsonls(cwd, config_dir=None):
    d, now, got = proj_dir(cwd, config_dir), time.time(), []
    try:
        for fn in os.listdir(d):
            sid, ext = os.path.splitext(fn)
            if ext == ".jsonl" and UUID_RE.match(sid):
                try:
                    if now - os.path.getmtime(os.path.join(d, fn)) < ACTIVE_WIN:
                        got.append(sid)
                except OSError:
                    pass
    except OSError:
        pass
    return got

# ---------- snapshot ----------
def take_snapshot(force=False):
    os.makedirs(STATE_DIR, exist_ok=True)
    # fresh-boot guard: don't clobber the pre-reboot state before restore ran
    boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
    stamped = os.path.exists(BOOT_STAMP) and open(BOOT_STAMP).read().strip() == boot_id
    with open("/proc/uptime") as f:
        up = float(f.read().split()[0])
    if not (stamped or up > 1800 or force):
        return 0                       # silently keep the previous snapshot
    r = tmux(["list-panes", "-a", "-F",
              "#{session_name}\t#{window_index}\t#{window_name}\t#{window_layout}"
              "\t#{pane_index}\t#{pane_current_path}\t#{pane_pid}\t#{pane_id}"])
    if r.returncode != 0:
        return 0                       # no tmux server -> nothing to record

    prev = {}
    try:
        with open(SNAP) as f:
            for s in json.load(f).get("sessions", []):
                for w in s["windows"]:
                    for p in w["panes"]:
                        prev[(s["name"], w["idx"], p["idx"])] = p
    except (OSError, ValueError, KeyError):
        pass

    tree = proc_tree()
    panes = []
    for line in r.stdout.splitlines():
        f = line.split("\t")
        if len(f) != 8:
            continue
        panes.append(dict(sess=f[0], widx=int(f[1]), wname=f[2], layout=f[3],
                          pidx=int(f[4]), cwd=f[5], pid=int(f[6]), pane_id=f[7]))

    # pass 1: session ids already claimed by some process's argv
    claimed = set()
    for p in panes:
        for d in [p["pid"]] + descendants(p["pid"], tree):
            s = extract_sid(cmdline(d))
            if s:
                claimed.add(s)

    # pass 2: what runs in each pane + ids provable from that pane's own argv
    sessions, pending, idless = {}, [], {}
    for p in panes:
        if p["sess"] in CONF["exclude"]:
            continue
        # what runs in the pane: the pane process itself if it isn't a shell,
        # else its newest non-shell child (the foreground command)
        cand = None
        own = cmdline(p["pid"])
        if own and os.path.basename(own[0]) not in SHELLS:
            cand = p["pid"]
        else:
            kids = [c for c in tree.get(p["pid"], [])
                    if (cl := cmdline(c)) and os.path.basename(cl[0]) not in SHELLS]
            if kids:
                cand = max(kids, key=starttime)
        rec = dict(idx=p["pidx"], cwd=p["cwd"], family="shell",
                   args=[], env={}, sid=None, sid_src="none", pid=None, start=None)
        if cand:
            argv = cmdline(cand)
            fam, args = classify(argv)
            rec.update(family=fam, pid=cand, start=starttime(cand))
            if fam == "other":
                rec["args"] = argv
            else:
                rec["args"] = strip_session_flags(args)
                rec["env"] = environ_allowed(cand)
                sid = pane_map_sid(p.get("pane_id"), cand, tree)
                if sid:
                    rec.update(sid=sid, sid_src="pane")
                    claimed.add(sid)
                if not rec["sid"]:
                    for d in [cand] + descendants(cand, tree):
                        sid = extract_sid(cmdline(d))
                        if sid:
                            rec.update(sid=sid, sid_src="argv")
                            break
                if not rec["sid"]:
                    key = (rec["env"].get("CLAUDE_CONFIG_DIR"), p["cwd"])
                    idless[key] = idless.get(key, 0) + 1
                    pending.append((p, rec, cand, key))
        sess = sessions.setdefault(p["sess"], {})
        win = sess.setdefault(p["widx"], dict(idx=p["widx"], name=p["wname"],
                                              layout=p["layout"], panes=[]))
        win["panes"].append(rec)

    # pass 3: id-less claude panes — transcript heuristic, then carry-over.
    # The lone active jsonl is only trustworthy when this (config-dir, cwd)
    # has exactly ONE id-less claude pane: with siblings it could belong to
    # any of them, and pinning it to whichever pane comes first would resume
    # the WRONG conversation after a reboot. On ambiguity fall back to the
    # carried id (process unchanged) or stay unpinned (pre-type only).
    for p, rec, cand, key in pending:
        if idless.get(key) == 1:
            un = [s for s in active_jsonls(p["cwd"], key[0]) if s not in claimed]
            if len(un) == 1:
                rec.update(sid=un[0], sid_src="jsonl")
                claimed.add(un[0])
        if not rec["sid"]:
            old = prev.get((p["sess"], p["widx"], p["pidx"]))
            if old and old.get("sid") and old.get("pid") == cand \
               and old.get("start") == starttime(cand):
                rec.update(sid=old["sid"], sid_src="carried")

    out = []
    for name, wins in sessions.items():
        has_claude = any(pn["family"] in ("claude", "happy")
                         for w in wins.values() for pn in w["panes"])
        if name.startswith(PREFIX) and not has_claude:
            continue                   # disposable shell-only session
        out.append(dict(name=name, windows=[wins[k] for k in sorted(wins)]))
    if not out:
        return 0                       # keep the previous snapshot
    data = dict(ts=int(time.time()), boot_id=boot_id, sessions=out)
    tmp = SNAP + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    if os.path.exists(SNAP):
        os.replace(SNAP, SNAP_BAK)
    os.replace(tmp, SNAP)
    _trim_log()
    try:                               # drop pane-sid entries idle for a week
        cutoff = time.time() - 7 * 86400
        for fn in os.listdir(MAP_DIR):
            fp = os.path.join(MAP_DIR, fn)
            if os.path.getmtime(fp) < cutoff:
                os.unlink(fp)
    except OSError:
        pass
    return 0

def _trim_log():
    try:
        if os.path.getsize(LOG) > 512 * 1024:
            with open(LOG) as f:
                tail = f.readlines()[-200:]
            with open(LOG, "w") as f:
                f.writelines(tail)
    except OSError:
        pass

# ---------- restore ----------
def q(tok):
    import shlex
    return shlex.quote(tok)

def build_cmd(p):
    """pane record -> (command line to type into the pane, auto-press-Enter?)"""
    fam = p["family"]
    if fam == "shell":
        return None, False
    if fam == "other":
        # never auto-run arbitrary commands at boot: pre-type only
        return " ".join(q(t) for t in p["args"]), False
    args, env = p["args"], p.get("env", {})
    head, prefix = {"claude": "claude", "happy": "happy"}[fam], ""
    for m in CONF["cmdmap"]:
        if m["var"] in env and fnmatch(env[m["var"]], m["glob"]):
            head, args, env = m["head"], args[m["skip"]:], {}
            break
    if env:
        # allowlisted, non-secret vars only (paths); quoted for the shell
        prefix = " ".join(f"{k}={q(v)}" for k, v in sorted(env.items())) + " "
    base = prefix + " ".join([head] + [q(t) for t in args])
    if p.get("sid"):
        return f"{base} --resume {p['sid']}", True
    return f"{base} --resume", False   # Enter opens Claude's own session picker

def restore(dry=False):
    os.makedirs(STATE_DIR, exist_ok=True)
    boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
    lines = []
    try:
        try:
            with open(SNAP) as f:
                data = json.load(f)
        except (OSError, ValueError):
            with open(SNAP_BAK) as f:
                data = json.load(f)
    except (OSError, ValueError):
        print("no snapshot")
        _stamp(boot_id, dry)
        return 0
    if os.path.exists(KILL_SWITCH):
        print("disabled (restore-disabled present)")
        _stamp(boot_id, dry)
        return 0

    age_h = (time.time() - data.get("ts", 0)) / 3600
    existing = set()
    r = tmux(["list-sessions", "-F", "#{session_name}"])
    if r.returncode == 0:
        existing = set(r.stdout.split())

    def run(args):
        if dry:
            print("DRY:", " ".join(q(a) for a in args))
            return True
        return tmux(args).returncode == 0

    for s in data.get("sessions", []):
        name = s["name"]
        if name in CONF["exclude"]:
            continue
        if name in existing:
            lines.append(f"{name}: exists, skipped")
            continue
        wins = s["windows"]
        first = wins[0]["panes"][0]
        if not run(["new-session", "-d", "-s", name, "-c", first["cwd"],
                    "-x", "220", "-y", "50"]):
            lines.append(f"{name}: create FAILED")
            continue
        run(["set", "-t", name, "status", "off"])   # match the picker's look
        n_res = n_pre = 0
        for wi, w in enumerate(wins):
            tgt = f"{name}:{w['idx']}"
            if wi > 0:
                run(["new-window", "-d", "-t", tgt, "-n", w["name"],
                     "-c", w["panes"][0]["cwd"]])
            for pi, p in enumerate(w["panes"]):
                if pi > 0:
                    run(["split-window", "-d", "-t", tgt, "-c", p["cwd"]])
            if len(w["panes"]) > 1 and w.get("layout"):
                run(["select-layout", "-t", tgt, w["layout"]])
            if not dry:
                time.sleep(0.4)                     # let the shell read its rc
            for p in w["panes"]:
                cmd, auto = build_cmd(p)
                if not cmd:
                    continue
                ptgt = f"{tgt}.{p['idx']}"
                run(["send-keys", "-t", ptgt, "-l", cmd])
                if auto:
                    run(["send-keys", "-t", ptgt, "Enter"])
                    n_res += 1
                else:
                    n_pre += 1
        tag = []
        if n_res:
            tag.append(f"resumed x{n_res}")
        if n_pre:
            tag.append(f"pretyped x{n_pre} (press Enter inside)")
        lines.append(f"{name}: {', '.join(tag) if tag else 'shell'}")

    _stamp(boot_id, dry)
    print(f"snapshot {age_h:.1f}h old" if age_h < 48 else
          f"snapshot {age_h/24:.1f}d old")
    for ln in lines:
        print(ln)
    return 0

def _stamp(boot_id, dry=False):
    # always stamp: unlocks cron snapshots for this boot (see fresh-boot guard)
    if not dry:
        with open(BOOT_STAMP, "w") as f:
            f.write(boot_id)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "snapshot":
        sys.exit(take_snapshot(force="--force" in a))
    if a and a[0] == "restore":
        sys.exit(restore(dry="--dry-run" in a))
    print("usage: vsct-persist.py snapshot [--force] | restore [--dry-run]",
          file=sys.stderr)
    sys.exit(2)
