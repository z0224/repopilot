# RepoPilot 四周项目推进计划

> 项目定位：基于代码 RAG、Coding Agent 执行轨迹审计和确定性策略引擎，对自动代码修复过程进行上下文增强、安全检查与质量验收。

## 1. 最终目标

RepoPilot 不重新实现大模型或完整 Coding Agent。第一版以 mini-swe-agent 为执行后端，在其外层实现：

1. 修改前保存代码快照并运行基线测试；
2. 使用 Repository RAG 检索相关源码、测试和依赖；
3. 调用 mini-swe-agent 执行代码修复；
4. 结构化解析命令、返回码、输出和文件操作；
5. 审计源码、测试、补丁范围和危险操作；
6. 根据确定性策略输出 `Accepted` 或 `Rejected`；
7. 生成 JSON、Markdown 和 HTML 报告；
8. 比较 Baseline、Safe、RAG、RAG + Safe 四组实验。

最终使用方式：

~~~bash
repopilot run ./project \
  --agent mini-swe-agent \
  --task "修复库存预留的原子性问题" \
  --policy configs/strict.yaml \
  --retrieval hybrid
~~~

期望输出：

~~~text
Decision: ACCEPTED
Baseline tests: 3 failed, 2 passed
Final tests: 5 passed
Changed source files: 1
Changed test files: 0
Unsafe overwrites: 0
Targeted edits: 1
Relevant file Recall@5: 1.00
Report: results/runs/<run-id>/report.html
~~~

## 2. 项目边界

### RepoPilot 负责

- Repository RAG；
- Agent 运行编排；
- 修改前后快照；
- 测试执行与结果记录；
- trajectory 解析；
- 文件和命令风险识别；
- 策略验收；
- Benchmark 和实验汇总；
- 报告生成。

### mini-swe-agent 负责

- 大模型调用；
- Agent 推理循环；
- Bash 命令执行；
- 源码修改；
- 原始 trajectory 生成。

### 第一版不做

- 不训练基础模型；
- 不实现操作系统级安全沙箱；
- 不自动合并或部署补丁；
- 不承诺补丁绝对正确；
- 不用 LLM 判断替代确定性验收；
- 不支持所有语言，第一版聚焦 Python。

## 3. 总体架构

~~~text
Task + Repository
        |
        v
Repository Indexer
  AST chunks / metadata / cache
        |
        v
Hybrid Retriever
  lexical + semantic + dependency rerank
        |
        v
Context Builder
  source / tests / symbols
        |
        v
Agent Adapter
  MiniSWEAgentAdapter
        |
        v
Trajectory Parser
  command / output / return code / paths
        |
        +------------------+
        |                  |
        v                  v
Change Auditor        Test Verifier
        |                  |
        +--------+---------+
                 |
                 v
            Policy Engine
          ACCEPT / REJECT
                 |
                 v
          Report Generator
       JSON / Markdown / HTML
~~~

建议最终目录：

~~~text
repopilot/
├── pyproject.toml
├── README.md
├── configs/
│   ├── safe_patch.yaml
│   ├── strict.yaml
│   └── balanced.yaml
├── src/repopilot/
│   ├── cli.py
│   ├── models.py
│   ├── snapshot.py
│   ├── testing.py
│   ├── adapters/
│   ├── retrieval/
│   ├── trajectory/
│   ├── audit/
│   ├── policy/
│   └── reporting/
├── benchmarks/
├── tests/
├── results/
└── docs/
~~~

## 4. 当前状态

当前版本可视为第 1 周 MVP。

### 已完成

- [x] mini-swe-agent 本地运行；
- [x] Safe Patch 配置；
- [x] 修改前快照；
- [x] 基线与最终测试；
- [x] 源码和测试文件变化检测；
- [x] trajectory 命令提取；
- [x] 整文件覆盖识别；
- [x] 精准替换和临时文件分类；
- [x] 5 个本地缺陷任务；
- [x] 5 个任务完成 Safe Patch 验收；
- [x] RepoPilot 单元测试；
- [x] GitHub 仓库与提交记录。

### 当前限制

- [ ] Agent 仍需手动运行；
- [ ] trajectory 解析主要依赖命令文本；
- [ ] 未完整关联命令和执行结果；
- [ ] 尚无 Repository RAG；
- [ ] 策略仍写在代码中；
- [ ] Benchmark 数量较少；
- [ ] 尚无 HTML 报告和正式 README。

## 5. 四周总览

