# 基于 Agent 的服务自动化修复系统 SPEC

> 文档同步说明：本 SPEC 已按当前仓库实现同步更新至 **2026-05-02**。  
> 其中：
> - 已真实落地的能力，会在对应章节明确标注“当前实现同步”
> - 尚未实现或仍属后续规划的内容，仍保留为设计目标，不视为当前代码已具备

## 1. 项目目标

构建一个面向简单 Web 服务的自动化修复系统。当服务运行报错时，系统自动完成以下链路：

1. 监控异常并获取 Traceback。
2. 基于 Agent + Tool Use 分析根因。
3. 自动修改代码并执行测试验证。
4. 修复成功后自动创建 PR。
5. 通过飞书卡片通知开发者：“我发现了一个 Bug 并已为您修复，请 Review”。

系统目标不是替代开发者，而是建立一条高可信、可审计、可回滚的人机协同修复链路。

---

## 2. 设计范围与边界

### 2.1 当前范围

- 仅处理“服务运行时报错”场景。
- 仅处理简单 Web 服务。
- 仅处理可复现、可测试的代码类错误。
- 仅自动提交 PR，不自动合并。

### 2.2 暂不处理

- 新 Bug 提单驱动修复。
- 数据库迁移、批量数据修复、支付链路、鉴权高风险链路。
- 无 Traceback、无明确代码定位、无可执行测试的复杂问题。

### 2.3 核心原则

- 可观测：所有阶段、Agent 调用、工具调用和结果都可追踪。
- 可控：自动修改必须受运行时护栏、权限和门禁约束。
- 可回退：所有改动通过 Git 分支和 PR 交付。
- 可验证：测试未通过不得进入 PR 阶段。
- 可扩展：后续可扩展更多触发源、更多工具和更多服务。

---

## 3. 总体架构

系统采用三阶段架构：

```text
阶段一：异常感知与 Traceback 获取
    -> 产出标准化修复任务 + 准备好的工作区

阶段二：基于 Tool Use 的循环式自动修复
    -> Explore / Plan / Execute / Verify
    -> 由 Repair Orchestrator 编排

阶段三：PR 提交与飞书通知
    -> 创建 PR
    -> 发送飞书卡片
```

### 3.1 分层结构

```text
Trigger Layer
  -> Sentinel Agent

Repair Workflow Layer
  -> Repair Orchestrator
     -> AgentTool(agent_type=explore)
     -> AgentTool(agent_type=plan)
     -> AgentTool(agent_type=execute)
     -> AgentTool(agent_type=verify)

Primitive Tool Layer
  -> Read
  -> Grep
  -> Glob
  -> Edit Code
  -> Bash
  -> Git Commit
  -> Feishu Notify

Delivery Layer
  -> Git Platform
  -> Feishu
```

---

## 4. 三阶段工作流

## 4.1 第一阶段：异常感知与 Traceback 获取

### 目标

将线上报错转成结构化修复任务，而不是直接进入 LLM 修复。

### 输入

- 服务异常告警
- 健康检查失败
- 日志中出现异常栈

### 处理步骤

1. 监控系统发现服务报错。
2. Sentinel Agent 获取对应时间窗口内的 Traceback。
3. 提取基础事件信息：
   - 服务名
   - 错误摘要
   - Traceback 原文
   - 触发时间
   - 仓库信息
   - 目标分支
4. 生成标准化修复任务，交给第二阶段。

### 输出

- `BugEvent`
- 原始 Traceback
- 基础仓库上下文

### 失败处理

- 无有效 Traceback：直接转人工
- 无法定位仓库或分支：直接转人工

---

## 4.2 第二阶段：基于 Tool Use 的循环式自动修复工作流

### 目标

围绕一次异常修复任务，完成“上下文收集 -> 根因分析 -> 修复计划 -> 代码修改 -> 测试验证”的循环式闭环。

### 核心特征

- 不是一次性的 LLM pipeline。
- 是由主 Agent 驱动的循环式修复过程。
- 外层由 `Repair Orchestrator` 采用 ReAct 模式自主决定下一步调用哪个 `AgentTool`。
- 内层通过 `AgentTool` 委派专用子 Agent。
- 子 Agent 再调用底层 `Primitive Tools` 与环境交互。



### 关键门禁

- 没有有效 Traceback，不进入修复流程。
- 没有定位到明确相关代码，不自动修改。
- 无法形成可执行修复计划，不自动修改。
- 测试不通过，不允许进入 PR 阶段。
- 超过最大迭代次数，转人工处理。
- 高风险模块或高风险修复方案，默认人工 Review。

### 迭代规则

- 第二阶段是循环式修复，不是一轮完成。
- 当 `Verification Agent` 返回失败结果时，工作流重新进入根因分析。
- 首版明确最大修复轮次为 `3` 轮。
- 任一轮命中高风险策略，立即停止自动修复。

---

## 4.3 第三阶段：PR 提交与飞书通知

### 目标

将验证通过的修复结果纳入标准研发流程，并通知开发者 Review。

### 处理步骤

1. 创建修复分支。
2. 提交代码并创建 PR。
3. 在 PR 描述中附带：
   - 错误摘要
   - 根因说明
   - 修复说明
   - 测试结果
4. 发送飞书卡片通知开发者。


### 失败处理

- PR 创建失败：转人工并保留本地修复结果
- 飞书通知失败：写入补偿队列稍后重发

---

## 5. 第二阶段实现方式

## 5.1 实现模式

第二阶段采用：

- `ReAct` 作为主编排模式
- `AgentTool` 作为高阶委派接口
- `Primitive Tools` 作为环境交互单元

这套设计参考 Claude Code 的工程模式，但按当前项目目标进行裁剪。

### Claude Code 借鉴说明

本项目第二阶段并非复刻 Claude Code，而是借鉴其公开可确认的 Agent 工程模式。当前可确认的关键点包括：

- 主 Agent 通过 `Agent` 工具委派 subagent。
- subagent 有独立上下文，只返回最终结果给父 Agent。
- subagent 由 `AgentDefinition` 定义，核心字段包括 `description`、`prompt`、`tools`、`disallowedTools`、`model`、`maxTurns`、`permissionMode`。
- subagent 不能继续再生成 subagent。
- 只读探索适合交给专门子 Agent，主上下文保持干净。
- GitHub issue 中仍可见大量 `Task` 命名和 `subagent_type` 字段，因此实现上需要兼容 `Task/Agent` 两种表述。

对当前项目最有价值的借鉴不是 Claude Code 的 UI 或 CLI 外壳，而是它在以下方面的建模思路：

- 主 Agent 与子 Agent 的职责分层
- 子 Agent 与底层工具的解耦
- 上下文隔离
- 高阶委派工具
- 状态流与可观测性

## 5.2 分层关系

```text
Repair Orchestrator
  -> AgentTool (agent_type=explore|plan|execute|verify)

Explore / Plan / Execute / Verify Agent
  -> Read
  -> Grep
  -> Glob
  -> Edit Code
  -> Bash
```

### 5.2.1 当前实现同步（2026-05-02）

当前仓库中的第二阶段已经落地为以下真实结构：

```text
Main-thread Orchestrator
  -> runtime/orchestrator.py
  -> 通过主线程 LLM 决定是否调用 agent 工具

AgentTool
  -> tools/agent_tool.py
  -> 统一承载 explore / plan / execute / verify 四类子任务委派

Sub-agent Runtime
  -> runtime/engine.py
  -> runtime/subagent_loop.py

Supporting Runtime
  -> runtime/runtime_state.py
  -> runtime/tool_resolution.py
  -> runtime/permission_semantics.py
```

这意味着当前实现中：

- 主线程只暴露一个高阶工具：`agent`
- 四类子 Agent 不再作为四个独立 Python Tool 类存在，而是作为 `AgentTool` 的四类 `agent_type`
- 子 Agent 的工具池、权限模式、结果结构和生命周期都已经在第二阶段内部收敛

