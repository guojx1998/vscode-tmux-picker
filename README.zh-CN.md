[English](README.md) | 中文

# vscode-tmux-picker

VS Code 集成终端的 **attach 前 tmux 会话选择器**。纯 bash，零依赖：不要 fzf，不要 Go 二进制。

开一个终端，在它接入 tmux **之前**就弹出一个终端内菜单：输名字新建会话，或用方向键挑一个已有的（显示它是否已连、当前目录）。每个终端都**透明地**跑在 tmux 里，所以正在跑的东西在重载窗口后不中断。它在 **Remote-SSH** 下最有用：活儿在远端、不在你笔记本上，所以你可以退出 VS Code、甚至关掉笔记本，过后换任意机器重连，东西都还在跑。（本地用它依然是个好用的会话选择器。）

![演示](demo-zh.gif)

界面跟随系统语言，英文 locale 则是英文界面：

![demo en](demo-en.gif)

## 为什么

VS Code 不会让远程终端进程在断连或重载窗口后存活。这是 VS Code 远程仓库里**票数最高、开了 6 年仍未做**的需求 [vscode-remote-release#3096][3096]。通行的兜底是把每个集成终端**透明地**跑在一个 **tmux** 会话里：这样重载窗口、SSH 掉线、VS Code 服务进程重启都不会杀掉正在跑的东西。重载窗口、退出 VS Code、关掉笔记本，过几天换一台机器重连，你的 shell、编译、REPL 还在服务器上跑着。

一旦这么做，你就要决定新终端该接入**哪个** tmux 会话。tmux 自带的 `choose-tree` 只能在你**已经进了**会话之后才用；本工具把这个选择提前到终端打开那一刻，还加了「输入即新建」，零额外依赖。

[3096]: https://github.com/microsoft/vscode-remote-release/issues/3096

## 特性

- **接入前就选**：终端一打开，菜单就在 TTY 里弹出。
- **输入即新建**：第 0 项是个输入框，带可移动的反显块光标（`←`/`→` 移动，`Backspace`/`Delete` 编辑）。留空 = 用完即弃的自动名 `vsct-<pid>`。
- **方向键选已有**：`↑`/`↓` 在活动会话间移动，每行显示它是否已被连接、以及当前目录。输了一半名字再用箭头切走，输入的内容会保留。
- **`Esc`** 退到普通 shell（不进 tmux）。
- **可本地化界面**，内置一个跟随系统 locale 的小 i18n 框架：默认中 / 英两种语言，加一种只需复制一个块（欢迎贡献）。
- **零依赖**，约 190 行 bash，并在没有 TTY、没有会话或任何出错时安全回退到单行提示，所以终端永远不会开不出来。

## 要求

- **跑脚本的那台机器**上需要 bash ≥ 4.3、tmux ≥ 3.3，也就是 Remote-SSH 场景下的**远端**主机。你本地客户端是什么系统无所谓（macOS 笔记本连 Linux 远端完全没问题）。
- Linux 上的 VS Code 集成终端（Remote-SSH，或本地 Linux）。持久化收益面向 **Remote-SSH**；本地用它依然是个会话选择器。

## 安装

```sh
./install.sh
```

它会把 `vsct-tmux-launch.sh` 拷到 `~/.local/bin/`，并打印要合并的 VS Code 设置与推荐的 `~/.tmux.conf` 片段。也可以手动来：

1. 把 `vsct-tmux-launch.sh` 放到机器上某处并 `chmod +x`。
2. 在 VS Code **Remote (machine) 设置**（或 User 设置）里加一个跑它的终端 profile：

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

3. 运行 **Developer: Reload Window**，然后开一个新终端。

> `automationProfile` 让任务 / 调试器走普通 shell（它们看不到菜单）。`tabs.title=${sequence}` 让 VS Code 的 tab 显示会话名（脚本会把它作为终端标题发出去）。

## 推荐 tmux 配置（滚轮 / 复制 / 粘贴）

选择器只负责挑会话。要让 tmux 体验顺手（滚轮翻历史、拖选复制、右键粘贴），把这些加进 `~/.tmux.conf`：

```tmux
set -g mouse on
set -g set-clipboard on
set -g allow-passthrough on
set -g terminal-features 'xterm*:clipboard'
set -g focus-events on
set -g set-titles on
set -g set-titles-string '#S'
unbind -T root MouseDown3Pane          # 把右键还给 VS Code

# 键盘回滚：PgUp 免 prefix 直接进滚动模式；PgUp/PgDn 翻页，Home/End 跳顶/回底，
# 翻回最底自动退出。vim/less/htop 等全屏程序内 PgUp 原样透传给程序。
bind -n PPage if -F '#{alternate_on}' 'send-keys PPage' 'copy-mode -eu'
bind -T copy-mode    Home send -X history-top
bind -T copy-mode    End  send -X cancel
bind -T copy-mode-vi Home send -X history-top
bind -T copy-mode-vi End  send -X cancel
```

再加一条 VS Code 设置，让右键粘贴：

```jsonc
"terminal.integrated.rightClickBehavior": "paste"
```

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `VSCT_PREFIX` | `vsct` | 用完即弃自动名的前缀 `<prefix>-<pid>` |
| `VSCT_LANG`   | 系统 locale | 强制界面语言（`en`、`zh`…） |

界面跟随系统 locale：中文 locale 出中文界面，**其它语言（以及无法识别的 `VSCT_LANG`）一律回退英文**。
（`vsct` = **VSCode Terminal**，即透明 tmux 终端用的前缀。）

## 跨重启会话持久化（可选附加件）

tmux 随主机一起死，重启一次会话全没。`vsct-persist.py` 附加件把它们带回来：

- cron 每 2 分钟把活着的会话（名字、窗口/pane、cwd、每个 pane 里跑的命令）快照到
  `~/.local/state/vsct/snapshot.json`；
- 开机时 systemd **user** 单元**同名重建**这些会话，之后 picker 一如既往地接入，
  像什么都没发生过；
- 之前跑着 **Claude Code**（裸 `claude` 或
  [`happy`](https://github.com/slopus/happy) 包裹）的 pane 会自动带
  `--resume <会话id>` 重新拉起，**对话本身**跨过这次重启；
- 其它长跑命令**只预填不执行**（开机自动重跑任意命令这种事本工具不干），
  普通 shell 回到原 cwd。

Claude 会话 id 按优先级恢复自：下文可选 [statusline 挂钩](#statusline-集成推荐每个-pane-拿到精确-id)
维护的 pane 映射（精确，`/clear` 换 id 也跟得上）；进程树里已有的 `--resume`
参数；`<config-dir>/projects/` 下的活跃 transcript，且仅当该 config-dir+cwd
下**恰好一个**没有 id 的 Claude pane 时才采信（同 cwd 开着多个会话时，唯一
活跃的 transcript 可能属于其中任何一个）；上一份快照（pid+starttime 未变时）。
都钉不住时，命令只预填一个裸 `--resume`：回车即进 Claude 自带的会话选择器。
**它从不猜**：resume 错对话比不 resume 更糟。

```bash
./install-persist.sh    # 拷贝脚本，打印 cron 行 + unit 装法
```

安全性质：restore 只*新建*会话（绝不杀/覆盖已有的）；
`touch ~/.local/state/vsct/restore-disabled` 一键停用；`<prefix>-*` 用完即弃
会话只在里面跑着 Claude 族进程时才持久化；env 捕获是严格白名单
（仅 `CLAUDE_CONFIG_DIR`，wrapper 环境里的 secret 永远不读不存）；
重启后快照会暂停，直到 restore 跑过，半恢复状态不可能覆盖重启前的快照。

可选配置 `~/.config/vsct/persist.conf`：

```ini
# 不碰的会话（例如由某个 systemd service 自己管理/自己 resume 的）
exclude = my-service-session
# 白名单 env 命中 glob 时改用个人 wrapper 重建
# （适用于必须自己 source 私有 env 的 wrapper，那些 env 本工具拒绝捕获）：
cmdmap = CLAUDE_CONFIG_DIR : */.claude-alt : my-claude-alt : 2
```

### statusline 集成（推荐）：每个 pane 拿到精确 id

argv/transcript 启发式分不清同 cwd 的兄弟会话，也看不见没带 `--resume` 新起
（或用 `/clear` 换过 id）的会话。Claude Code 的 statusline 可以：每次刷新它
都从 stdin 收到当前 `session_id`，而且它就跑在 pane 里，知道 `$TMUX_PANE`。
把下面这段追加到你的 statusline 脚本末尾（输出状态行之后），每个 pane 就有了
精确且始终最新的 id：

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

其中 `$input` 就是你的 statusline 已经从 stdin 读进来的 JSON
（`input=$(cat)`）。还没有 statusline 的话，一个只含这一行加上面代码块的脚本
即可，在 `~/.claude/settings.json` 里把 `statusLine.command` 指过去。若用
`VSCT_STATE_DIR` 挪过状态目录，`vdir` 同步改。

快照只在能证明映射属于 pane 里当前进程时才采信（写入者的父 pid 是该进程或其
后代，或文件写于该进程启动之后），pane 前任留下的陈旧映射会被忽略。一周没
更新的映射条目自动清理。

已知边界：突然断电前最后 ≤2 分钟新建的会话会丢；scrollback 文本不恢复
（Claude pane 的对话本身会回来，那才是要紧的部分）。

## 加一种语言

界面字符串以关联数组目录的形式放在脚本顶部。复制 `MSG_en`、翻译它的值、命名为 `MSG_<code>`，再在 `detect_lang()` 里加一条匹配即可。`[auto]` 里的 `{name}` 会被替换成自动名；`[attached_pad]` 必须是与 `[attached]` 等显示宽度的空格。

## 工作原理

终端 profile 运行 `vsct-tmux-launch.sh`：它把菜单画到 **stderr**、从 **stdin** 读键、把选中的名字打到 **stdout**；父进程随后 `tmux new-session -A` 接入它（有就接、没有就建），并保住 VS Code 的 shell 集成标记与 tab 标题。`Esc` 返回一个哨兵退出码，父进程据此 `exec` 一个普通 shell。

## 限制

- 会话很多时可能撑出短终端的可视区（菜单暂不滚动）。
- 交互编辑 / 渲染需要真 TTY；没有时回退到单行提示。
- 需要**跑它的那台机器**有 bash 4.3+。Remote-SSH 下那是**远端**，所以 macOS 客户端没问题；只有当你在本地 macOS（自带 bash 3.2）上跑它才需 `brew install bash`。
- 只有远端主机自己重启才会结束会话（tmux 随之消失），除非启用[持久化附加件](#跨重启会话持久化可选附加件)。

## 许可

MIT &copy; guojx1998