| 周次 | 核心目标 | 主要产物 | 验收标准 |
|---|---|---|---|
| 第 1 周 | 安全审计 MVP | CLI、5 个任务、基础审计 | 任务可复现，单元测试通过 |
| 第 2 周 | 代码 RAG 与 Agent Adapter | AST 索引、混合检索、上下文包 | 返回可解释的 Top-K 文件 |
| 第 3 周 | 结构化轨迹、策略和正式实验 | 事件模型、Policy、15～20 个任务 | 四组实验可批量运行 |
| 第 4 周 | 产品化和展示 | 安装包、报告、CI、README、Demo | 新用户能按 README 复现 |

建议投入：每周 12～18 小时，总计约 50～70 小时。

## 6. 第 1 周：安全审计 MVP

### Day 1：环境与基础 Agent

- 安装 WSL、Python 和虚拟环境；
- 安装 mini-swe-agent；
- 配置模型与 API Key；
- 完成最小计算错误任务；
- 保存并查看第一条 trajectory。

验收：

- mini-swe-agent 能完成一次修复；
- API Key 不进入 Git；
- trajectory 可以保存和检查。

### Day 2：构造 5 个 Benchmark

任务类型：

1. 简单表达式错误；
2. 除零边界条件；
3. 折扣计算和无关功能保护；
4. 多文件数据清洗；
5. 库存预留原子性。

每个任务必须有故障源码、测试、初始结果、正确修复结果和原始轨迹。

### Day 3：快照与变更审计

- 收集源码文件；
- 保存 SHA-256、行数和内容；
- 比较新增、删除和修改文件；
- 统计增删行；
- 识别测试文件；
- 输出 JSON。

### Day 4：trajectory 审计

- 提取 Bash 命令；
- 识别 `cat >`、`Path.write_text` 和 `open(..., "w")`；
- 区分精准替换和临时文件；
- 接入 Accept/Reject；
- 为误报案例补回归测试。

### Day 5：Safe Patch 对照实验

- 编写 `safe_patch.yaml`；
- 对 5 个任务重新运行；
- 修复审计误报；
- 记录实验日志；
- 提交 GitHub。

验收：所有数字都能回溯到报告或 trajectory，不提前编造提升比例。

## 7. 第 2 周：Repository RAG 与 Agent Adapter

### Day 6：重构 Python 包

- 创建 `src/repopilot/`；
- 拆分 snapshot、testing、audit、reporting；
- 添加 `pyproject.toml`；
- 保持现有 CLI 行为；
- 补充回归测试。

验收：

~~~bash
pip install -e .
repopilot --help
pytest -q
~~~

### Day 7：AST 代码切块

- 使用 Python AST 解析源码；
- 按函数、类、模块切块；
- 保存路径、符号、行号、docstring、imports；
- 无法解析时降级为模块级文本；
- 使用文件哈希做增量更新。

Chunk 示例：

~~~json
{
  "chunk_id": "inventory/service.py::reserve_inventory",
  "path": "inventory/service.py",
  "symbol": "reserve_inventory",
  "kind": "function",
  "start_line": 4,
  "end_line": 22,
  "imports": ["InsufficientStockError"],
  "content": "def reserve_inventory(...): ...",
  "sha256": "..."
}
~~~

验收：行号和内容正确、chunk ID 稳定、未变化文件不重复索引。

### Day 8：关键词检索

- 索引路径、符号、docstring 和源码；
- 查询由任务、失败测试名和 traceback 组成；
- 返回 Top-K chunk；
- 保存分数和命中原因。

验收：查询库存原子性时，`reserve_inventory` 位于 Top 3。

### Day 9：语义与混合检索

- 为代码块生成 embedding；
- 实现向量相似度检索；
- 与关键词分数组合；
- 用测试引用与 import 关系重排；
- embedding 失败时降级到关键词检索。

候选公式：

~~~text
hybrid_score =
    0.45 * lexical_score
  + 0.35 * semantic_score
  + 0.20 * dependency_score
~~~

权重仅为实验起点，必须通过实验调整。

验收：

- 标注每个任务的 relevant files；
- 计算 Recall@1、Recall@3、Recall@5；
- 可单独关闭 lexical 或 semantic。

### Day 10：Context Builder 与 Agent Adapter

- 定义 `AgentAdapter`；
- 实现 `MiniSWEAgentAdapter`；
- 把 Top-K 结果组成 Context Bundle；
- 控制上下文预算；
- 注入 Agent 任务；
- 保存实际注入内容。

接口示例：

~~~python
class AgentAdapter:
    def run(self, project, task, context, output_path):
        raise NotImplementedError
~~~

验收：RepoPilot 能通过 Adapter 启动 mini-swe-agent，报告中能看到检索结果和注入上下文。

## 8. 第 3 周：结构化轨迹、策略与实验

### Day 11：结构化轨迹事件

