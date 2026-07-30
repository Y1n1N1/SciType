# SciType

SciType 0.6.0 是一个面向中文用户的 Windows 本地理科符号快捷输入项目。它允许
用户在普通输入框中通过斜杠命令输入 Unicode 符号和简单公式片段。

当前示例包括：

- `/fi` → `φ`
- `/jdz` → `||`，光标位于两条竖线之间
- `/jf` → `∫dx`，光标位于 `∫` 与 `d` 之间
- `/gh` → `√()`，光标位于括号内
- V0.5a 实验：`/fs` → `()/()`，两次 `Tab` 依次跳到分母和表达式末尾

这些缩写只是随包提供的兼容默认示例，不是 SciType 规定的唯一或官方标准。

## 当前进度

### V0.1：单命令解析

- 从 JSON 包资源加载并严格校验数据；
- `parse_text()` 只解析一个完整命令；
- 已知命令返回输出模板，未知命令原样返回；
- 包资源加载与当前工作目录无关。

输入 `这里有/xw` 不会扫描句中命令，这是有意的解析边界。

### V0.2a：输入状态机

- `NORMAL` 和 `SYMBOL` 两种状态；
- `/` 进入临时符号模式；
- `Space` 或 `Enter` 确认；
- `Esc` 取消，`Backspace` 编辑；
- 未支持的可打印字符会恢复已经拦截的原文，不会静默吞字。

### V0.2b：Windows 全局输入

- `WH_KEYBOARD_LL` 负责全局监听和选择性拦截；
- Unicode 文本通过 `SendInput` 插入；
- 命中绑定时确认用 `Enter` 的按下与释放都会被消费；replacement 内部
  换行单独注入为带 SciType 标记的 Enter，不会与确认键混淆；
- `Ctrl + Alt + Q` 安全退出；
- 程序注入事件绕过状态机，避免递归触发；
- 普通输入内容不会被记录或打印。

### V0.2c：单光标模板

- 模板最多包含一个 `${cursor}`；
- 插入前删除占位符；
- 插入后按占位符右侧字符数发送左方向键；
- 文本和方向键共用递归保护；
- 不使用鼠标定位。

例如，`√(${cursor})` 会插入 `√()`，再向左移动一次。

### V0.3a：高频符号与一键启动

- 增加高频关系、运算、集合、逻辑、常数和部分希腊字母；
- 根号默认模板由 `√${cursor}` 调整为 `√(${cursor})`；
- 增加当前用户范围的 Windows named mutex 单实例保护；
- 增加 `%LOCALAPPDATA%\SciType\scitype.log` 轮转日志；
- 增加桌面快捷方式创建、删除和前台排错脚本；
- 使用 `pythonw.exe` 双击启动时，致命错误会写入日志并显示消息框。

### V0.4a：Windows 发布包

- 新增正式入口 `scitype.app`，开发入口 `scitype.windows_demo` 作为兼容
  包装继续可用；
- 使用 PyInstaller 6.21.0 构建 Windows x64 `onedir` 发布包；
- `SciType.exe` 默认不显示控制台，普通用户无需预装 Python；
- JSON 词库和 LICENSE 随冻结程序分发，启动 Hook 前可执行只读资源自检；
- 增加可复用构建脚本、发布目录与 ZIP 验证、Windows 版本资源和 SHA-256
  哈希；
- 不启用 UPX，当前不使用自定义图标，也没有数字签名。

### V0.5a：基础分式 Tab 跳转实验

- `/fs` 经现有单光标渲染插入 `()/()`，初始光标位于第一个括号内；
- 分式会话独立于普通斜杠命令状态，只保存固定两步和前台窗口句柄；
- 第一次 `Tab` 被消费并向右移动 3 格，第二次被消费并向右移动 1 格；
- 第二次跳转后会话立即结束，第三次 `Tab` 恢复目标程序原本行为；
- `Esc`、导航键、前台窗口变化或鼠标点击会安全取消会话，但不删除文本；
- 普通字符和 `Backspace` 不会取消会话；
- `Ctrl + Alt + Q` 退出前会清理会话。

这是固定分式的最小实验。V0.6 发布包继续包含该功能，但没有通用多占位符、
嵌套模板、`Shift+Tab` 或结构检查。

### V0.5b：用户自定义 A→B 绑定底层

