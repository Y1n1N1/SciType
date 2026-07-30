SciType 0.6.0 Windows x64 使用说明
===================================

SciType 是面向中文用户的 Windows 本地理科符号快捷输入工具。

一、启动与退出

1. 保留本目录中的全部文件和 _internal 文件夹，不要只复制两个 EXE。
2. 双击 SciType.exe。程序会在后台运行，默认不显示控制台窗口。
3. 在普通输入框中输入斜杠命令，并按 Space 或 Enter 确认。
4. 随时按 Ctrl + Alt + Q 安全退出。
5. 再次启动时若已有实例运行，SciType 会提示后退出，不会安装第二套监听。

常用示例：

  /fi   -> φ
  /jdz  -> ||，光标位于中间
  /jf   -> ∫dx，光标位于 ∫ 和 d 之间
  /gh   -> √()，光标位于括号内
  /fs   -> ()/()，两次 Tab 依次跳到分母和末尾
  //    -> /

完整示例见同目录的 symbols.md。

二、管理自己的快捷绑定

1. 双击 SciTypeSettings.exe，打开独立设置窗口。
2. 在“我的绑定”点击“新建绑定”，填写以 / 开头的触发词和静态输出内容。
3. 输出可以包含中文、Unicode 数学符号、颜文字、换行，以及最多一个
   ${cursor}。
4. 保存成功后，重启后台 SciType.exe 才会生效；设置程序不会强制结束或
   自动重启后台程序。
5. 关闭 SciTypeSettings.exe 不会结束已经运行的 SciType.exe。

用户配置保存在：

  %LOCALAPPDATA%\SciType\user_bindings.json

配置损坏时，设置程序会保留原文件并提供打开配置目录的入口，不会自动覆盖。

三、词典与本地扩展包

“词典”页面只读展示 SciType 基础词典，以及下列目录中的本地 JSON
扩展包：

  %LOCALAPPDATA%\SciType\packs\

可以搜索名称、触发词、输出和分类，复制 trigger，或创建自己的版本。
扩展包只包含静态 JSON 数据，不执行脚本。导入前会验证；同一 pack id
必须确认后才会替换。完整格式见 extension-packs.md。

四、运行要求

- Windows 10 或 Windows 11，x64 系统。
- 在普通记事本等普通权限程序中使用时，不需要管理员权限。
- 运行发布包不需要预先安装 Python，也不需要联网。
- 普通权限的 SciType 无法向以管理员权限运行的目标程序注入文本。

五、日志与隐私

日志文件位于：

  %LOCALAPPDATA%\SciType\scitype.log
  %LOCALAPPDATA%\SciType\scitype-settings.log

可双击 open_log_folder.bat 打开日志目录。SciType 只记录程序生命周期、Hook
安装/释放、配置操作状态和非内容型错误，不记录普通输入、trigger、
replacement、搜索词、扩展包词条、命令缓冲区或按键流水。

六、安全提示

本版本使用 PyInstaller onedir 打包，没有启用 UPX，也没有数字签名。某些
安全软件可能对未签名的 PyInstaller 程序产生误报。请不要关闭或绕过
Windows Defender；只从项目作者发布的官方 GitHub Release 获取发布包，
并使用 SHA256SUMS.txt 核对哈希。遇到警报时应停止运行并反馈，不要强行
添加排除项。

七、许可证

SciType 是源码可用软件（source-available），不是 OSI 定义下的开源软件。
使用、修改或分发前请阅读同目录 LICENSE；许可证正文优先于其他说明。

设置程序使用 PySide6/Qt。第三方组件的版权、动态链接说明和许可证位置见
THIRD_PARTY_NOTICES.txt，完整 LGPL v3 与 GPL v3 正文位于
third_party_licenses 文件夹。第三方组件继续适用各自许可证。

Copyright (c) 2026 Y1n1N1