- 关联 command、tool call id、output 和 return code；
- 区分 attempted、executed 和 failed；
- 记录命令序号与时间；
- 解析目标路径；
- 区分源码、测试、临时文件和项目外路径。

事件示例：

~~~json
{
  "index": 6,
  "command": "perl -0pi ... inventory/service.py",
  "returncode": 0,
  "executed": true,
  "operation": "targeted_edit",
  "targets": ["inventory/service.py"],
  "scope": "project_source",
  "risk_level": "low"
}
~~~

验收：

- `apply_patch: not found` 标记为失败尝试；
- 后续成功替换标记为实际编辑；
- 未执行的完成标记不影响修复判断。

### Day 12：策略引擎

- 将验收条件移出硬编码；
- 使用 YAML 定义策略；
- 支持多条拒绝原因；
- 区分 error、warning、info；
- 报告每条规则结果。

~~~yaml
policy:
  require_baseline_test: true
  require_final_test_pass: true
  forbid_test_changes: true
  forbid_full_file_overwrite: true
  allow_temporary_files: true
  max_changed_files: 5
  max_added_lines: 100
  max_deleted_lines: 100
~~~

验收：同一运行结果可用 strict 和 balanced 策略评估，最终决策不依赖 LLM。

### Day 13：扩展 Benchmark

扩展至 15～20 个任务，覆盖：

- 单文件逻辑；
- 边界条件；
- 多文件修改；
- 异常处理；
- 数据一致性；
- 状态原子性；
- 无关函数保护；
- 测试诱导修改；
- 大文件局部错误；
- 工具失败恢复；
- 临时文件；
- 新增和删除文件；
- import 与包结构；
- 配置修改；
- RAG 易混淆文件。

每个任务包含：

~~~text
task.yaml
source files
test files
expected_relevant_files.json
expected_policy.json
README.md
~~~

### Day 14：批量实验运行器

实验分组：

| 组别 | RAG | Safe Prompt |
|---|---:|---:|
| Baseline | 否 | 否 |
| Safe Only | 否 | 是 |
| RAG Only | 是 | 否 |
| RAG + Safe | 是 | 是 |

要求：

- 每次运行使用独立目录和 run id；
- 记录模型、配置、耗时、API 调用和命令数；
- 一个任务失败后继续其他任务；
- 支持按任务或组别重跑；
- 保存 trajectory、diff 和报告。

### Day 15：指标与消融实验

统计：

- Repair Success Rate；
- Policy Acceptance Rate；
- Unsafe Overwrite Rate；
- Test Modification Rate；
- Baseline Test Execution Rate；
- Relevant File Recall@K；
- 首次查看正确文件的位置；
- 平均命令数和 API 调用；
- 平均修改文件数与增删行；
- 审计器误报和漏报。

原则：

- 不预设 RAG 一定提升；
- 小样本注明范围；
- 保存失败案例；
- 不只展示最好结果；
- 简历数字必须来自汇总文件。

验收：自动生成 `results/summary.json` 和四组方案对比表。

## 9. 第 4 周：产品化与展示

### Day 16：统一 CLI

~~~bash
repopilot index PROJECT
repopilot retrieve PROJECT --query "..."
repopilot start PROJECT
repopilot run PROJECT --task "..."
repopilot verify PROJECT --trajectory FILE
repopilot summarize results/runs
~~~

建议退出码：

~~~text
0 = accepted
1 = rejected by policy
2 = configuration or input error
3 = agent execution failed
4 = unexpected test failure
~~~

### Day 17：报告生成

每次运行输出：

~~~text
results/runs/<run-id>/
├── metadata.json
├── baseline.json
├── retrieval.json
├── context.md
├── trajectory.json
├── diff.patch
├── report.json
├── report.md
└── report.html
~~~

HTML 展示：

- 最终决策；
- 任务与模型配置；
- 基线与最终测试；
- 检索代码块；
- 文件 diff；
- 命令时间线；
- 风险事件；
- 策略检查；
- 实验指标。

验收：HTML 可离线打开、不含 API Key、不同格式核心数字一致。

### Day 18：测试和 CI

- 单元测试扩展至 25～40 个；
- 增加端到端测试；
- 添加 GitHub Actions；
- 提供无需真实 API 的 mock；
- 验证打包和安装。

CI 至少运行：

~~~bash
python -m pytest -q
python -m compileall src
repopilot --help
~~~

### Day 19：README 与 Demo

README 包含：

1. 一句话介绍；
2. 项目动机；
3. 演示；
4. 核心功能；
5. 架构；
6. 安装和 Quick Start；
7. RAG 设计；
8. 策略引擎；
9. 实验设计与真实结果；
10. 局限；
11. 与 mini-swe-agent 的关系；
12. License 与致谢。

