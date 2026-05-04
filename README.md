# 基于 Agent 的服务自动化修复系统

## 项目简介

这是一个面向简单 Web 服务的自动化修复系统，当服务运行报错时，系统会自动完成以下链路：

1. 监控异常并获取 Traceback
2. 基于 Agent + Tool Use 分析根因
3. 自动修改代码并执行测试验证
4. 修复成功后自动创建 PR
5. 通过飞书卡片通知开发者

## 系统架构

系统采用三阶段架构：

1. **第一阶段：异常感知与 Traceback 获取**
   - Sentinel Agent 采集异常与 Traceback
   - 生成标准化修复任务

2. **第二阶段：基于 Tool Use 的循环式自动修复**
   - Repair Orchestrator 作为主控 Agent
   - 委派 Explore / Plan / Execute / Verify 四类 AgentTool
   - 子 Agent 调用底层 Primitive Tool 与环境交互

3. **第三阶段：PR 提交与飞书通知**
   - 自动创建 PR、填写修复信息
   - 发送飞书卡片通知开发者 Review

## 目录结构

```
web_service_guard/
├── web_service_guard/
│   ├── __init__.py
│   ├── config.py          # 配置管理
│   ├── enums.py           # 枚举定义
│   ├── errors.py          # 错误处理
│   ├── policy.py          # 门禁与护栏规则
│   ├── audit.py           # 审计记录
│   ├── workflow/          # 工作流编排
│   ├── runtime/           # 运行时核心
│   ├── agent_tools/       # AgentTool 抽象层
│   ├── primitive_tools/   # 底层工具
│   ├── agents/            # 角色 Agent
│   ├── monitoring/        # 监控与 Traceback 采集
│   ├── delivery/          # 交付服务
│   ├── integrations/      # 外部系统适配
│   ├── schemas/           # 数据结构定义
│   └── api/               # 对外接口
├── tests/                 # 测试文件
├── docs/                  # 文档
├── pyproject.toml         # 项目配置
└── README.md              # 项目说明
```

## 快速开始

### 环境准备

1. 安装 Python 3.8+
2. 安装依赖：

```bash
pip install -e .
```

### 配置

1. 创建 `.env` 文件，配置以下环境变量：

```
# 模型配置
ANALYZER_MODEL=ep-20260423222752-9tcpw
ANALYZER_TEMPERATURE=0.3
ANALYZER_MAX_TOKENS=1000
ANALYZER_TIMEOUT=30

# API 配置
DOUBAO_API_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_API_KEY=your_doubao_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_openai_api_key

# Git 配置
GIT_REPO_URL=https://github.com/your/repo.git
GITHUB_TOKEN=your_github_token

# 飞书配置
FEISHU_APP_ID=your_feishu_app_id
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_WEBHOOK_URL=your_feishu_webhook_url

# 监控配置
LOG_PATH=./app.log
MONITOR_LOG_PATTERN=ERROR|Exception|Traceback

# 运行时配置
MAX_ITERATIONS=3
```

### 运行

1. 启动 Webhook 服务：

```bash
python -m web_service_guard.api.webhook
```

2. 触发修复：

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{"service": "test_service", "repo": "your/repo", "branch": "main"}'
```

## 核心功能

### 1. 异常感知
- 自动收集日志中的 Traceback
- 生成标准化 BugEvent

### 2. 根因分析
- 基于 LLM 分析错误原因
- 生成详细的修复计划
- 评估修复风险等级

### 3. 自动修复
- 根据修复计划修改代码
- 支持代码备份
- 生成修复 diff

### 4. 测试验证
- 运行定向测试
- 运行冒烟测试
- 验证修复是否成功

### 5. 交付通知
- 自动创建 PR
- 发送飞书通知
- 记录修复过程

## 安全与护栏

- **可观测**：所有阶段、Agent 调用、工具调用和结果都可追踪
- **可控**：自动修改必须受运行时护栏、权限和门禁约束
- **可回退**：所有改动通过 Git 分支和 PR 交付
- **可验证**：测试未通过不得进入 PR 阶段
- **可扩展**：后续可扩展更多触发源、更多工具和更多服务

## 开发指南

### 新增 AgentTool

1. 在 `agent_tools/` 目录下创建新的 AgentTool 类
2. 继承 `AgentTool` 基类
3. 实现 `invoke` 方法

### 新增 PrimitiveTool

1. 在 `primitive_tools/` 目录下创建新的 PrimitiveTool 类
2. 继承 `PrimitiveTool` 基类
3. 实现 `execute` 方法

### 测试

```bash
pytest tests/
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License