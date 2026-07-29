# SciType Windows 发布说明

## 构建边界

V0.4a 使用 PyInstaller 6.21.0 的 `onedir` 模式。`SciType.exe` 是无控制台
窗口的正式入口，Python 运行库和依赖位于同级 `_internal` 目录。发布包不
依赖开发机上的 Python、虚拟环境或项目源码路径。

PyInstaller 只属于 `build` 可选依赖，不是 SciType 的运行时依赖。构建未
启用 UPX，当前没有代码签名，也没有自定义图标；`SciType.spec` 中的
`packaging/SciType.ico` 是未来替换图标的位置，不存在时使用 PyInstaller
默认图标。

## 本地构建

在 Windows x64 和项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --editable ".[build]"
.\scripts\build_windows_release.ps1
```

若当前机器仅因 PowerShell 执行策略拒绝本地脚本，可以只为本次构建子进程
指定 `RemoteSigned`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\build_windows_release.ps1
```

该命令不会修改系统级执行策略或 Defender 设置。

构建脚本会依次检查 64 位 Python、项目安装和 PyInstaller 版本，安全清理
项目内旧的 `build`、`dist`、`release`，运行全部自动测试，执行
`SciType.spec`，运行冻结程序的只读资源自检，复制用户文档，验证目录和
ZIP 内容、版本资源、许可证以及敏感路径，最后生成 SHA-256 哈希。

预期产物：

```text
release/
├── SciType-0.4.0-windows-x64/
│   ├── SciType.exe
│   ├── _internal/
│   ├── LICENSE
│   ├── README.txt
│   ├── symbols.md
│   └── open_log_folder.bat
├── SciType-0.4.0-windows-x64.zip
└── SHA256SUMS.txt
```

## 自动验证与人工验证的边界

构建脚本可以自动确认文件存在、JSON 包资源可读取、LICENSE 一致、ZIP
可解压、版本信息正确、敏感开发路径未泄漏，以及自动测试通过。真实全局
键盘 Hook、不同输入法状态、目标软件兼容性、无 Python 机器运行情况和
安全软件表现必须人工验证，不能由单元测试代替。

## 发布前人工测试

建议从构建目录以外复制整个发布文件夹后执行，且不要只复制 EXE。

1. 在未安装 Python 的 Windows 10/11 x64 环境启动 `SciType.exe`。
2. 确认没有控制台窗口，且普通输入“今天学习”不受影响。
3. 在记事本中输入 `/xw` 和 `/fi` 后按 `Space`，确认得到 `φ`。
4. 输入 `/jdz` 后按 `Space`，确认得到 `||` 且光标位于中间。
5. 输入 `/jf` 后按 `Space`，确认得到 `∫dx` 且光标位于 `∫` 与 `d`
   之间。
6. 输入 `/gh` 后按 `Space`，确认得到 `√()` 且光标位于括号内。
7. 输入 `//`，确认只得到一个 `/`。
8. 输入 `/abc` 后确认，确认原文 `/abc` 被恢复。
9. 输入 `/x1`，确认没有吞字或重复字符。
10. 验证 `Esc` 取消，`Backspace` 编辑及退出符号模式。
11. 再次双击 EXE，确认只允许一个实例且没有第二套 Hook。
12. 按 `Ctrl + Alt + Q` 退出，确认退出后键盘完全恢复。
13. 双击 `open_log_folder.bat`，确认能打开
    `%LOCALAPPDATA%\SciType\`，且日志不含普通输入内容。
14. 将整个发布目录移动到其他位置后重复启动和输入测试。
15. 分别在中文输入法中文模式和英文模式重复第 2–10 步，记录字符重复、
    漏字、吞键、光标偏移或明显延迟。

未执行的人工项目必须在发布记录中明确标注“未验证”，不能用自动测试通过
代替。

## Defender 与分发

发布包未签名，PyInstaller 产物可能被安全软件启发式误报。项目不会禁用或
绕过 Defender，不会自动添加排除项，也不会隐藏反病毒规避逻辑。用户遇到
警报时应停止运行并通过项目渠道反馈。

正式发布时只应从项目作者维护的官方 GitHub Release 提供下载，并同时提供
`SHA256SUMS.txt`。本地构建脚本不会上传文件、访问在线扫描服务、创建桌面
快捷方式或设置开机启动。