Demo 展示：建立基线、RAG 检索、Agent 修复、轨迹解析、策略验收、打开 HTML 报告。

### Day 20：封版

- 创建版本标签；
- 检查密钥和缓存；
- 验证文档链接；
- 从新目录复现 Quick Start；
- 整理项目复盘；
- 只使用已有证据支持的指标。

~~~bash
git status --short
pytest -q
git grep -n "sk-"
git log --oneline --decorate -10
~~~

## 10. Git 推进策略

推荐提交：

~~~text
feat: add AST-based repository chunker
feat: implement lexical code retrieval
feat: add hybrid retrieval and context builder
refactor: introduce agent adapter interface
feat: parse trajectory commands and outcomes
feat: add configurable policy engine
test: expand benchmark task set
feat: add batch experiment runner
feat: generate markdown and HTML reports
ci: add automated test workflow
docs: add architecture and evaluation results
~~~

每次提交前：

~~~bash
pytest -q
git diff --check
git status --short
~~~

禁止提交 `.env`、API Key、虚拟环境、缓存、无必要的大型索引和含敏感信息的终端记录。

## 11. 每日记录模板

~~~markdown
## 今日目标

- 一个能够验收的主要目标。

## 验收条件

- [ ] 单元测试
- [ ] 手动演示
- [ ] 文档更新
- [ ] Git 提交

## 今日完成

- 实际完成：
- 测试结果：
- 产生文件：
- 提交哈希：

## 问题与处理

- 失败尝试：
- 原因：
- 处理方式：

## 明日第一步

- 一个可以直接执行的动作：
~~~

## 12. 风险与应对

### RAG 在小仓库没有明显提升

- 增加含相似文件的中型任务；
- 同时评估 Recall@K、命令数和修复率；
- 如实报告无提升场景。

### 向量检索复杂但收益有限

- 先完成关键词基线；
- 语义检索保持可选；
- 做 lexical、semantic、hybrid 消融。

### 命令正则持续膨胀

- 关联命令与执行结果；
- 以最终 diff 为主、命令文本为辅；
- unknown 类型进入人工复核，不默认安全。

### Benchmark 偏向自身规则

- 提前定义任务与预期；
- 保留失败任务；
- 覆盖不同错误类型；
- 不因结果不理想删除样本。

### 范围过大

- 第一版只支持 Python；
- 第一版只接 mini-swe-agent；
- HTML 使用静态模板；
- 优先完成实验闭环，再扩展 UI。

## 13. Definition of Done

### 功能

- [ ] 可安装 `repopilot` CLI；
- [ ] 一条命令运行完整流程；
- [ ] 支持 mini-swe-agent Adapter；
- [ ] 支持 AST 索引；
- [ ] 支持混合检索；
- [ ] 支持 Context Bundle；
- [ ] 支持结构化 trajectory；
- [ ] 支持 YAML 策略；
- [ ] 支持 Accept/Reject；
- [ ] 支持 JSON、Markdown、HTML 报告。

### 质量

- [ ] 至少 25 个单元测试；
- [ ] 至少一个端到端测试；
- [ ] GitHub Actions 通过；
- [ ] 仓库不含 API Key；
- [ ] 错误信息清晰；
- [ ] Quick Start 可在干净环境复现。

### 实验

- [ ] 15～20 个 Benchmark；
- [ ] relevant files 人工标注；
- [ ] 四组消融实验；
- [ ] 自动生成 summary；
- [ ] 保存失败案例；
- [ ] 明确样本范围和局限。

### 展示

- [ ] README；
- [ ] 架构图；
- [ ] 演示 GIF 或视频；
- [ ] 示例 HTML 报告；
- [ ] 实验结果表；
- [ ] 项目复盘；
- [ ] 有证据支撑的项目描述。

## 14. 最终验收

四周结束时，项目至少包含：

1. 可安装的 RepoPilot Python 包；
2. mini-swe-agent Adapter；
3. Repository RAG；
4. 结构化轨迹解析器；
5. 变更审计器；
6. 可配置策略引擎；
7. 批量 Benchmark 运行器；
8. 15～20 个任务；
9. 自动汇总结果；
10. JSON、Markdown、HTML 报告；
11. 25～40 个单元测试；
12. GitHub Actions；
13. README、架构图和演示；
14. 完整实验日志与限制说明。

最终验收方式：

> 一个不了解项目的人，按照 README 在干净环境中配置模型后，能够运行一条命令，看到 Repository RAG 的检索结果、mini-swe-agent 的修复过程、RepoPilot 的 Accept/Reject 决策，并打开完整审计报告。

