# SciType Windows 发布说明

## 构建边界

V0.6 使用 PyInstaller 6.21.0 的共享 `onedir` 模式。`SciType.exe` 是无
控制台窗口的后台输入入口，`SciTypeSettings.exe` 是独立 Qt Widgets 设置
入口；Python 和 Qt 动态库位于同级 `_internal` 目录。发布包不依赖开发机
上的 Python、虚拟环境或项目源码路径。

`build` 可选依赖固定 PyInstaller 6.21.0 和 PySide6 Essentials 6.11.1。
设置程序只导入 QtCore、QtGui 和 QtWidgets，不使用 QML、Qt Quick 或
Qt WebEngine。构建未启用 UPX，没有代码签名，也没有自定义图标；
`SciType.spec` 中的 `packaging/SciType.ico` 是未来替换图标的位置，
不存在时使用 PyInstaller 默认图标。

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
`SciType.spec`，分别运行两个冻结程序的只读资源自检，复制用户文档和第三
方声明，验证目录和 ZIP 内容、两个版本资源、许可证、Qt 模块范围以及敏感
路径，最后生成 SHA-256 哈希。

预期产物：

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

## 自动验证与人工验证的边界

构建脚本可以自动确认文件存在、JSON 包资源可读取、LICENSE 一致、ZIP
可解压、版本信息正确、敏感开发路径未泄漏，以及自动测试通过。真实全局
键盘 Hook、不同输入法状态、目标软件兼容性、设置窗口实际交互、无 Python
机器运行情况和安全软件表现必须人工验证，不能由单元测试代替。

## Qt 与第三方许可证

PySide6 Essentials 6.11.1、Shiboken6 6.11.1 以及本构建使用的 Qt 6.11.1
组件按其发行元数据提供 LGPL-3.0-only、GPL-2.0-only 或 GPL-3.0-only
选择。本发布包选择 LGPL v3 路径，以可替换 DLL 的动态链接形式分发 Qt。

发布目录必须保留 `THIRD_PARTY_NOTICES.txt`、`third_party_licenses`、
`LICENSE` 和 `_internal`。详细组件、官方来源与动态链接说明见
`packaging/THIRD_PARTY_NOTICES.txt`。这些说明不是对具体分发场景的法律
意见；公开分发前仍应由发布者确认全部实际携带二进制的许可证义务。

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
16. 双击 `SciTypeSettings.exe`，使用虚构内容创建、编辑、停用和删除绑定。
17. 关闭并重开设置程序，确认多行文本、Unicode、颜文字和单个
    `${cursor}` 完整保留。
18. 用一条含内部换行的测试绑定按 `Enter` 确认，确认 replacement 的段落
    换行完整保留、确认键不产生额外尾部换行，随后主动按下的 `Enter` 正常
    工作。
19. 测试 trigger 冲突、多个 `${cursor}`、未保存切换和关闭提示。
20. 在隔离的临时 `LOCALAPPDATA` 中损坏配置，确认 GUI 不崩溃、不覆盖原
    文件且可打开配置文件夹。
21. 确认关闭设置程序不会结束已运行的后台 SciType；保存后重启后台程序，
    确认新绑定才生效。
22. 检查“我的绑定”“词典”“设置”三个一级入口，确认页面导航和绑定列表
    不在同一层级。
23. 在词典页搜索“积分”，确认 `/jf` 的纯文本预览为 `∫│dx`。
24. 在隔离的 `%LOCALAPPDATA%\SciType\packs\` 中放入合法和损坏 JSON，
    确认合法包可搜索，损坏包保留且不影响基础词典。
25. 导入同 pack id 文件时确认必须明确选择是否替换。
26. 分别以 100%、125% 和 150% 缩放检查中文、按钮和输入框无重叠或裁切。

未执行的人工项目必须在发布记录中明确标注“未验证”，不能用自动测试通过
代替。

## Defender 与分发

发布包未签名，PyInstaller 产物可能被安全软件启发式误报。项目不会禁用或
绕过 Defender，不会自动添加排除项，也不会隐藏反病毒规避逻辑。用户遇到
警报时应停止运行并通过项目渠道反馈。

正式发布时只应从项目作者维护的官方 GitHub Release 提供下载，并同时提供
`SHA256SUMS.txt`。本地构建脚本不会上传文件、访问在线扫描服务、创建桌面
快捷方式或设置开机启动。
