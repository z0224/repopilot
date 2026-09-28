# RepoPilot 面试讲解指南

这份文档用于秋招简历、项目演示和技术面试。所有数字均来自仓库中已经提交的正式实验，不要把小规模实验描述成普遍结论。

## 30 秒项目介绍

RepoPilot 是一个面向 AI 编程 Agent 的仓库级评测与安全审计工具。它不重新实现 Agent，而是接入 mini-SWE-agent，在执行前检索相关代码，在执行后分析轨迹、文件变更和测试结果，再通过确定性的 YAML 规则判断修复是否可以接受。项目的核心观点是：测试通过只代表功能修复成功，不代表修改过程安全、范围合理。

## 简历项目描述

**RepoPilot｜AI 编程 Agent 检索、审计与评测平台**  
技术栈：Python、AST、RAG、sentence-transformers、pytest、Git、GitHub Actions

- 基于 Python AST 实现函数、类和模块级代码切块与增量索引，支持词法、语义和混合检索，为 coding agent 生成长度受限且可追溯的仓库上下文。
- 接入 mini-SWE-agent，记录命令、文件操作、测试结果与模型开销；实现全文件覆盖、测试篡改、临时文件及修改范围等风险检测。
- 设计可配置 YAML 策略引擎，将“测试是否通过”和“修改是否符合安全约束”分离，并输出逐规则的 PASS、FAIL、WARNING 判定。
- 构建 10 个可复现 Python 缺陷任务和 Baseline、Safe、RAG、RAG+Safe 四组实验，共完成 40 次真实 Agent 运行；所有运行均修复测试，严格策略通过率分别为 10%、80%、40%、80%。
- 实现可恢复批量实验、JSON/Markdown/HTML 报告和 Python 3.10/3.12/3.14 CI，项目包含 100 余项自动化测试。

数字应随仓库继续开发而更新。面试时应主动说明：实验任务较小、每组只运行一次，因此这些结果是描述性证据，不是因果结论。

## 两分钟演示流程

### 1. 说明问题

先展示一个测试通过但过程不安全的例子：Agent 可能整文件覆盖、修改测试或留下临时脚本。说明 RepoPilot 为什么同时检查结果和过程。

### 2. 展示系统流程

打开 README 的架构图，按以下顺序讲解：

1. AST 建立仓库索引；
2. lexical、semantic 或 hybrid 检索相关代码；
3. 将有字符预算的上下文注入 mini-SWE-agent；
4. 保存执行轨迹和修改前快照；
5. 重新运行测试并审计修改；
6. YAML 策略引擎输出 Accepted 或 Rejected；
7. 批量实验汇总为 JSON、Markdown 和 HTML。

### 3. 运行免费演示

下面的命令不会调用模型，也不会产生 API 费用：

```bash
repopilot run-one-experiment \
  benchmarks/benchmark-manifest.json \
  --task task-001 \
  --group rag_safe \
  --output-root /tmp/repopilot-demo \
  --mini-executable mini \
  --agent-model-class litellm_response \
  --policy configs/strict.yaml \
  --dry-run
```

如果只想展示 RAG：

```bash
repopilot context benchmarks/task-005 \
  --query "修复库存预留逻辑，重复 SKU 要聚合，失败时保持原子性" \
  --retriever hybrid \
  --top-k 5 \
  --max-chars 6000
```

### 4. 展示实验结果

打开 `results/formal-batch-01/summary.html`，重点解释：

- 四组的修复成功率均为 100%，说明这些小任务无法证明 RAG 提升修复率；
- Baseline 的严格策略通过率只有 10%，说明“测试通过”不足以代表安全；
- Safe 和 RAG+Safe 均达到 80%，并显著减少全文件覆盖和临时文件；
- RAG 单独使用时通过率为 40%，说明检索到正确上下文不等于 Agent 会采用安全编辑方式；
- 这是 10 个合成任务、每种配置一次运行，不能做一般化或因果推断。

## 面试官常见追问

### 为什么不直接做一个新的 Agent？

项目关注的是 Agent 外部的基础设施：检索、可观察性、审计、策略和评测。复用 mini-SWE-agent 能控制变量，也让同一套 RepoPilot 能适配其他 Agent 后端。

### RAG 在这里解决什么问题？

它解决大仓库中“给模型看哪些代码”的问题。RepoPilot 使用 AST 保留代码结构，再组合关键词匹配与向量相似度，最后根据字符预算输出可检查的上下文包。

### 为什么策略判断不用 LLM？

测试修改、文件数量、增删行数和覆盖操作等规则需要稳定、可复现、便于审计。确定性规则更适合作为准入条件；LLM 可以用于解释，但不应替代硬约束。

### 如何识别整文件覆盖？

系统将轨迹中的 shell 命令解析为结构化事件，识别重定向、`write_text` 等写入模式，并结合修改前后快照和差异统计。对于带唯一目标与保护检查的局部替换，会单独标记为 targeted rewrite，避免一概拒绝。

### 如何避免 Agent 修改原始基准？

实验运行器把任务复制到隔离目录，清理缓存和历史产物，保存基线后才启动 Agent。批量运行支持断点续跑，完成结果写入独立目录。

### 目前最大的局限是什么？

主要局限是基准规模小、只覆盖 Python、每种配置只运行一次，而且命令审计依赖保守的静态规则。下一阶段应增加真实仓库任务、多随机种子和容器级隔离。

## 可以深入展开的技术点

- AST 切块如何保留文件路径、符号名和行号；
- 增量索引如何利用内容哈希复用未变化文件；
- lexical、semantic、hybrid 检索的差异及中英文评测；
- 上下文字符预算和结果可追溯性；
- mini-SWE-agent Responses tool-call 轨迹适配；
- 快照、Git diff 与命令事件如何共同形成审计证据；
- 策略规则和执行机制解耦的原因；
- 实验断点续跑、成本统计和报告生成。

## 表述边界

不要说：

- “RAG 将修复率提升了多少”；四组修复率本来都是 100%。
- “RepoPilot 能阻止所有危险命令”；它目前是审计和评测原型，不是操作系统沙箱。
- “80% 是稳定的线上指标”；实验只有 10 个合成任务且每组一次运行。

可以说：

- RepoPilot 让通过测试但违反策略的修复变得可见；
- 在本次已记录实验中，安全提示组比 Baseline 获得更高的严格策略通过率；
- 项目形成了从检索、执行、审计到实验报告的完整闭环。