## 5.3 Repair Orchestrator

### 职责

- 负责第二阶段的主循环推进
- 判断当前上下文缺失的信息
- 决定是否调用 `agent` 工具，以及调用哪个 `agent_type`
- 接收子 Agent 返回结果
- 决定继续、重试、转人工或终止

### ReAct 行为

- `Thought`：当前处于哪个状态，还缺什么
- `Action`：调用某个 `AgentTool`
- `Observation`：接收结构化结果
- `Decision`：进入下一状态或转人工

### 约束

- 不直接承担根因分析
- 不直接修改代码
- 不直接运行测试
- 必须遵守护栏规则，不可越权或无限循环

### 当前实现同步（2026-05-02）

当前 `runtime/orchestrator.py` 已经按主线程 LLM 模式实现，而不是固定顺序状态机：

- 主线程也使用 `LLMAdapter`
- 主线程每轮只允许：
  - 调用 `agent`
  - 返回 `final`
- 主线程将 `AgentToolResult` 写回为正式 `tool_result` observation
- 主线程当前会显式消费以下结构化结果：
  - `explore.output.context_completeness`
  - `plan.output.repair_plan`
  - `plan.output.need_human_review`
  - `execute.output.patch_result`
  - `execute.output.need_replan`
  - `verify.output.verification_result`

当前主线程的最终判断优先使用结构化字段，而不是依赖自然语言 `summary` 猜测。

## 5.4 AgentTool 与 Primitive Tool 的区别

### AgentTool

用于完成完整子任务，是高阶委派工具，例如：

- 收集修复上下文
- 输出根因和修复计划
- 执行补丁修改
- 验证一轮修复结果

### Primitive Tool

用于执行单一环境动作，例如：

- 读取日志
- 读取代码
- 修改代码
- 运行测试

### 约束

- 主 Agent 优先调用 `AgentTool`
- 子 Agent 在内部调用 `Primitive Tool`
- `Read` / `Grep` / `Glob` / `Bash` 可并发
- `Edit Code` / `Git Commit` 必须串行

---

## 6. 第二阶段 Agent 规格

## 6.0 AgentTool I/O 设计原则

为了让第二阶段真正可执行，四个 `AgentTool` 的输入输出协议需要先于 `schemas` 细化。这里采用的原则是：

- 协议应围绕工作流状态，而不是围绕当前临时 schema 设计。
- 父 Agent 传给子 Agent 的输入必须是“任务级输入”，不是底层工具参数。
- 子 Agent 返回给父 Agent 的输出必须是“结构化阶段结果”，而不是自然语言长文。
- 每个 `AgentTool` 都必须返回统一的执行元信息，便于审计、重试和状态推进。

### 通用调用包结构

所有 `AgentTool` 调用统一遵循以下调用包。这里展示的是**字段规格**，不是示例值：

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "input": "object",
  "constraints": {
    "max_turns": "integer",
    "read_only": "boolean",
    "allowed_tools": ["string"],
    "permission_mode": "string"
  }
}
```

### 通用返回包结构

所有 `AgentTool` 返回统一遵循以下结果包。这里展示的是**字段规格**，不是示例值：

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "status": "string",
  "stop_reason": "string",
  "summary": "string",
  "output": "object",
  "artifacts": ["string"],
  "allowed_tools": ["string"],
  "permission_mode": "string",
  "read_only": "boolean",
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "stage": "string",
      "source": "string"
    }
  ]
}
```

### 通用字段说明

- `run_id`：一次完整修复任务的唯一标识。
- `iteration`：当前第几轮修复尝试。
- `summary`：短摘要，供主Agent和审计系统快速阅读。
- `status`：当前子 Agent 最终状态，当前实现为 `completed | failed | max_turns_reached`
- `stop_reason`：子 Agent 的停止原因
- `output`：该AgentTool的核心结构化结果。
- `artifacts`：补充产物，例如文件路径、测试命令、diff摘要。
- `errors`：结构化错误列表。

### 当前接口同步（2026-05-02）

当前仓库中 `AgentTool` 同时支持两层调用方式：

1. 兼容式调用：
   - `execute(agent_type=..., user_prompt=...)`
2. 任务级调用：
   - `invoke(payload)`

其中 `invoke(payload)` 已被 `runtime/orchestrator.py` 采用，用于统一主线程到子 Agent 的任务级委派。

### Claude Code 风格的兼容思路

参考 Claude Code 官方 SDK，subagent 的核心是：

- 父 Agent 通过一个“委派动作”传入 prompt 和必要上下文
- 子 Agent 在独立上下文中运行
- 中间工具调用不返回父上下文
- 父 Agent 只接收最终结果

因此本项目中的 `AgentTool` 也遵循同一原则：

- 输入必须包含完成该子任务所需的全部上下文
- 输出必须是最终结果，而不是中间步骤流
- 子 Agent的工具调用细节由审计层记录，而不是塞回父Agent的主上下文

## 6.1 Explore Agent

### 职责

- 读取 Traceback
- 定位本地代码、函数和调用位置
- 查找相关测试
- 构建结构化修复上下文

### 输入

- `traceback`
- `service`
- `repo`
- `branch`
- 可选 `time_window`
- 可选 `entry_request`

### 输出

- `RepairContext`
- 可疑文件列表
- 相关测试列表
- 上下文完整度说明

### `ExploreAgentTool` 输入协议

> 当前实现映射：此处概念上的 `ExploreAgentTool` 在代码中对应  
> `tools/agent_tool.py` 的 `AgentTool.invoke(payload)`，其中 `payload["agent_tool"] == "explore"`。

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "input": {
    "traceback": "string",
    "service": "string",
    "repo": "string",
    "branch": "string",
    "time_window": "string | null",
    "entry_request": "object | null"
  },
  "constraints": {
    "max_turns": "integer",
    "read_only": "boolean",
    "allowed_tools": ["ReadLog", "ReadCode", "SearchCode"]
  }
}
```

### `ExploreAgentTool` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "summary": "string",
  "output": {
    "repair_context": {
      "bug_summary": "string",
      "traceback": "string",
      "suspect_files": ["string"],
      "code_snippets": ["object"],
      "related_tests": ["string"],
      "recent_commits": ["string"]
    },
    "suspect_files": ["string"],
    "related_tests": ["string"],
    "context_completeness": "string"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 可调用工具

- `Read`
- `Grep`
- `Glob`

### 约束

- 只读
- 不做根因结论
- 不修改代码
- 若上下文不足，必须显式返回 `context_completeness = insufficient`

### 当前实现同步（2026-05-02）

当前主线程 orchestrator 已经显式依赖以下字段：

- `output.repair_context.code_snippets`
- `output.suspect_files`
- `output.context_completeness`

当前实现中，只有在同时具备：

- `suspect_files`
- `code_snippets`

时，`context_completeness` 才会被判定为 `sufficient`；否则主线程会直接进入 `NEED_HUMAN_REVIEW`。

## 6.2 Plan Agent

### 职责

- 单独执行根因分析
- 给出证据和风险等级
- 生成修复计划和测试建议

### 输入

- `RepairContext`

### 输出

- 根因分析结果
- `RepairPlan`
- 建议执行测试
- 风险等级

### `PlanAgentTool` 输入协议

> 当前实现映射：此处概念上的 `PlanAgentTool` 在代码中对应  
> `tools/agent_tool.py` 的 `AgentTool.invoke(payload)`，其中 `payload["agent_tool"] == "plan"`。

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "input": {
    "repair_context": {
      "bug_summary": "string",
      "traceback": "string",
      "suspect_files": ["string"],
      "code_snippets": ["object"],
      "related_tests": ["string"],
      "recent_commits": ["string"]
    }
  },
  "constraints": {
    "max_turns": "integer",
    "read_only": "boolean",
    "allowed_tools": ["string"]
  }
}
```