- 从 `%LOCALAPPDATA%\SciType\user_bindings.json` 读取可选的
  `trigger → replacement` 用户绑定；
- 配置使用带 `schema_version` 的对象结构，每项包含 `enabled`；
- 用户文件与包内符号目录、默认绑定分离，程序升级不会改写它；
- 启用的同名用户 trigger 覆盖默认示例，停用的同名 trigger 屏蔽默认示例；
- 文件缺失表示尚未配置；损坏文件会原样保留并安全降级到默认绑定；
- Windows 启动时把合并后的只读快照交给现有状态机，不改变单命令解析边界；
- 提供校验、冲突判断、原子保存和显式 reload 接口，供后续界面调用。

显式 reload 只生成新的有效快照，当前运行中的 Hook 不会被暗中替换；保存
后仍需重启 SciType 才能让后台输入程序使用新绑定。本轮没有文件监听、后台
轮询、GUI、导入导出、`trigger → symbol_id` 用户配置或通用多占位符系统。

完整命令请查看[理科符号速查表](docs/symbols.md)。

## 符号与快捷键的数据边界

SciType 不根据专业含义规定用户必须使用什么缩写。同一个符号在不同专业中
可能有不同含义，内置目录只描述符号本身。

- `src/scitype/data/symbols.json` 是符号目录，保存稳定 ID、名称、分类和
  输出模板，不包含 trigger；
- `src/scitype/data/default_bindings.json` 保存当前兼容默认示例的
  `trigger → symbol_id`；
- `%LOCALAPPDATA%\SciType\packs\` 保存可选的本地只读 JSON 扩展包；
- `/xw → φ` 暂时作为旧版本兼容别名保留，更中性的名称示例是
  `/fi → φ`；
- 希腊字母示例按字母名称组织，`d` 前缀表示大写；
- 本轮不包含化学式、化学反应、化学专用结构或专业语义别名。

V0.5b 用户绑定保存在
`%LOCALAPPDATA%\SciType\user_bindings.json`，不会与包资源混放，也不会
因程序升级被覆盖。V0.6 设置程序可以搜索、预览和增删改这些直接的
`trigger → replacement`，并在只读词典中查找基础命令与本地扩展包。用户
配置整体导入导出仍属于后续版本。只读词典的停用项单独保存在
`%LOCALAPPDATA%\SciType\catalog_masks.json`，不会向旧版严格
`user_bindings.json` schema 增加字段。

详细边界见[数据设计说明](docs/design.md)。

## 用户自定义 A→B 绑定

V0.5b 源码版启动时读取下面的可选文件：

```text
%LOCALAPPDATA%\SciType\user_bindings.json
```

程序不会自动创建或覆盖该文件。需要测试时，请先退出 SciType，再以 UTF-8
创建文件，例如：

```json
{
  "schema_version": 1,
  "bindings": [
    {
      "trigger": "/my1",
      "replacement": "★",
      "enabled": true
    },
    {
      "trigger": "/kk",
      "replacement": "【${cursor}】",
      "enabled": true
    },
    {
      "trigger": "/fi",
      "replacement": "此项停用并屏蔽默认 /fi",
      "enabled": false
    }
  ]
}
```

重新启动源码版后：

- `/my1` 加 `Space` 或 `Enter` 输出 `★`；
- `/kk` 输出 `【】`，光标位于括号中；
- `/fi` 未展开为默认 `φ`，因为同名用户项已明确停用；
- 删除用户文件中的 `/fi` 后重启，随包 `/fi → φ` 会恢复。

trigger 目前必须为 `/` 加一个或多个小写 ASCII 字母或数字，或为 `//`；
replacement 必须是非空字符串，最多包含一个 `${cursor}`。`${0}`、`${1}`、
`${2}` 和其他 `${...}` 不是可用语法。文件内 trigger 重复时整份用户配置
验证失败，不允许依赖加载顺序覆盖。

用户配置损坏或验证失败时，SciType 不删除、不覆盖也不重置原文件，只记录
不含 trigger 和 replacement 的错误类型，并继续用默认绑定安装 Hook。
`reload_user_bindings()` 失败会保留调用方当前的有效快照；成功会返回新快照
以及“需重启后台 SciType 才能生效”的状态，不实现自动热重载。

格式、优先级和故障处理详见
[用户绑定说明](docs/user-bindings.md)。

