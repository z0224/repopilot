# RepoPilot Benchmark Suite

该目录包含 RepoPilot 的本地 Python 缺陷修复 Benchmark。

## 任务结构

每个任务同时保存：

- 修复后的标准源码；
- 自动化测试；
- `fixtures/buggy/` 中的缺陷模板。

标准源码保持测试通过，使仓库自身始终处于绿色状态。批量实验运行器会把任务复制到临时目录，再使用缺陷模板覆盖目标文件。

## 当前任务

| ID | 类型 |
|---|---|
| task-001 | 单文件逻辑错误 |
| task-002 | 除零边界条件 |
| task-003 | 百分比折扣计算 |
| task-004 | 多文件数据清洗 |
| task-005 | 库存原子性 |
| task-006 | 异常处理 |
| task-007 | 全局配置污染 |
| task-008 | 测试修改诱导 |
| task-009 | 大文件局部错误 |
| task-010 | RAG 易混淆文件 |

任务定义统一保存在 `benchmark-manifest.json`，包括：

- Agent 任务描述；
- 中英文查询；
- 缺陷模板和目标文件；
- 测试命令；
- 预期基线失败数量；
- Retrieval Ground Truth。

`retrieval-ground-truth.json` 和
`retrieval-ground-truth-zh.json` 由以下命令自动生成：

```bash
python scripts/generate_retrieval_manifests.py \
  benchmarks/benchmark-manifest.json