### `PlanAgentTool` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "summary": "string",
  "output": {
    "root_cause_analysis": {
      "root_cause": "string",
      "evidence": ["string"],
      "risk_level": "string"
    },
    "repair_plan": {
      "root_cause": "string",
      "fix_plan": ["string"],
      "files_to_modify": ["string"],
      "risk_level": "string"
    },
    "tests_to_run": ["string"],
    "need_human_review": "boolean"
  },
  "next_recommendation": "string",
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 可调用工具

- 以推理为主
- 默认不调用写入工具

### 约束

- 不修改代码
- 不直接运行测试
- 根因不明确时应明确返回证据不足或计划不可执行
- `root_cause_analysis` 与 `repair_plan` 必须分开返回
- 当缺乏明确证据或无法形成可执行计划时应返回 `need_human_review`

### 当前实现同步（2026-05-02）

当前主线程 orchestrator 已经显式依赖以下字段：

- `output.root_cause_analysis.evidence`
- `output.repair_plan.files_to_modify`
- `output.need_human_review`

当前实现中，若满足以下任一条件，主线程会直接进入 `NEED_HUMAN_REVIEW`：

- `need_human_review = true`
- `files_to_modify` 为空
- `evidence` 为空

## 6.3 Execute Agent

### 职责

- 按修复计划执行代码修改
- 必要时补充测试

### 输入

- `RepairPlan`
- 修改范围

### 输出

- 补丁应用结果
- 实际修改文件列表
- 补充测试说明

### `ExecuteAgentTool` 输入协议

> 当前实现映射：此处概念上的 `ExecuteAgentTool` 在代码中对应  
> `tools/agent_tool.py` 的 `AgentTool.invoke(payload)`，其中 `payload["agent_tool"] == "execute"`。

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "input": {
    "repair_plan": {
      "root_cause": "string",
      "fix_plan": ["string"],
      "files_to_modify": ["string"],
      "risk_level": "string"
    }
  },
  "constraints": {
    "max_turns": "integer",
    "read_only": "boolean",
    "allowed_tools": ["ReadCode", "EditCode"]
  }
}
```

### `ExecuteAgentTool` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "summary": "string",
  "output": {
    "patch_result": {
      "modified_files": ["string"],
      "patch_summary": ["string"],
      "test_updates": ["string"]
    },
    "plan_deviation": {
      "deviated": "boolean",
      "reason": "string | null"
    },
    "need_replan": "boolean"
  },
  "next_recommendation": "string",
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 可调用工具

- `Edit Code`
- 必要时 `Read`

### 约束

- 不允许无边界扩大修改范围
- 若计划与代码现实不匹配，返回主 Agent 重新规划
- 不允许自行决定提交 Git
- 不允许自行进入验证结论

### 当前实现同步（2026-05-02）

当前主线程 orchestrator 已经显式依赖以下字段：

- `output.patch_result.modified_files`
- `output.plan_deviation`
- `output.need_replan`

当前实现中，若满足以下任一条件，主线程会直接进入 `NEED_HUMAN_REVIEW`：

- `need_replan = true`
- `modified_files` 为空

## 6.4 Verification Agent

### 职责

- 运行定向测试
- 运行基础回归验证
- 判断修复是否成立
- 输出下一步建议

### 输入

- 修复后的代码状态
- 建议执行的测试

### 输出

- 测试结果
- 新的失败信息
- 是否建议继续迭代

### `VerifyAgentTool` 输入协议

> 当前实现映射：此处概念上的 `VerifyAgentTool` 在代码中对应  
> `tools/agent_tool.py` 的 `AgentTool.invoke(payload)`，其中 `payload["agent_tool"] == "verify"`。

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "input": {
    "modified_files": ["string"],
    "tests_to_run": ["string"],
    "smoke_tests": ["string"]
  },
  "constraints": {
    "max_turns": "integer",
    "read_only": "boolean",
    "allowed_tools": ["Read", "Grep", "Glob", "Bash"]
  }
}
```