### V0.6：独立用户绑定设置程序

- 新增基于 PySide6 Essentials 6.11.1 与 Qt Widgets 的中文设置窗口；
- `SciTypeSettings.exe` 独立管理用户绑定，不接入或重构键盘 Hook 的事件
  循环；
- 采用 Quiet Utility 信息架构，分为“我的绑定”“词典”“设置”三个一级
  入口；
- 支持搜索、新建、编辑、删除、启用/停用、多行文本、纯文本预览、实时
  中文校验和键盘快捷操作；
- “词典”只读展示随包基础词典和
  `%LOCALAPPDATA%\SciType\packs\` 中的本地 JSON 扩展包；
- 扩展包只允许 schema_version 1 的静态数据，不执行脚本、HTML、动态
  变量或其他代码；损坏包不会影响基础词典、用户绑定或程序启动；
- 可以复制词典 trigger、创建用户自定义版本、打开扩展包目录，以及验证后
  安全导入本地 JSON；相同 pack id 必须确认后才替换；
- GUI 只调用 V0.5b 的加载、验证、冲突、原子保存与 reload 接口，不直接
  读写用户 JSON；词典与扩展包同样通过独立服务加载；
- 切换项目、新建或关闭窗口时，未保存修改可选择保存、放弃或取消；
- 用户配置损坏时保留原文件，界面进入只读安全状态，可打开配置文件夹；
- 设置程序通过 `%LOCALAPPDATA%\SciType\runtime_status.json` 中不含配置
  内容的 PID、启动时间和最终有效词典 SHA-256，持续区分后台未运行、配置
  已应用、等待重启，以及“检测到旧后台但无法确认配置”四种状态；没有新版
  状态文件时会只读探测同一个 named mutex，不按进程名称猜测；不使用 IPC、
  `taskkill`、自动重启或热更新；
- 发布目录同时包含原后台 `SciType.exe` 和独立设置
  `SciTypeSettings.exe`。

本轮不包含用户配置导入导出、在线词库、可执行插件、通用多槽位模板、QML、
Qt WebEngine、托盘、自动更新或安装器。

### 本地只读扩展包

扩展包目录：

```text
%LOCALAPPDATA%\SciType\packs\
```

每个扩展包是一个 UTF-8 JSON 文件，包含 `schema_version`、pack 的
`id/name/version` 元数据和静态词条。基础词典与扩展包均不可在 GUI 中直接
编辑；“创建自定义版本”只会把内容复制进用户绑定编辑器。

扩展词条与基础词典、其他扩展包或系统保留命令冲突时会在词典页标记，并且
不参与有效输入。启用的用户绑定会覆盖同名词典值，停用的同名用户绑定会
移除该 trigger；独立词典屏蔽在最终合并阶段应用。词典详情页可以停用基础
或扩展词条：程序只在用户
目录的 `catalog_masks.json` 中记录 trigger；重新启用时删除该 trigger，
不改写 `user_bindings.json` 或只读来源。冲突词条不提供启用开关。完整
格式、安全导入和故障边界见
[本地只读扩展包说明](docs/extension-packs.md)。

## 运行环境

- Windows 10 或 Windows 11
- x64 发布包
- 普通权限即可操作普通权限运行的记事本

发布包不需要预先安装 Python，不需要联网，也不会请求管理员权限。设置程序
随包携带 PySide6/Qt 动态库；第三方组件说明见发布目录
`THIRD_PARTY_NOTICES.txt`。普通权限的 SciType 无法向更高完整性级别的
程序注入文本。

从源码运行或构建时需要 Python 3.10 或更高版本。

## 从发布包启动

解压 `SciType-0.6.0-windows-x64.zip`，保留文件夹内的全部文件和
`_internal` 目录。双击 `SciType.exe` 启动后台输入；双击
`SciTypeSettings.exe` 管理用户绑定、查找词典或导入本地扩展包。不要单独
复制任一 EXE。

程序默认在后台运行，不显示控制台窗口。按 `Ctrl + Alt + Q` 安全退出。
日志仍位于 `%LOCALAPPDATA%\SciType\scitype.log`；发布目录中的
`open_log_folder.bat` 只用于打开该日志目录。

发布包的详细使用与安全说明见同目录 `README.txt`。

## 安装源码开发环境

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --editable ".[gui]"
```

