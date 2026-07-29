SciType 0.4.0 Windows x64 使用说明
===================================

SciType 是面向中文用户的 Windows 本地理科符号快捷输入工具。

一、启动与退出

1. 保留本目录中的全部文件和 _internal 文件夹，不要只复制 SciType.exe。
2. 双击 SciType.exe。程序会在后台运行，默认不显示控制台窗口。
3. 在普通输入框中输入斜杠命令，并按 Space 或 Enter 确认。
4. 随时按 Ctrl + Alt + Q 安全退出。
5. 再次启动时若已有实例运行，SciType 会提示后退出，不会安装第二套监听。

常用示例：

  /fi   -> φ
  /jdz  -> ||，光标位于中间
  /jf   -> ∫dx，光标位于 ∫ 和 d 之间
  /gh   -> √()，光标位于括号内
  //    -> /

完整示例见同目录的 symbols.md。

二、运行要求

- Windows 10 或 Windows 11，x64 系统。
- 在普通记事本等普通权限程序中使用时，不需要管理员权限。
- 运行发布包不需要预先安装 Python，也不需要联网。
- 普通权限的 SciType 无法向以管理员权限运行的目标程序注入文本。

三、日志与隐私

日志文件位于：

  %LOCALAPPDATA%\SciType\scitype.log

可双击 open_log_folder.bat 打开日志目录。SciType 只记录程序生命周期、Hook
安装/释放和异常，不记录普通输入、命令缓冲区或按键流水。

四、安全提示

本版本使用 PyInstaller onedir 打包，没有启用 UPX，也没有数字签名。某些
安全软件可能对未签名的 PyInstaller 程序产生误报。请不要关闭或绕过
Windows Defender；只从项目作者发布的官方 GitHub Release 获取发布包，
并使用 SHA256SUMS.txt 核对哈希。遇到警报时应停止运行并反馈，不要强行
添加排除项。

五、许可证

SciType 是源码可用软件（source-available），不是 OSI 定义下的开源软件。
使用、修改或分发前请阅读同目录 LICENSE；许可证正文优先于其他说明。

Copyright (c) 2026 Y1n1N1
