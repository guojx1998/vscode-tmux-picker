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
- **双语界面**，跟随系统 locale（内置中 / 英，可轻松扩展到更多语言）。
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

## 加一种语言

界面字符串以关联数组目录的形式放在脚本顶部。复制 `MSG_en`、翻译它的值、命名为 `MSG_<code>`，再在 `detect_lang()` 里加一条匹配即可。`[auto]` 里的 `{name}` 会被替换成自动名；`[attached_pad]` 必须是与 `[attached]` 等显示宽度的空格。

## 工作原理

终端 profile 运行 `vsct-tmux-launch.sh`：它把菜单画到 **stderr**、从 **stdin** 读键、把选中的名字打到 **stdout**；父进程随后 `tmux new-session -A` 接入它（有就接、没有就建），并保住 VS Code 的 shell 集成标记与 tab 标题。`Esc` 返回一个哨兵退出码，父进程据此 `exec` 一个普通 shell。

## 限制

- 会话很多时可能撑出短终端的可视区（菜单暂不滚动）。
- 交互编辑 / 渲染需要真 TTY；没有时回退到单行提示。
- 需要**跑它的那台机器**有 bash 4.3+。Remote-SSH 下那是**远端**，所以 macOS 客户端没问题；只有当你在本地 macOS（自带 bash 3.2）上跑它才需 `brew install bash`。
- 只有远端主机自己重启才会结束会话（tmux 随之消失）。

## 许可

MIT &copy; guojx1998