## 源码开发启动方式

### 前台排错启动

```powershell
.\scripts\start_scitype_debug.ps1
```

该脚本使用 `.venv\Scripts\python.exe`，保留控制台和错误输出。也可以直接
执行：

```powershell
.\.venv\Scripts\python.exe -m scitype.windows_demo
```

正式应用入口也可在开发环境中通过以下命令启动：

```powershell
.\.venv\Scripts\python.exe -m scitype.app
```

`scitype.windows_demo` 只保留兼容入口，不复制启动或输入逻辑。

独立设置程序：

```powershell
.\.venv\Scripts\python.exe -m scitype.settings_app
```

设置程序关闭后不会影响已运行的后台 SciType。保存后，窗口顶部与“设置”
页面会持续显示后台是否运行，以及当前配置是否已应用；若后台仍使用旧
快照，会明确提示需要重启。本版本不会自动结束或重启后台。

### 创建桌面快捷方式

```powershell
.\scripts\create_desktop_shortcut.ps1
```

脚本只在当前用户桌面创建或更新 `SciType.lnk`，目标为项目虚拟环境中的
`pythonw.exe`，不会请求管理员权限。创建前会检查：

- `.venv` 是否存在；
- `python.exe` 和 `pythonw.exe` 是否存在；
- 当前虚拟环境能否导入 `scitype`。

任何条件不满足时都会显示中文错误，不会创建损坏的快捷方式。

删除快捷方式：

```powershell
.\scripts\remove_desktop_shortcut.ps1
```

删除脚本只处理当前用户桌面的 `SciType.lnk`，不会删除项目、虚拟环境或
日志。

### V0.1 终端解析器

```powershell
.\.venv\Scripts\python.exe -m scitype
```

## 单实例与退出

启动程序时会使用基于当前用户标识生成的 `Local\` named mutex。第一个
实例验证词库并安装 Hook；第二个实例会提示“SciType 已在运行”，不会创建
第二套 Hook，随后正常退出。

程序通过 `Ctrl + Alt + Q` 退出。正常退出和异常退出都会优先释放 Hook 和
mutex。进程异常终止时，Windows 也会回收 mutex 句柄。

## 后台日志与隐私

日志位置：

```text
%LOCALAPPDATA%\SciType\scitype.log
```

日志使用 UTF-8 和标准库 `RotatingFileHandler`，单个文件最大 512 KiB，
最多保留 3 个备份。只记录：

- 程序启动和退出；
- Hook 安装和释放；
- 第二实例被拒绝；
- 未处理异常。

日志严禁记录用户普通输入、命令缓冲区、按键流水、窗口标题或完整公式。
设置程序也不记录用户 trigger、replacement、词典搜索词、所选词条、
剪贴板内容或扩展包词条内容。
分式会话只在内存中保存固定阶段和不透明的前台窗口句柄；鼠标取消监听不
读取或保存鼠标坐标。

## 自动测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

自动测试覆盖解析、模板、状态机、固定分式会话、Windows 适配、数据分层、
单实例判断、日志配置和启动脚本静态契约。真实全局 Hook、鼠标取消、真实
named mutex 双进程行为和 `.lnk` 创建仍需人工验证。

## 构建 Windows 发布包

`build` 可选依赖固定 PyInstaller 和 PySide6 Essentials 的构建版本：

```powershell
.\.venv\Scripts\python.exe -m pip install --editable ".[build]"
.\scripts\build_windows_release.ps1
```

如果本机仅因 PowerShell 执行策略拒绝本地脚本，可只对该构建子进程使用
`RemoteSigned`，不修改系统级策略：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\build_windows_release.ps1
```

脚本会清理项目内旧的 `build`、`dist` 和 `release`，先运行全部测试，再
依据 `SciType.spec` 构建两个无控制台 `onedir` 程序。随后会验证冻结资源、
两个 EXE 的版本信息、Qt 模块边界、发布文件、ZIP、许可证一致性及开发机
敏感路径，最后生成：

```text
release/
├── SciType-0.6.0-windows-x64/
│   ├── SciType.exe
│   ├── SciTypeSettings.exe
│   ├── _internal/
│   ├── LICENSE
│   ├── THIRD_PARTY_NOTICES.txt
│   ├── third_party_licenses/
│   ├── README.txt
│   ├── symbols.md
│   ├── extension-packs.md
│   └── open_log_folder.bat
├── SciType-0.6.0-windows-x64.zip
└── SHA256SUMS.txt
```

