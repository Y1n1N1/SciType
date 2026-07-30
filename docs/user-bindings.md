# V0.5b 用户快捷绑定

V0.5b 提供与界面无关的 `trigger → replacement` 配置服务。它用于安全地
补充、覆盖或停用随包默认示例，不规定用户应该选择哪一种缩写。

## 文件位置

用户文件固定为：

```text
%LOCALAPPDATA%\SciType\user_bindings.json
```

该文件位于 Python 包和发布目录之外。升级、重新解压或替换 SciType 程序
不会覆盖它。程序不会在文件缺失时自动创建空文件，也不会在启动时改写现有
文件。

## schema_version 1

文件必须是 UTF-8 JSON 对象：

```json
{
  "schema_version": 1,
  "bindings": [
    {
      "trigger": "/ceshi1",
      "replacement": "示例文本",
      "enabled": true
    },
    {
      "trigger": "/kuohao",
      "replacement": "【${cursor}】",
      "enabled": true
    },
    {
      "trigger": "/fi",
      "replacement": "停用项的内容不会展开",
      "enabled": false
    }
  ]
}
```

顶层只包含：

- `schema_version`：当前必须为整数 `1`；
- `bindings`：用户绑定数组。

每个用户绑定严格只包含：

- `trigger`：以 `/` 开头的正式触发词；
- `replacement`：静态输出文本；
- `enabled`：布尔值，决定该项是否参与展开。

`catalog_mask` 不是正式字段，正常加载器会像处理其他未知字段一样拒绝它。
这保持了旧版严格 schema 的可读性。当前不保存使用次数、时间、标签、分类
或稳定 ID。

## 字段规则

trigger：

- 必须在配置中包含开头的 `/`；
- 主体只能包含小写 ASCII 字母和数字；
- `//` 是允许的特殊触发词；
- 不允许空格、换行、控制字符、大写字母、正则或模糊匹配；
- 同一文件中的 trigger 必须唯一，不能依赖“最后一项覆盖”。

replacement：

- 必须是非空字符串；
- 支持中文、英文、Unicode 数学符号、颜文字、空格和换行；
- 可以没有 `${cursor}`，也可以恰好有一个；
- 多个 `${cursor}` 会验证失败；
- `${0}`、`${1}`、`${2}` 及其他 `${...}` 不是可用语法；
- 内容始终作为静态文本处理，不执行脚本、命令、变量、动态日期、正则或
  剪贴板操作。

`${cursor}` 沿用现有单光标渲染器：插入前删除该标记，再按其右侧字符数定位
真实光标。内部占位符不会原样输入目标窗口。

## enabled、覆盖与屏蔽

有效集合由配置服务统一生成：

1. 先合并基础词典与没有冲突的本地扩展包；
2. 对 `enabled: true` 的用户项写入同名 trigger，因此用户值覆盖默认值；
3. 对 `enabled: false` 的用户项移除同名 trigger，因此同名默认值也被屏蔽；
4. 最后应用 `catalog_masks.json` 中的只读词典屏蔽；
5. 停用且没有同名默认值的普通用户项不参与展开。

Hook 和 V0.6 GUI 只消费配置服务生成的结果，不自行重复判断优先级。

## 损坏文件的安全降级

- 文件不存在：返回“未配置”状态并使用默认绑定；
- 文件有效：返回用户文档和合并后的有效绑定；
- 文件损坏或验证失败：保留原文件，返回失败状态并使用默认绑定；
- 默认词库损坏：属于核心资源错误，阻止 Hook 安装。

用户文件错误不会使整个 SciType 失效。Windows 启动日志只记录“缺失、
成功或失败”、非内容错误代码及异常类型，不记录 trigger、replacement、
配置内容或按键。

## 原子保存

`save_user_bindings()` 执行以下顺序：

1. 在内存中验证完整文档；
2. 在正式文件的同一目录创建临时文件；
3. 以 UTF-8 写入，执行 flush 和 fsync，然后关闭文件；
4. 从临时文件重新读取并验证完整 schema；
5. 使用 `os.replace()` 原子替换正式文件；
6. 无论失败或成功都清理遗留临时文件。

它不会先删除旧文件。校验、写入或替换失败时，原有效文件保持不变。

## 显式 reload

`reload_user_bindings()` 是独立接口：

- 成功时生成一个新的不可变有效快照；
- 失败时原样返回调用方当前的有效快照；
- 不会让半加载配置污染当前状态机；
- 不启动文件监听或后台轮询。

当前运行中的 Windows Hook 没有安全快照交换机制。reload 成功只供调用方
检查新配置；要让后台输入程序采用它，仍需重启 SciType。接口会明确返回
`restart_required=True`，不会假装已经实时生效。

## V0.6 设置界面接入

V0.6 的 `SciTypeSettings.exe` 复用本文所述服务接口，提供用户绑定的搜索、
新建、编辑、删除、启用/停用、校验和纯文本预览。界面不直接读写 JSON，
不编辑基础词典或本地扩展包，也不重新实现 trigger、replacement 或冲突
规则。词典页的“创建自定义版本”只是把静态 trigger 和 replacement 填入
本编辑器，随后仍走同一套用户配置校验与原子保存。

保存时先由服务层验证并原子替换文件，再显式 reload 生成新快照；当前后台
Hook 不会热交换该快照。后台运行期间会另行发布只含 PID、进程启动时间和
最终有效词典 SHA-256 的 `runtime_status.json`；设置程序重新加载基础词典、
合法扩展包、用户绑定和词典屏蔽，使用同一个核心函数计算 hash。状态文件
不含 trigger 或 replacement。若新版状态文件缺失或损坏，但同一用户的
SciType named mutex 已存在，界面显示“检测到后台，但无法确认配置”，不会
误报为未运行。

基础词典或扩展包词条被停用时，独立服务写入：

```text
%LOCALAPPDATA%\SciType\catalog_masks.json
```

```json
{
  "schema_version": 1,
  "disabled_triggers": [
    "/jf"
  ]
}
```

重新启用会从该数组删除 trigger。文件采用严格 UTF-8 schema、8 MiB 上限、
重复字段检测、深度异常隔离，以及与用户文件同等级的临时文件、`fsync`、
重新读取验证和 `os.replace()` 原子保存。损坏的 masks 文件原样保留，但不
阻止基础词典、扩展包或用户绑定加载。

短暂开发阶段曾把 `catalog_mask=true` 写入用户绑定。当前有效配置加载入口
只为一次性迁移识别该字段：先将 trigger 合并、排序并去重写入
`catalog_masks.json`，再把普通绑定按旧版三字段 schema 原子写回
`user_bindings.json`。没有该字段的普通覆盖，即使 replacement 与词典输出
相同，也不会被当成 mask。迁移失败时原文件保留，GUI 显示安全错误。

## 当前不包含

当前不包含在线同步、用户配置导入导出、官方预设管理、文件监听、后台
轮询、`trigger → symbol_id` 用户格式、动态宏或通用多占位符系统。设置
前端只复用本服务的加载、校验、冲突、保存和 reload 接口。本地只读扩展包
格式和优先级另见 `docs/extension-packs.md`。
