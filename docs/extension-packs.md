# SciType 本地只读扩展包

V0.6 可以从本机目录加载纯数据 JSON 扩展包，用于补充“词典”页面和后台输入
字典。扩展包不是插件：SciType 不执行其中的脚本、Python、Shell、HTML、
动态变量或其他代码。

## 存放位置

```text
%LOCALAPPDATA%\SciType\packs\
```

每个扩展包是一个独立的 UTF-8 `.json` 文件。它与随程序发布的
`symbols.json`、`default_bindings.json` 以及用户自己的
`user_bindings.json` 相互分离。程序升级不会主动改写本目录。

## schema_version 1

```json
{
  "schema_version": 1,
  "pack": {
    "id": "scitype.kaomoji.zh-cn",
    "name": "中文颜文字",
    "version": "1.0.0",
    "description": "常用中文语境颜文字",
    "author": "SciType Community"
  },
  "entries": [
    {
      "name": "微笑",
      "category": "颜文字",
      "trigger": "/weixiao",
      "replacement": "(＾▽＾)"
    }
  ]
}
```

必需字段：

- 顶层：`schema_version`、`pack`、`entries`；
- `pack`：`id`、`name`、`version`；
- 每个词条：`name`、`category`、`trigger`、`replacement`。

`description` 和 `author` 可选。当前 schema 不接受未知字段，以免未来格式
迁移时把数据误读成其他含义。

`trigger` 和 `replacement` 使用与用户绑定相同的校验规则。replacement
可以包含零个或一个 `${cursor}`，不支持 `${0}`、`${1}`、`${2}`、动态
日期、正则、剪贴板宏或多槽位模板。

## 只读、优先级与冲突

基础词典和扩展包在 GUI 中始终只读。需要修改某个词条时，应点击“创建
自定义版本”，把静态内容复制到“我的绑定”编辑器；源 JSON 不会被修改。

有效输入按以下规则产生：

1. 先加载 SciType 基础词典；
2. 只加入没有冲突的扩展包词条；
3. `enabled=true` 的用户绑定覆盖同名词典 trigger；
4. `enabled=false` 的用户绑定屏蔽同名词典 trigger；
5. 最后应用独立 `catalog_masks.json` 中的词典屏蔽 trigger。

扩展包不能覆盖系统保留命令。V0.6 中 `//` 和固定分式 `/fs` 属于保留
命令。扩展包与基础词典或其他扩展包发生 trigger 冲突时，冲突扩展词条仍可
在词典页看到并会显示原因，但不会参与有效输入。多个扩展包之间的冲突按
完整集合计算，不依赖文件枚举顺序。基础词典的 source id `scitype.base`
同样属于保留值，扩展包不得使用。

词典详情页可以通过独立词典屏蔽服务停用一个无冲突扩展词条，但不会修改
扩展包文件或 `user_bindings.json`；重新启用时从
`%LOCALAPPDATA%\SciType\catalog_masks.json` 删除对应 trigger。冲突词条
不显示普通启用开关，也不能借此绕过冲突规则。

## 损坏包与导入

损坏、非 UTF-8、schema 不支持或词条非法的扩展包：

- 不会被删除或覆盖；
- 不影响基础词典；
- 不影响用户绑定；
- 不阻止 SciType 启动；
- 会在词典页面显示加载失败；
- 日志只写非内容型错误代码和异常类型。

程序只枚举扩展包目录的直接子文件，`.json` 后缀大小写不敏感且排序确定；
不会扫描子目录。单个 JSON 文件上限为 8 MiB，嵌套过深或超过上限均按无效
扩展包隔离。

设置程序支持选择本地 JSON 后导入。导入前会完整验证，并在目标目录中使用
临时文件、`fsync` 和 `os.replace()` 安全复制。发现相同 `pack.id` 时必须
由用户明确确认，程序不会静默覆盖。

当前没有在线商店、网络下载、自动更新、依赖系统、社区评分、远程仓库或
可执行插件。