完整构建边界和发布检查见
[Windows 发布说明](docs/windows-release.md)。

## Windows 发布包人工测试清单

### 词库与光标

从构建目录以外的位置复制整个发布文件夹，在记事本中检查：

- `/gh` → `√()`，光标位于括号内；
- `/wq` → `∞`；
- `/xy` → `≤`；
- `/dy` → `≥`；
- `/bd` → `≠`；
- `/qh` → `∑`；
- `/pd` → `∂`；
- `/sy` → `∈`；
- `/jj` → `∩`；
- `/bj` → `∪`；
- `/pi` → `π`；
- `/gm` → `γ`，`/dgm` → `Γ`；
- `/sg` → `σ`，`/dsg` → `Σ`；
- `/fi` → `φ`，`/dfi` → `Φ`；
- `/og` → `ω`，`/dog` → `Ω`。

### 快捷方式、单实例和日志

1. 在未安装 Python 的 Windows 10/11 x64 环境双击 `SciType.exe`。
2. 确认没有控制台窗口，且普通输入“今天学习”不受影响。
3. 在记事本中输入上述命令并检查输出和光标位置。
4. 检查 `//`、未知 `/abc`、可打印失败恢复 `/x1`、`Esc` 和
   `Backspace`。
5. 再次双击 EXE，确认提示“SciType 已在运行”。
6. 确认没有第二套 Hook、字符重复或响应叠加。
7. 按 `Ctrl + Alt + Q` 退出。
8. 退出后再次双击，确认可以重新启动。
9. 双击 `open_log_folder.bat`，确认打开
   `%LOCALAPPDATA%\SciType\`。
10. 检查 `scitype.log` 只含生命周期和异常信息，不含普通输入。
11. 将整个发布目录移动到其他位置后重新启动。
12. 退出后继续输入，确认键盘完全恢复正常。
13. 双击 `SciTypeSettings.exe`，创建、编辑、停用和删除虚构绑定，关闭并
    重开后确认数据保持。
14. 制造冲突、多个 `${cursor}` 和损坏的隔离配置，确认不会覆盖旧文件或
    显示 Python 堆栈。
15. 确认关闭设置窗口不影响已运行的 `SciType.exe`。

以上步骤分别在中文输入法中文模式和英文模式执行，并记录是否出现重复、
漏字、吞键、光标偏移或明显延迟。未执行的项目必须明确标记“未验证”，
自动测试不能替代真实 Hook 和无 Python 环境测试。

源码开发环境的桌面快捷方式创建和删除脚本仍可使用，但它们不属于当前
V0.6 便携发布包。

## V0.5a 分式实验人工测试

V0.6 便携发布包已经包含该实验，可直接启动其中的 `SciType.exe`。如需从
源码验证，可运行：

```powershell
.\.venv\Scripts\python.exe -m scitype.windows_demo
```

分别在记事本和聊天框中执行：

1. 输入 `/fs`，按 `Space` 或 `Enter`，确认得到 `()/()`，光标位于第一
   个括号内。
2. 输入 `x+1`，按第一次 `Tab`，确认光标进入第二个括号内，且目标程序
   没有收到该次 Tab。
3. 输入 `x-1`，按第二次 `Tab`，确认光标到达表达式末尾。
4. 再按第三次 `Tab`，确认恢复目标程序原本行为。
5. 重新开始 `/fs`，分别测试 `Esc`、四个方向键、`Home`、`End`、
   `PageUp`、`PageDown`、切换前台窗口和鼠标点击；会话应取消，已有文本
   应保留，下一次 `Tab` 应交还目标程序。
6. 确认普通字符和 `Backspace` 不会提前取消会话。
7. 在会话中按 `Ctrl + Alt + Q`，确认程序退出且键盘恢复正常。
8. 检查日志不含输入字符、窗口标题或完整公式。

## V0.5b 用户绑定人工测试

V0.6 设置程序已经使用这套底层服务。以下隔离故障场景仍建议从源码测试：

```powershell
.\.venv\Scripts\python.exe -m scitype.windows_demo
```

1. 确认没有 `user_bindings.json` 时，`/fi`、`/jf`、`/jdz`、`/gh`、`/fs`
   和 `//` 仍按默认行为工作。
