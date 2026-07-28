# SciType

SciType 是一个面向中文用户的 Windows 本地理科符号快捷输入项目。它允许
用户在普通输入框中通过斜杠命令输入 Unicode 符号和简单公式片段。

当前示例包括：

- `/fi` → `φ`
- `/jdz` → `||`，光标位于两条竖线之间
- `/jf` → `∫dx`，光标位于 `∫` 与 `d` 之间
- `/gh` → `√()`，光标位于括号内

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

完整命令请查看[理科符号速查表](docs/symbols.md)。

## 符号与快捷键的数据边界

SciType 不根据专业含义规定用户必须使用什么缩写。同一个符号在不同专业中
可能有不同含义，内置目录只描述符号本身。

- `src/scitype/data/symbols.json` 是符号目录，保存稳定 ID、名称、分类和
  输出模板，不包含 trigger；
- `src/scitype/data/default_bindings.json` 保存当前兼容默认示例的
  `trigger → symbol_id`；
- `/xw → φ` 暂时作为旧版本兼容别名保留，更中性的名称示例是
  `/fi → φ`；
- 希腊字母示例按字母名称组织，`d` 前缀表示大写；
- 本轮不包含化学式、化学反应、化学专用结构或专业语义别名。

未来用户绑定将保存在 `%LOCALAPPDATA%\SciType\`，不会与包资源混放，也
不会因程序升级被覆盖。搜索符号、自定义缩写、预览、冲突检测、增删改以及
导入导出属于后续版本，本轮没有实现自定义界面。

详细边界见[数据设计说明](docs/design.md)。

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10 或更高版本
- 普通权限即可操作普通权限运行的记事本

项目没有第三方运行时依赖。

## 安装开发环境

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --editable .
```

## 启动方式

### 前台排错启动

```powershell
.\scripts\start_scitype_debug.ps1
```

该脚本使用 `.venv\Scripts\python.exe`，保留控制台和错误输出。也可以直接
执行：

```powershell
.\.venv\Scripts\python.exe -m scitype.windows_demo
```

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

日志严禁记录用户普通输入、命令缓冲区或按键流水。

## 自动测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

自动测试覆盖解析、模板、状态机、Windows 适配、数据分层、单实例判断、
日志配置和启动脚本静态契约。真实全局 Hook、真实 named mutex 双进程行为
和 `.lnk` 创建仍需人工验证。

## V0.3a 人工测试清单

### 词库与光标

在记事本中检查：

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

1. 运行 `scripts/create_desktop_shortcut.ps1`。
2. 确认当前用户桌面出现 `SciType` 快捷方式。
3. 双击快捷方式，确认无需打开 PowerShell 即可使用。
4. 在记事本中输入上述命令并检查输出和光标位置。
5. 再次双击快捷方式，确认提示“SciType 已在运行”。
6. 确认没有第二套 Hook、字符重复或响应叠加。
7. 按 `Ctrl + Alt + Q` 退出。
8. 退出后再次双击，确认可以重新启动。
9. 检查 `%LOCALAPPDATA%\SciType\scitype.log` 只含生命周期和异常信息。
10. 运行 `scripts/remove_desktop_shortcut.ps1` 并确认快捷方式被删除。
11. 退出后继续输入，确认键盘完全恢复正常。

以上步骤分别在中文输入法中文模式和英文模式执行，并记录是否出现重复、
漏字、吞键、光标偏移或明显延迟。

## 已知限制

- 当前只保证 Windows 记事本中的技术链路；
- 普通权限无法向更高完整性级别的程序注入文本；
- 不同键盘布局、死键和复杂 IME 仍可能存在差异；
- `Local\` mutex 保护当前 Windows 交互会话中的同一用户实例；
- 每个模板最多支持一个 `${cursor}`；
- 没有多占位符、Tab 跳转、分式模板或 n 次根模板；
- 没有自定义绑定界面、完整预设管理、GUI、候选窗口、托盘或开机自启；
- 没有 exe 打包、安装器、LaTeX 模式、联网功能或应用专项适配。

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
