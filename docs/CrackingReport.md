# WF无限调优 MCP (v5.0.0) 逆向与绕过报告

## 1. 概述
本报告详细记录了对 "WF无限调优 MCP" 插件 (v5.0.0) 的逆向分析、验证绕过及隐私保护处理过程。

**分析对象:** `wf-dialog-mcp-5.0.0.vsix` (已解压)
**核心目标:** 绕过卡密验证，移除远程校验，恢复完整功能。

## 2. 核心验证逻辑分析

通过对入口文件 `extension/dist/extension.js` 的静态分析，定位到以下关键验证逻辑：

### 2.1 本地状态校验
插件内部维护了两个核心状态变量，默认值为 `false` (混淆为 `!0x1`)：
- `valid`: 标记 License 是否有效。
- `activated`: 标记是否已激活。

原始代码片段 (混淆后):
```javascript
{'valid':!0x1,'activated':!0x1 ...}
```

### 2.2 远程验证机制
插件会在运行时向以下接口发送请求以验证 License 状态：
- **激活检查接口:** `https://wf-license-gen.wf-license-zhc.workers.dev/api/check-activation`
- **时间校验接口:** `https://api.m.taobao.com/rest/api3.do` (获取网络时间，防止本地改时间绕过试用)

## 3. 实施方案与修改记录

### 3.1 静态代码补丁
直接修改 `extension.js` 中的默认状态值，强制使其初始化为 `true`。

**修改前:**
```javascript
{'valid':!0x1,'activated':!0x1 ...}
```

**修改后:**
```javascript
{'valid':!0x0,'activated':!0x0 ...}
```

**操作统计:**
- `'valid':!0x1` -> `'valid':!0x0`: 替换 12 处
- `'activated':!0x1` -> `'activated':!0x0`: 替换 6 处

### 3.2 阻断远程连接 (隐私保护)
为防止插件自动联网校验导致状态回滚或上传用户隐私，将所有相关远程 API 域名重定向到本地回环地址。

**修改记录:**
- `https://wf-license-gen.wf-license-zhc.workers.dev` -> `http://127.0.0.1`
- `https://api.m.taobao.com` -> `http://127.0.0.1`

此修改确保了插件在离线或联网状态下均无法连接到验证服务器，从而保持“已激活”状态。

## 4. 验证结果
- **语法检查:** 通过 `node -c` 验证修改后的 `extension.js` 语法正确。
- **逻辑验证:** 静态分析确认核心状态变量已强制置真。
- **安全检查:** 远程验证域名已全部屏蔽。

## 5. 交付物
- **修改后的文件:** `extension/dist/extension.js`
- **重打包插件:** `wf-dialog-mcp-5.0.0-cracked.vsix`

## 6. 声明
本报告及相关修改仅供安全研究与学习使用。

---

## 7. 二次修改记录 (2026-01-09)

### 7.1 工具名称修改
- **修改前**: `task-sync-{端口号}`
- **修改后**: `shouji-{端口号}`
- **影响文件**: `extension/dist/extension.js`
- **修改次数**: 4处

### 7.2 工具描述本地化
- **工具描述**: "User feedback collection tool for task coordination" → "收集"
- **参数本地化**:
  - `title`: "Brief task status (required)" → "简要任务状态（必填）"
  - `summary`: "Context for user (optional)" → "用户上下文（可选）"
  - `choices`: "User options (optional)" → "用户选项（可选）"
  - `default_feedback`: "Suggested input (optional)" → "建议输入（可选）"

### 7.3 作者信息修改
**修改文件**: `extension/package.json`
- **publisher**: "wf-dialog" → "f"
- **author**: 新增
  - name: "f"
  - email: "f@gmail.com"
- **repository.url**: "https://gitee.com/zhczhczhc/wf-dialog-mcp.git" → "https://github.com"

### 7.4 技术细节
所有修改均在混淆后的代码中完成，通过字符串替换实现功能变更。