2. 退出 SciType，在隔离的临时 `LOCALAPPDATA` 中按上文格式创建 UTF-8
   用户文件并重新启动。
3. 在测试输入框中确认 `/my1` 输出 `★`，`/kk` 删除占位符并把光标放在
   括号中。
4. 确认启用的同名绑定覆盖默认输出，停用的同名绑定屏蔽默认输出，而未冲突
   的 `/jf` 仍可用。
5. 修改用户文件后不重启，确认当前会话仍使用启动时快照；重启后新值生效。
6. 故意损坏隔离配置中的 JSON，确认原文件未被覆盖、Hook 仍安装，且 `/fi`
   等默认绑定继续可用。
7. 确认用户文件始终位于 `%LOCALAPPDATA%\SciType\`，包目录中没有生成个人
   配置。
8. 检查日志不含测试 trigger、replacement 或配置内容。

## 已知限制

- 当前只保证 Windows 记事本中的技术链路；
- 普通权限无法向更高完整性级别的程序注入文本；
- 不同键盘布局、死键和复杂 IME 仍可能存在差异；
- `Local\` mutex 保护当前 Windows 交互会话中的同一用户实例；
- 每个模板最多支持一个 `${cursor}`；
- 分式仅支持固定 `()/()` 和两次向右跳转，不检查用户是否改变了结构；
- `Shift+Tab`、通用多占位符、任意槽位、嵌套模板和其他模板的 Tab 跳转
  均未实现；
- 鼠标按键或滚轮会直接取消分式会话，不尝试恢复鼠标改变后的槽位；
- 没有 n 次根模板；
- 运行中后台不会热加载用户绑定；设置界面会识别“未运行 / 已应用 / 等待
  重启 / 后台存在但配置未知”，但不会代替用户重启；设置界面没有用户配置
  导入导出、完整预设管理、默认词库或扩展包直接编辑、候选窗口、托盘或
  开机自启；
- 本地扩展包只支持 schema_version 1 的静态 JSON，不支持包依赖、在线
  下载、自动更新、脚本或可执行插件；
- 当前发布形式是需保留 `_internal` 的便携目录和 ZIP，没有安装器；
- EXE 未数字签名，PyInstaller 产物可能被安全软件启发式误报；
- 没有 LaTeX 模式、联网功能或应用专项适配。

SciType 不会关闭、绕过或修改 Windows Defender，也不会自动添加排除项。
发布构建没有启用 UPX。请只从项目作者维护的官方 GitHub Release 获取
正式发布包，并用 `SHA256SUMS.txt` 核对哈希；遇到安全软件警报时应停止
运行并反馈，而不是强行绕过。

V0.6 设置程序使用动态链接的 PySide6/Qt。对应第三方声明、可替换动态库
说明和许可证位置见 `packaging/THIRD_PARTY_NOTICES.txt`；构建时不会收集
QML、Qt Quick 或 Qt WebEngine。

## 许可证与使用范围

SciType 采用 **MIT License + “Commons Clause” License Condition v1.0**。
它是源码可用软件（source-available），不是 OSI 定义下的开源软件。

在保留许可证、版权声明和 Commons Clause 通知并遵守完整许可证的前提下，
以下使用方式属于允许范围：

- 个人免费使用；
- 用于学习、教学和科研；
- 公司及组织内部使用；
- 在工作或付费教学中把 SciType 作为输入工具使用；
- 查看、修改和分发源代码；
- 将 SciType 集成进真正增加了独立、实质性价值的更大产品。

未经作者另行书面商业授权，以下行为不在本许可证授权范围内：

- 直接出售 SciType；
- 改名、换图标或轻微修改后收费发布；
- 将主要价值实质上来自 SciType 的版本做成付费下载、订阅或商业服务；
- 删除许可证、版权声明或 Commons Clause 通知。

这并非“禁止一切商业使用”。使用 SciType 完成有报酬的工作，与出售主要
价值来自 SciType 本身的软件或服务，是不同的使用场景。需要商业授权时，
请通过 GitHub Issues 联系项目作者。

更多示例见[许可证与使用场景说明](docs/licensing.md)。README 仅用于帮助
理解授权范围；如其解释与 [LICENSE](LICENSE) 正文不一致，以 LICENSE
正文为准。