### `VerifyAgentTool` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "agent_tool": "string",
  "summary": "string",
  "output": {
    "verification_result": {
      "verdict": "PASS | FAIL | PARTIAL",
      "targeted_tests_passed": "boolean",
      "smoke_tests_passed": "boolean",
      "failed_tests": ["string"],
      "failure_logs": ["string"],
      "bash_checks": [
        {
          "command": "string | null",
          "exit_code": "integer | null",
          "status": "completed | failed",
          "stdout": "string",
          "stderr": "string",
          "combined_output": "string",
          "duration_sec": "number | null"
        }
      ],
      "ready_for_pr": "boolean"
    }
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 可调用工具

- `Read`
- `Grep`
- `Glob`
- `Bash`

### 约束

- 目标是验证修复是否真的成立
- 不为修改背书
- 当测试失败时必须返回结构化失败日志，供下一轮重新分析

### 当前实现同步（2026-05-02）

当前 `verify` 已经成为第二阶段主链路的正式收口点，当前实现要求：

- `output.verification_result.verdict` 必须存在
- `verdict` 仅允许：
  - `PASS`
  - `FAIL`
  - `PARTIAL`
- `ready_for_pr` 必须和 `verdict` 保持一致
- `summary` 中继续保留 Claude Code 风格文本 verdict：
  - `VERDICT: PASS`
  - `VERDICT: FAIL`
  - `VERDICT: PARTIAL`
- 当存在 `bash_checks` 时，`verify` 必须优先消费其结构化结果，而不是仅依赖 `summary`
- `bash_checks.exit_code != 0` 或 `bash_checks.status == "failed"` 必须导致 `verification_result.verdict = FAIL`

当前主线程 orchestrator 优先消费结构化 `verification_result`，而不是依赖 `summary` 猜测最终状态。

## 6.5 Orchestrator 决策协议

虽然 `Repair Orchestrator` 不直接修改代码，但它必须统一消费四个 `AgentTool` 的结果，并输出显式决策。建议其内部统一采用如下决策结构：

```json
{
  "run_id": "string",
  "iteration": "integer",
  "latest_result_from":  "agent(explore) | agent(plan) | agent(execute) | agent(verify)",
  "decision": "continue | retry | escalate | terminate",
  "reason": "string"
}
```

该结构不一定第一时间落成独立 schema，但必须在实现中作为显式契约存在。

---

## 7. Tool Use 规格

## 7.1 Primitive Tool 设计原则

Primitive Tool 是环境交互的最小执行单元。它们不负责复杂任务语义，只负责完成单一动作，并返回结构化结果供 `AgentTool` 消费。

设计原则如下：

- 一个工具只解决一种环境动作。
- 工具结果必须结构化，不能只返回自然语言。
- 工具错误必须可判断、可重试、可审计。
- 工具接口必须独立于具体 Agent，便于复用和替换。

## 7.2 通用调用包结构

所有 `Primitive Tool` 调用统一遵循以下调用包。这里展示的是**字段规格**，不是示例值：

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": "object",
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

## 7.3 通用返回包结构

所有 `Primitive Tool` 返回统一遵循以下结果包。这里展示的是**字段规格**，不是示例值：

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": "object",
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 通用字段说明

- `tool_name`：工具名，固定值，不允许动态扩展。
- `invoked_by`：哪个 `AgentTool` 调用了该工具。
- `input`：本次工具执行参数。
- `constraints`：超时、只读、是否允许重试等执行约束。
- `status`：成功或失败。
- `summary`：本次执行摘要。
- `output`：结构化执行结果。
- `artifacts`：产物，例如文件路径、测试命令、diff 摘要。
- `errors`：错误列表，错误必须结构化。

## 7.4 `ReadLog` 协议

> 当前实现说明（2026-05-02）：`ReadLog` 仍保留在设计中，但当前仓库尚未实现其真实工具能力。  
> 当前方向已开始向 Claude Code 风格的通用 `Read` / `Grep` / `Glob` 工具模型收敛，其中这三个 primitive tools 都已经在仓库中落地，`ReadLog` / `ReadCode` 将逐步退居兼容层或设计占位。

### 能力

- 读取日志文件、异常栈、日志平台输出
- 支持按时间窗口过滤
- 支持按关键字或请求 ID 聚合

### `ReadLog` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "service": "string",
    "source": "string",
    "path": "string | null",
    "time_window": "string | null",
    "keyword": "string | null",
    "request_id": "string | null",
    "max_lines": "integer | null"
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `ReadLog` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "traceback_blocks": ["string"],
    "matched_lines": "integer",
    "source": "string"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 只读
- 允许并发
- 不负责解释错误根因

## 7.5 `ReadCode` 协议

> 当前实现说明（2026-05-02）：`ReadCode` 仍保留在设计中，但当前仓库已经开始引入更通用的 `Read` 工具模型。  
> 当前 `read_code.py` 仍保留为兼容占位，后续将逐步迁移到 `Read` / `Grep` / `Glob` 的组合能力上。

### 能力

- 按文件、函数、行号范围读取代码
- 支持查找相关测试和配置

### `ReadCode` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "file": "string",
    "start_line": "integer | null",
    "end_line": "integer | null",
    "symbol": "string | null",
    "include_related_tests": "boolean"
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `ReadCode` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "file": "string",
    "start_line": "integer | null",
    "end_line": "integer | null",
    "content": "string",
    "related_tests": ["string"]
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 只读
- 允许并发
- 不负责修改文件

## 7.6 `EditCode` 协议

### 能力

- 在受控范围内修改指定文件
- 保留 diff
- 支持最小补丁写入

### `EditCode` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "file": "string",
    "edit_type": "string",
    "patch": "string",
    "reason": "string"
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `EditCode` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "modified_file": "string",
    "diff_summary": ["string"],
    "lines_added": "integer",
    "lines_removed": "integer"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 写入工具，必须串行
- 不允许超出门禁范围修改文件
- 不允许自行创建 Git 提交

## 7.7 `RunTest` / `Bash` 协议

> 当前实现说明（2026-05-02）：设计层仍保留 `RunTest` 这个更强语义化工具名，但当前仓库已经真实落地的是更接近 Claude Code 风格的 `Bash` primitive tool。  
> 当前 `verify` 实际通过受限 `bash` 命令执行测试、读取输出，并消费其结构化结果形成 `verification_result`。

### 能力

- 执行指定测试命令
- 收集测试日志与失败用例
- 支持先局部测试再回归测试
- 支持必要的只读辅助命令，例如 `pwd`、`ls`、`cat`、`head`、`tail`、`echo`

### 当前实现对应关系

- 设计语义：`RunTest`
- 当前工具名：`bash`
- 当前输入参数：
  - `command`
  - `working_dir`
  - `timeout_sec`
- 当前执行约束：
  - 仅允许第一阶段 allowlist 内命令
  - 显式拒绝危险前缀，例如 `rm`、`sudo`、`chmod`、`chown`、`mv`、`cp`

### `RunTest` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "command": "string",
    "working_dir": "string",
    "timeout_sec": "integer",
    "test_scope": "string"
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `RunTest` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "passed": "boolean",
    "exit_code": "integer",
    "failed_tests": ["string"],
    "log_excerpt": ["string"],
    "duration_sec": "number"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 当前 `bash` 为只读受限执行工具，可并发
- 测试失败必须返回结构化失败结果
- 测试无法运行时必须返回工具错误而不是空结果

## 7.8 `GitCommit` 协议

### 能力

- 创建分支
- 提交代码
- 推送远程
- 创建 PR

### `GitCommit` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "branch_name": "string",
    "commit_message": "string",
    "pr_title": "string",
    "pr_body": "string"
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `GitCommit` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "branch_name": "string",
    "commit_hash": "string",
    "pr_url": "string"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 仅在第三阶段使用
- 不允许直接推主分支
- 必须受 Git 权限策略约束

## 7.9 `FeishuNotify` 协议

### 能力

- 构造飞书卡片
- 发送通知
- 返回投递结果

### `FeishuNotify` 输入协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "invoked_by": "string",
  "input": {
    "webhook_url": "string",
    "title": "string",
    "body": {
      "service": "string",
      "summary": "string",
      "root_cause": "string",
      "pr_url": "string"
    }
  },
  "constraints": {
    "timeout_sec": "integer",
    "read_only": "boolean",
    "retryable": "boolean"
  }
}
```

### `FeishuNotify` 输出协议

```json
{
  "run_id": "string",
  "iteration": "integer",
  "tool_name": "string",
  "status": "string",
  "summary": "string",
  "output": {
    "delivered": "boolean",
    "message_id": "string",
    "recipient": "string"
  },
  "artifacts": ["string"],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "retryable": "boolean",
      "source": "string"
    }
  ]
}
```

### 约束

- 仅在第三阶段使用
- 发送失败时必须支持补偿重试

## 7.10 工具权限约束

- 只读工具允许并发：`Read`、`Grep`、`Glob`、`Bash`
- 写入工具必须串行：`EditCode`、`GitCommit`、`FeishuNotify`
- Git 类工具只在第三阶段使用
- 危险命令和未授权目录访问必须禁止

## 7.11 当前 Primitive Tool 重构方向（2026-05-02）

为了贴近 Claude Code 的工具设计哲学，当前项目已明确不再长期围绕“专用日志读取 / 专用代码读取”继续建模，而是逐步收敛为更通用的底层能力工具。

### 当前目标模型

- `Read`
- `Grep`
- `Glob`
- `EditCode`
- `Bash`

### 当前已落地

当前仓库已新增：

- `tools/FileReadTool/`
- `tools/GrepTool/`
- `tools/GlobTool/`
- `tools/EditCodeTool/`
- `tools/BashTool/`

当前能力状态：

- `Read`
  - 工具名为 `read`
  - 仅支持文本文件读取
  - 支持：
    - `file_path`
    - `offset`
    - `limit`
  - 明确约束：
    - 必须是绝对路径
    - 不允许目录读取
    - 不允许二进制文件
    - 默认最大读取行数 `200`
    - 硬上限 `2000`
- `Grep`
  - 工具名为 `grep`
  - 支持按正则搜索文本内容
  - 支持：
    - `pattern`
    - `path`
    - `glob`
    - `output_mode`
    - `context_lines`
    - `head_limit`
    - `offset`
  - 当前输出模式包括：
    - `files_with_matches`
    - `count`
    - `content`
- `Glob`
  - 工具名为 `glob`
  - 支持按 glob pattern 搜索文件
  - 支持：
    - `pattern`
    - `path`
    - `head_limit`
    - `offset`
- `EditCode`
  - 工具名为 `edit`
  - 支持基于精确字符串替换修改文本文件
  - 支持：
    - `file_path`
    - `old_string`
    - `new_string`
    - `replace_all`
  - 明确约束：
    - 修改前必须先由 `Read` 读取同一文件
    - 文件发生变更后必须重新读取
    - 不允许目录、设备路径和二进制文件
- `Bash`
  - 工具名为 `bash`
  - 支持受限 shell 命令执行
  - 支持：
    - `command`
    - `working_dir`
    - `timeout_sec`
  - 返回结构化字段：
    - `exit_code`
    - `stdout`
    - `stderr`
    - `combined_output`
    - `duration_sec`
  - 当前主要用于 `verify` 阶段执行测试与只读检查

当前实现中，`FileReadTool`、`GrepTool`、`GlobTool`、`EditCodeTool`、`BashTool` 已可直接进入子 Agent 工具池并参与第二阶段调用链。第二阶段当前真实使用的是这五个 primitive tools。

### 当前未完全收口

以下方向仍处于迁移中，而不是最终形态：

- `ReadLog`
- `ReadCode`
- 更细粒度的 primitive tool 协议文档统一

因此在当前代码状态下，第二阶段的五个核心 primitive tools 已经全部落地并通过仓库测试；仍处在迁移中的主要是旧命名工具文档与兼容层，而不是主链路能力缺失。

---

## 8. 数据结构策略

当前不将 `schemas` 作为优先主线，而是将其视为支撑工作流的过渡层。

### 当前保留的最小结构

- `BugEvent`
- `RepairContext`
- `RepairPlan`

### 当前策略

- 不继续围绕旧 schema 做大规模扩展
- 先以工作流和 `AgentTool` 输入输出为主
- 后续根据真实接口反推和重构 schema

### 未来需要补充的结构方向

- 修复运行态
- Agent 调用记录
- Tool 调用记录
- 验证结果
- Orchestrator 决策结果

---

## 9. 模块划分

## 9.1 Agent 划分

- `Sentinel Agent`
- `Repair Orchestrator`
- `Explore Agent`
- `Plan Agent`
- `Execute Agent`
- `Verification Agent`
- `Delivery Agent`

## 9.2 各 Agent 定位

### `Sentinel Agent`

- 监听异常事件
- 获取 Traceback
- 生成标准化修复任务

### `Repair Orchestrator`

- 第二阶段主控 Agent
- 负责编排和门禁

### `Delivery Agent`

- 创建 PR
- 发送飞书卡片

---

## 10. 目录结构建议

本章基于**当前真实项目结构**说明目录设计。当前代码已经将“工具体系”重构为统一的 `tools/` 层，并将“子 Agent 执行引擎”抽离到 `runtime/engine.py`。因此目录说明需要以当前结构为准，而不是此前的过渡方案。

### 10.1 当前完整项目目录结构

```text
web_service_guard/
├── __init__.py
├── config.py
├── enums.py
├── errors.py
├── policy.py
├── audit.py
│
├── runtime/
│   ├── __init__.py
│   ├── engine.py
│   ├── orchestrator.py
│   ├── permission_semantics.py
│   ├── runtime_state.py
│   ├── subagent_loop.py
│   └── tool_resolution.py
│
├── tools/
│   ├── __init__.py
│   ├── base.py
│   ├── agent_tool.py
│   ├── read_log.py
│   ├── read_code.py
│   ├── edit_code.py
│   ├── run_test.py
│   ├── git_commit.py
│   └── feishu_notify.py
│
├── agents/
│   ├── __init__.py
│   ├── registry.py
│   └── sentinel_agent.py
│
├── workflow/
│   ├── __init__.py
│   ├── repair_pipeline.py
│   ├── stage_router.py
│   └── recovery.py
│
├── monitoring/
│   ├── __init__.py
│   ├── event_detector.py
│   ├── traceback_collector.py
│   └── healthcheck_adapter.py
│
├── delivery/
│   ├── __init__.py
│   ├── pr_service.py
│   └── notify_service.py
│
├── integrations/
│   ├── __init__.py
│   ├── log_client.py
│   ├── github_client.py
│   └── feishu_client.py
│
├── schemas/
│   ├── __init__.py
│   ├── agent_messages.py
│   ├── tool_result.py
│   ├── run_result.py
│   └── audit_event.py
│
├── api/
│   ├── __init__.py
│   └── webhook.py
│
├── tests/
│   ├── fixtures/
│   │   ├── tracebacks/
│   │   ├── cases/
│   │   └── repos/
│   ├── test_pipeline.py
│   ├── test_orchestrator.py
│   ├── test_agent_tools.py
│   ├── test_primitive_tools.py
│   ├── test_policy.py
│   └── test_audit.py
│
├── docs/
│   ├── DEVELOPMENT_ORDER.md
│   ├── prompts/
│   ├── examples/
│   └── diagrams/
│
├── pyproject.toml
└── ARCHITECTURE_DESIGN.md
```

### 10.2 三阶段工作流如何映射到当前目录

#### 第一阶段：异常感知与 Traceback 获取

主要对应：

- `monitoring/`
- `agents/sentinel_agent.py`
- `integrations/log_client.py`
- `api/webhook.py`

职责是：

- 发现服务异常
- 采集 Traceback
- 生成标准化修复任务
- 进入第二阶段修复流程

#### 第二阶段：基于 Tool Use 的循环式自动修复

主要对应：

- `runtime/`
- `tools/`
- `agents/registry.py`

职责是：

- `runtime/orchestrator.py` 运行主 Agent loop
- `runtime/engine.py` 执行被 fork 出来的子 Agent loop
- `tools/agent_tool.py` 作为主 Agent 调用子 Agent 的高阶工具入口
- `tools/*.py` 提供原子工具能力
- `agents/registry.py` 提供各类子 Agent 的定义与配置

这一层是当前项目的核心，必须保持 Claude Code 风格：

- 主 Agent 决定下一步做什么
- 通过 `AgentTool` fork 子 Agent
- 子 Agent 在独立上下文中调用允许的工具
- 子 Agent 只把最终结果返回给主 Agent

#### 第三阶段：PR 提交与飞书通知

主要对应：

- `delivery/`
- `tools/git_commit.py`
- `tools/feishu_notify.py`
- `integrations/github_client.py`
- `integrations/feishu_client.py`

职责是：

- 创建分支、提交代码、创建 PR
- 发送飞书通知
- 做交付层补偿和收敛

### 10.3 `runtime/` 目录职责

`runtime/` 是第二阶段主循环的运行时核心目录。

#### `runtime/engine.py`

负责运行**被 fork 出来的子 Agent loop**。  
当前实现要点包括：

- 接收 `system_prompt`
- 接收 `user_prompt`
- 接收允许使用的工具池
- 调用 `LLMAdapter`
- 处理 `tool` / `final` 两类 turn
- 返回 `AgentRunResult`

它的定位更接近 Claude Code 风格的 `runAgent` 执行引擎，而不是系统级 workflow。

#### `runtime/orchestrator.py`

负责第二阶段主线程 Agent 的同步运行入口。  
当前实现要点包括：

- 接收结构化修复任务输入
- 维护主线程消息历史
- 通过主线程 LLM 决定是否调用 `agent`
- 将 `AgentToolResult` 写回为正式 `tool_result`
- 根据结构化 observation 决定最终结果

当前实现中，`runtime/orchestrator.py` 已经收拢了外层主循环推进逻辑，不再单独依赖 `runtime/loop.py` 或 `runtime/decisions.py`。

#### `runtime/subagent_loop.py`

负责承载单个子 Agent 的内部轻量 loop：

- 调用子 Agent LLM
- 处理 `tool` / `final`
- 回流 `tool_result`
- 维护子 Agent 内部 `messages / tool_calls / tool_results`

#### `runtime/runtime_state.py`

定义主 Agent loop 的统一运行时状态容器。  
它服务于：

- 消息历史
- 工具上下文
- 当前轮次
- 最近一次结果
- 最终退出信息
- 审计引用

#### `runtime/tool_resolution.py`

负责按照 `AgentDefinition` 解析子 Agent 可用的工具池，并统一处理：

- `tools`
- `disallowed_tools`
- `read_only`
- `permission_mode`

#### `runtime/permission_semantics.py`

负责第二阶段当前已落地的权限语义，包括：

- `default`
- `plan`
- `acceptEdits`
- `bypassPermissions`

并在工具解析阶段做冲突校验。

### 10.4 `tools/` 目录职责

`tools/` 是当前项目重构后的统一工具层。  
它统一承载：

- 原子工具
- 高阶代理工具
- 工具注册与协议

#### `tools/base.py`

定义所有 Tool 的统一基础接口与注册表，包括：

- `BaseTool`
- `ToolRegistry`
- `global_tool_registry`

当前它已经明确承担“统一工具协议层”的角色。

#### `tools/agent_tool.py`

这是当前项目中最关键的高阶工具之一。  
它负责：

- 根据 `agent_type` 读取 `AgentDefinition`
- 从 `ToolRegistry` 组装该子 Agent 允许使用的工具池
- 调用 `runtime/engine.py`
- 返回子 Agent 最终结果

它本质上是：

**主 Agent fork 子 Agent 的统一入口**

#### 原子工具文件

- `read_log.py`
- `read_code.py`
- `edit_code.py`
- `run_test.py`
- `git_commit.py`
- `feishu_notify.py`

这些文件只负责单一环境动作，不负责复杂任务语义。

### 10.5 `agents/` 目录职责

当前 `agents/` 目录已经从“具体角色实现集合”收敛为：

- Agent 定义
- 第一阶段入口 Agent

#### `agents/registry.py`

这是当前项目中非常关键的配置中心。  
它负责：

- 定义 `AgentDefinition`
- 注册内置 Agent：
  - `explore`
  - `plan`
  - `execute`
  - `verify`
- 约束每类 Agent 的：
  - `description`
  - `system_prompt`
  - `tools`
  - `disallowed_tools`
  - `model`
  - `max_turns`
  - `permission_mode`
  - `read_only`

这说明当前项目已经不再把子 Agent 写成散乱模块，而是采用：

**AgentDefinition + AgentEngine + ToolPool**

的结构。

#### `agents/sentinel_agent.py`

对应第一阶段的异常感知入口角色。

### 10.6 `workflow/` 目录职责

`workflow/` 负责三阶段之间的系统级串联，不进入第二阶段内部的详细推理。

#### `workflow/repair_pipeline.py`

系统级总流程入口，负责：

- 从第一阶段进入第二阶段
- 从第二阶段进入第三阶段
- 汇总最终结果

#### `workflow/stage_router.py`

负责阶段级路由判断：

- 是否继续下一阶段
- 是否进入补偿
- 是否直接转人工

#### `workflow/recovery.py`

负责恢复和补偿逻辑：

- PR 创建失败补偿
- 通知失败补偿
- 阶段中断后的恢复入口

### 10.7 `monitoring/`、`delivery/`、`integrations/`、`api/` 的职责

#### `monitoring/`

承载第一阶段异常感知和 Traceback 获取逻辑：

- `event_detector.py`
- `traceback_collector.py`
- `healthcheck_adapter.py`

#### `delivery/`

承载第三阶段交付服务逻辑：

- `pr_service.py`
- `notify_service.py`

#### `integrations/`

承载外部系统适配：

- `log_client.py`
- `github_client.py`
- `feishu_client.py`

#### `api/`

承载对外入口：

- `webhook.py`

### 10.8 `schemas/`、`tests/`、`docs/` 的职责

#### `schemas/`

当前放稳定数据契约：

- `agent_messages.py`
- `run_result.py`
- `tool_result.py`
- `audit_event.py`

当前 `schemas/` 主要服务于第二阶段已经落地的运行协议：

- 主线程 / 子 Agent 消息
- 子 Agent 运行结果
- `AgentTool` 对外结果
- 审计事件占位

#### `tests/`

放测试和固定样例：

- `fixtures/`：输入样例和 demo repo
- `test_pipeline.py`：测试三阶段串联
- `test_orchestrator.py`：测试第二阶段主 loop
- `test_agent_tools.py`：测试 `AgentTool`
- `test_primitive_tools.py`：测试原子工具
- `test_policy.py`：测试门禁策略
- `test_audit.py`：测试审计记录

#### `docs/`

放开发辅助文档：

- `DEVELOPMENT_ORDER.md`
- `prompts/`
- `examples/`
- `diagrams/`

### 10.9 当前阶段优先实现范围

虽然第 10 章描述的是完整项目结构，但当前阶段真正优先实现的部分应集中在：

- `runtime/`
- `tools/`
- `agents/registry.py`
- `errors.py`
- `enums.py`
- `policy.py`
- `audit.py`
- `tests/fixtures/`
- `tests/test_orchestrator.py`
- `tests/test_agent_tools.py`
- `tests/test_audit.py`

其中最核心的当前路径是：

- `runtime/engine.py`
- `runtime/runtime_state.py`
- `tools/base.py`
- `tools/agent_tool.py`
- `agents/registry.py`

---

## 11. 推荐开发顺序

### 阶段一：最小工作流骨架

优先完成：

- `Repair Orchestrator`
- `agent(explore)`
- `agent(plan)`
- `agent(execute)`
- `agent(verify)`
- 第二阶段运行时骨架

目标：

- 先把第二阶段主链路跑通

### 阶段二：补齐 Primitive Tools

当前状态（2026-05-02）：

- 已完成 `Read`
- 已完成 `Grep`
- 已完成 `Glob`
- 已完成 `EditCode`
- 已完成 `Bash`

阶段结果：

- 已打通最小修复闭环
- `verify` 已能基于 `bash` 的结构化结果形成 verdict

### 阶段三：补齐交付能力

优先完成：

- `Git Commit`
- `Feishu Notify`
- `Delivery Agent`

目标：

- 打通 PR 和通知链路

### 阶段四：接入第一阶段触发源

优先完成：

- `Sentinel Agent`
- 日志监控接入

目标：

- 打通端到端自动触发

---

## 12. 阶段一：最小工作流骨架开发方案

本阶段仅聚焦第二阶段自动修复工作流，不接入 LangGraph，也不要求打通监控入口、PR 提交和飞书通知。目标是先验证 Claude Code 风格的主 Agent + AgentTool 架构在当前项目中能否稳定运作。

### 12.1 阶段目标

验证以下问题：

- `Repair Orchestrator` 能否作为主线程 Agent 运行。
- 主线程 LLM 能否通过 `agent` 工具委派 `explore / plan / execute / verify` 四类子任务。
- 第二阶段主循环能否正确推进、重试、终止和转人工。
- 在不依赖完整真实工具链的情况下，最小修复闭环能否先跑通。

### 12.2 设计原则

- 阶段一优先验证主循环，不优先验证外部集成。
- 阶段一优先验证 Agent 委派，不优先验证复杂工具能力。
- 阶段一优先保证主循环与护栏清晰，不优先追求功能覆盖广度。
- 阶段一允许使用 stub / fake 工具或最小实现，以降低实现复杂度。

### 12.3 开发顺序

#### 第一步：实现 `Repair Orchestrator` 主循环骨架

优先实现一个主 Agent runtime，负责：

- 接收异常任务输入。
- 维护 `current_stage`、`iteration`、`max_iterations` 等运行态。
- 通过 ReAct 方式自主决定调用哪个 `AgentTool`。
- 调用 `agent(explore|plan|execute|verify)`。
- 根据返回结果决定 `continue / retry / escalate / terminate`。

本层对应 Claude Code 风格中的主线程 Agent loop，是阶段一的第一优先级。

#### 第二步：定义统一的 `AgentTool` 抽象接口

在实现具体子 Agent 前，先定义四类 `AgentTool` 的统一调用协议，至少包括：

- `invoke(payload) -> result`
- 标准输入结构
- 标准输出结构
- 标准错误结构

这一步的目的是让 `Repair Orchestrator` 先依赖抽象契约，而不是耦合具体实现。

#### 第三步：实现一个 `AgentTool` + 四类 `agent_type` 的最小版本

按以下顺序实现最小可运行版本：

- `agent(explore)`
- `agent(plan)`
- `agent(execute)`
- `agent(verify)`

这一阶段可以先采用：

- 简化规则解析
- 固定模板输出
- mock LLM
- fake/stub primitive tools

目标不是立刻做强能力版本，而是先让调用链成立。

#### 第四步：实现第二阶段运行时护栏与退出控制

在主循环中显式接入：

- 运行时阶段标签
- 最大迭代次数限制
- 高风险停止条件
- 测试失败回退逻辑

不要把这些护栏实现成固定业务图；它们的作用是限制主 Agent 的执行边界，而不是替主 Agent 决策。

#### 第五步：加入最小审计能力

即使是阶段一，也必须记录最小审计信息，例如：

- `run_id`
- 当前轮次
- 当前状态
- 调用的 `AgentTool`
- 返回摘要
- 最终结果

可以先用 SQLite 或 JSONL，只要能支持回放与调试即可。

#### 第六步：用固定样例跑通端到端主循环

先不用急着接入完整真实工具，而是先准备固定样例：

- 成功修复样例
- 失败升级样例

通过固定样例验证：

- 主循环能否正常推进
- 护栏与退出条件是否正确
- 重试逻辑是否成立
- 人工升级逻辑是否成立

#### 第七步：逐步替换为真实 Primitive Tool

当主循环与护栏稳定后，再按以下顺序替换内部 stub：

1. `agent(explore)` 接真实 `Read / Grep / Glob`
2. `agent(verify)` 接真实 `Bash`
3. `agent(execute)` 接真实 `EditCode`
4. `agent(plan)` 接真实 LLM 推理能力

顺序这样安排的原因是：

- 先把读取与验证做稳，比先改代码更安全
- 先把“看懂问题”和“验证结果”做好，再把“实际修改代码”接进去

### 12.4 阶段一运行接口规格

阶段一明确采用同步运行接口，不实现异步接口。这样可以先稳定主循环和状态机，再在后续迭代中评估是否需要异步化。

#### 12.4.1 `Repair Orchestrator` 同步运行入口

推荐提供统一同步入口：

```python
run(task_input: dict) -> dict
```

其中：

- `task_input` 是一次修复任务的结构化输入
- 返回值是一次修复任务的最终结构化结果

#### 12.4.2 `task_input` 最小字段

阶段一要求 `run(task_input)` 至少接收以下字段：

```json
{
  "run_id": "<run_id>",
  "bug_event": {},
  "traceback": "Traceback (most recent call last): ...",
  "repo": "<repo>",
  "branch": "<branch>",
  "max_iterations": 3
}
```

字段说明：

- `run_id`：本次修复任务唯一 ID
- `bug_event`：标准化事件对象
- `traceback`：原始错误栈
- `repo`：目标仓库标识
- `branch`：目标分支
- `max_iterations`：最大修复轮次，阶段一固定默认为 `3`

#### 12.4.3 `run()` 返回值最小字段

阶段一要求 `run()` 至少返回：

```json
{
  "run_id": "<run_id>",
  "final_status": "READY_FOR_PR | NEED_HUMAN_REVIEW | FAILED",
  "current_stage": "READY_FOR_PR",
  "iterations_used": 2,
  "summary": "<summary>",
  "artifacts": {},
  "errors": []
}
```

字段说明：

- `final_status`：最终任务状态
- `current_stage`：结束时所在状态
- `iterations_used`：已使用轮次
- `summary`：最终摘要
- `artifacts`：补丁、测试、PR 等产物摘要
- `errors`：结构化错误列表

#### 12.4.4 `Repair Orchestrator` 内部最小同步接口

当前实现中，`runtime/orchestrator.py` 已经收敛为单文件主线程 runtime，内部至少应存在以下实现边界：

- `initialize_run(task_input) -> run_state`
- `_build_initial_messages(task_input) -> messages`
- `_invoke_agent_tool(state, tool_call) -> AgentToolResult`
- `_build_agent_payload(state, tool_call) -> payload`
- `_record_agent_observation(state, result) -> None`
- `finalize_run(run_state) -> result`

这些函数当前不要求拆为独立模块，但它们已经在代码中形成稳定的职责边界。

#### 12.4.5 阶段一同步实现约束

- 所有 `AgentTool` 调用必须同步执行
- 所有 `Primitive Tool` 调用必须同步执行
- 主循环一次只允许推进一个状态
- 不允许在阶段一引入并发执行和后台任务
- 若后续需要异步能力，应在阶段一完成后单独设计 `arun()`

### 12.5 阶段一统一错误码体系

阶段一必须引入统一错误码，而不是只依赖自然语言报错。这样主循环、AgentTool、Primitive Tool 和审计系统才能共享稳定的失败语义。

#### 12.5.1 错误对象结构

所有错误统一采用如下结构：

```json
{
  "code": "PLAN_INSUFFICIENT_EVIDENCE",
  "message": "Root cause analysis did not produce actionable evidence",
  "retryable": false,
  "stage": "CONTEXT_BUILT",
  "source": "agent(plan)"
}
```

字段说明：

- `code`：错误码，必须稳定
- `message`：人类可读说明
- `retryable`：是否允许重试
- `stage`：错误发生阶段
- `source`：错误来源，可能是 `RepairOrchestrator`、`AgentTool` 或 `Primitive Tool`

#### 12.5.2 错误码命名规则

建议统一采用：

```text
<LAYER>_<ERROR_NAME>
```

其中 `LAYER` 可取：

- `ORCH`
- `EXPLORE`
- `PLAN`
- `EXECUTE`
- `VERIFY`
- `TOOL`
- `AUDIT`

例如：

- `ORCH_INVALID_STATE_TRANSITION`
- `PLAN_INSUFFICIENT_EVIDENCE`
- `EXECUTE_PATCH_APPLY_FAILED`
- `TOOL_RUN_TEST_FAILED`

#### 12.5.3 第一批最小错误码清单

##### 主循环错误码

- `ORCH_INVALID_INPUT`
- `ORCH_INVALID_STATE_TRANSITION`
- `ORCH_MAX_ITERATIONS_EXCEEDED`
- `ORCH_POLICY_VIOLATION`

##### Explore 阶段错误码

- `EXPLORE_TRACEBACK_INSUFFICIENT`
- `EXPLORE_CODE_NOT_FOUND`
- `EXPLORE_CONTEXT_INSUFFICIENT`

##### Plan 阶段错误码

- `PLAN_INSUFFICIENT_EVIDENCE`
- `PLAN_UNACTIONABLE_REPAIR_PLAN`
- `PLAN_HIGH_RISK_REPAIR`

##### Execute 阶段错误码

- `EXECUTE_PATCH_APPLY_FAILED`
- `EXECUTE_PLAN_DEVIATION`
- `EXECUTE_UNAUTHORIZED_MODIFICATION`

##### Verify 阶段错误码

- `VERIFY_TARGETED_TEST_FAILED`
- `VERIFY_SMOKE_TEST_FAILED`
- `VERIFY_TEST_ENVIRONMENT_ERROR`

##### Primitive Tool 错误码

- `TOOL_READ_LOG_FAILED`
- `TOOL_READ_CODE_FAILED`
- `TOOL_EDIT_CODE_FAILED`
- `TOOL_RUN_TEST_FAILED`
- `TOOL_GIT_COMMIT_FAILED`
- `TOOL_FEISHU_NOTIFY_FAILED`

##### 审计错误码

- `AUDIT_WRITE_FAILED`
- `AUDIT_PAYLOAD_SERIALIZATION_FAILED`

#### 12.5.4 错误码与状态流转关系

错误码不仅用于报错，也用于驱动主循环中的护栏决策。阶段一至少应遵循以下规则：

- `*_INSUFFICIENT` 类错误通常进入 `NEED_HUMAN_REVIEW`
- `*_FAILED` 且 `retryable = true` 的错误可进入重试分支
- `ORCH_MAX_ITERATIONS_EXCEEDED` 必须直接进入 `NEED_HUMAN_REVIEW`
- `ORCH_INVALID_STATE_TRANSITION` 必须直接进入 `FAILED`
- `PLAN_HIGH_RISK_REPAIR` 必须直接进入 `NEED_HUMAN_REVIEW`

#### 12.5.5 阶段一实现要求

阶段一实现时必须做到：

- `AgentTool` 返回的 `errors` 必须使用统一错误对象
- `Primitive Tool` 返回的 `errors` 必须使用统一错误对象
- `Repair Orchestrator` 的最终结果中必须包含聚合后的错误列表
- 审计记录中必须保留错误码而不是只保留报错文本

### 12.6 阶段一的推荐实现边界

本阶段明确不要求：

- 接入第一阶段真实监控系统
- 接入第三阶段真实 GitHub PR 创建
- 接入第三阶段真实飞书通知
- 完整的生产级权限系统
- 完整的多仓库支持

本阶段必须具备：

- 主 Agent 主循环
- 四类 `AgentTool` 抽象与最小实现
- 第二阶段运行时护栏
- 最小审计能力
- 成功/失败两类固定样例

### 12.7 阶段一的推荐目录职责

本阶段实现时，职责顺序建议如下：

1. 主 Agent runtime
2. `AgentTool` 抽象协议
3. 四个 `AgentTool` 最小实现
4. 运行时护栏与门禁逻辑
5. 审计记录
6. 固定样例测试

注意这里强调的是“职责顺序”，而不是必须采用特定文件名。阶段一的目标是先验证结构成立，而不是过早锁死工程文件组织。

### 12.8 阶段一验收标准

阶段一完成后，至少应满足以下条件：

- 能启动一个 `Repair Orchestrator`。
- 能按顺序调用四个 `AgentTool`。
- 能维护明确的 `current_stage` 和 `iteration`。
- 能根据 `agent(verify)` 结果决定继续、重试、升级或终止。
- 能限制最大修复轮次。
- 能输出最终状态：
  - `READY_FOR_PR`
  - `NEED_HUMAN_REVIEW`
  - `FAILED`
- 能记录最小审计信息。
- 能返回统一错误码。

### 12.9 阶段一测试要求

至少准备两类固定测试样例：

#### 成功修复样例

期望结果：

- 主循环完成一次或多次修复迭代
- 最终进入 `READY_FOR_PR`

#### 失败升级样例

期望结果：

- 主循环在多轮尝试后停止
- 最终进入 `NEED_HUMAN_REVIEW`

如果这两类样例都能稳定通过，就说明阶段一的最小工作流骨架已经成立。

---

## 13. 安全、审计与降级

### 13.1 权限控制

- Agent 仅能访问授权仓库
- 不允许直接推主分支
- Shell 命令必须白名单化

### 13.2 变更限制

- 限制修改范围不得偏离修复计划
- 限制单次 diff 行数
- 高风险目录禁止自动修改

### 13.3 审计记录

必须记录：

- 事件来源
- Traceback
- 根因分析结果
- 修复计划
- 工具调用轨迹
- 测试结果
- PR 链接
- 通知状态

#### 13.3.1 审计目标

审计记录的核心目标不是替代普通日志，而是用结构化方式记录一次自动修复任务的完整执行过程，以便支持：

- 执行回放
- 失败排障
- 安全治理
- 修复质量复盘
- 后续策略优化

审计记录应回答四类问题：

- 系统做了什么
- 系统为什么这么做
- 系统改了什么
- 系统最终结果是什么

#### 13.3.2 审计事件模型

建议将审计记录视为一串结构化事件流，而不是一条最终总结。首版最少包含以下事件类型：

- `repair_run_started`
- `agent_tool_invoked`
- `agent_tool_completed`
- `primitive_tool_invoked`
- `primitive_tool_completed`
- `orchestrator_decision_made`
- `repair_run_finished`

其中：

- `repair_run_started` 表示一次修复任务正式开始
- `agent_tool_invoked/completed` 记录高阶子任务执行
- `primitive_tool_invoked/completed` 记录底层环境动作
- `orchestrator_decision_made` 记录状态流转和重试/升级决策
- `repair_run_finished` 记录最终结果

#### 13.3.3 最小审计字段

每条审计事件建议至少包含：

- `audit_id`
- `run_id`
- `iteration`
- `event_type`
- `stage`
- `actor`
- `status`
- `summary`
- `payload_json`
- `created_at`

字段说明如下：

- `audit_id`：审计事件唯一 ID
- `run_id`：所属修复任务 ID
- `iteration`：所属第几轮修复迭代
- `event_type`：事件类型
- `stage`：当前状态机阶段
- `actor`：执行主体，如 `RepairOrchestrator`、`agent(plan)`、`RunTest`
- `status`：事件状态，如 `started`、`success`、`failed`
- `summary`：短摘要
- `payload_json`：结构化详细信息
- `created_at`：事件时间

#### 13.3.4 推荐落库表结构

首版建议采用单表事件流结构，避免一开始拆太多关系表。

推荐表：

`audit_events`

推荐字段：

```text
id
run_id
iteration
event_type
stage
actor
status
summary
payload_json
created_at
```

这样做的优点是：

- 结构简单
- 易于追加写入
- 易于按 `run_id` 回放完整执行过程
- 后续如果迁移到 PostgreSQL 或 OLAP，也容易扩展

#### 13.3.5 `payload_json` 推荐内容

不同事件类型的 `payload_json` 可包含不同内容。

例如：

- `repair_run_started`
  - `bug_event`
  - `traceback_ref`
  - `service`

- `agent_tool_completed`
  - `agent_tool`
  - `output`
  - `next_recommendation`

- `primitive_tool_completed`
  - `tool_name`
  - `input`
  - `output`
  - `errors`

- `orchestrator_decision_made`
  - `current_stage`
  - `decision`
  - `next_stage`
  - `reason`

- `repair_run_finished`
  - `final_status`
  - `pr_url`
  - `notification_status`

#### 13.3.6 推荐审计事件流示例

一次典型修复任务建议形成如下审计序列：

1. `repair_run_started`
2. `agent_tool_invoked` - `agent(explore)`
3. `primitive_tool_invoked` - `ReadLog`
4. `primitive_tool_completed` - `ReadLog`
5. `primitive_tool_invoked` - `ReadCode`
6. `primitive_tool_completed` - `ReadCode`
7. `agent_tool_completed` - `agent(explore)`
8. `agent_tool_invoked` - `agent(plan)`
9. `agent_tool_completed` - `agent(plan)`
10. `orchestrator_decision_made`
11. `agent_tool_invoked` - `agent(execute)`
12. `primitive_tool_invoked` - `EditCode`
13. `primitive_tool_completed` - `EditCode`
14. `agent_tool_completed` - `agent(execute)`
15. `agent_tool_invoked` - `agent(verify)`
16. `primitive_tool_invoked` - `RunTest`
17. `primitive_tool_completed` - `RunTest`
18. `agent_tool_completed` - `agent(verify)`
19. `repair_run_finished`

#### 13.3.7 阶段一最低要求

在阶段一最小工作流骨架中，不要求一次性实现完整审计平台，但最低要求必须满足：

- 能按 `run_id` 追踪一次修复任务
- 能记录每次 `AgentTool` 调用
- 能记录每次 `Primitive Tool` 调用
- 能记录每次 `Orchestrator` 决策
- 能记录最终结果

#### 13.3.8 审计与普通日志的区别

普通日志主要面向开发调试，通常是非结构化文本；审计记录则面向：

- 回放
- 治理
- 统计
- 追责
- 复盘

因此审计记录必须是结构化、稳定、可查询的数据，而不能仅依赖控制台输出或散乱文本日志。

### 13.4 降级策略

- 采集失败：转人工
- 根因不明：转人工
- 多轮修复失败：转人工
- 测试失败：停止提交 PR
- 通知失败：补偿重试

---

## 14. MVP 定义

首版 MVP 仅要求：

- 单个 Python Web 服务
- 本地日志文件 Traceback
- pytest 测试
- GitHub PR
- 飞书 webhook 通知

首版 MVP 必须实现：

1. 监控报错并抓取 Traceback
2. 第二阶段循环式自动修复工作流
3. 测试通过后自动创建 PR
4. 自动发送飞书卡片

---

## 15. 成功标准

- 能稳定获取服务 Traceback
- 能定位相关代码和测试
- 能完成至少一个已知错误的自动修复
- 测试通过后能成功创建 PR
- 能成功发送飞书通知
- 任一失败场景都能正确停止并转人工

---

## 16. 一句话总结

当 Web 服务报错时，系统先感知异常并获取 Traceback，再由 `Repair Orchestrator` 通过 `AgentTool` 编排 `Explore / Plan / Execute / Verify` 四类子 Agent 完成循环式自动修复，最后在验证通过后自动提交 PR 并通过飞书通知开发者 Review。
