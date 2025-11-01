# AI Agent Prompt 测试指南

本指南介绍如何使用 `test_prompt_output.py` 测试程序来验证和查看各个 AI Agent 的完整 Prompt 输出。

## 快速开始

### 基本用法
```bash
# 测试结构化预测 Prompt
uv run python tests/test_prompt_output.py --agent structured_prediction --ticker AAPL

# 测试技术分析 Prompt  
uv run python tests/test_prompt_output.py --agent technical_analysis --ticker MSFT

# 测试综合分析 Prompt
uv run python tests/test_prompt_output.py --agent synthesis --ticker TSLA
```

### 高级用法
```bash
# 指定自定义结束日期
uv run python tests/test_prompt_output.py --agent structured_prediction --ticker AAPL --end_date 2024-12-31

# 保存 Prompt 输出到文件
uv run python tests/test_prompt_output.py --agent technical_analysis --ticker GOOGL --save_to_file output.txt
```

## 命令参数说明

| 参数 | 必需 | 描述 | 示例 |
|------|------|------|------|
| `--agent` | ✅ | 要测试的Agent类型 | `structured_prediction`, `technical_analysis`, `synthesis` |
| `--ticker` | ✅ | 股票代码 | `AAPL`, `MSFT`, `TSLA`, `GOOGL` |
| `--end_date` | ❌ | 自定义结束日期(YYYY-MM-DD格式) | `2024-12-31` |
| `--save_to_file` | ❌ | 保存Prompt到指定文件 | `prompt_output.txt` |

## Agent 类型详解

### 1. structured_prediction
测试结构化预测Agent的完整Prompt输出，包含：
- 股票基本信息和价格数据
- 技术分析、基本面分析、新闻情感分析结果
- 市场感知日期和交易日计算
- 具体的4%涨跌目标价格计算
- 概率预测要求和输出格式

**使用场景**：验证AI预测模型的输入数据完整性

### 2. technical_analysis  
测试技术分析Agent的完整Prompt输出，包含：
- 多时间维度价格数据(日线/周线/10分钟线)
- 技术指标计算结果(MA、RSI、MACD、布林带等)
- 市场感知日期和分析要求
- 技术分析输出格式规范

**使用场景**：验证技术指标计算和分析逻辑

### 3. synthesis
测试综合分析Agent的完整Prompt输出，包含：
- 所有可用的分析结果整合
- 技术分析、基本面分析、新闻情感分析摘要
- 市场时间框架和投资建议格式
- 综合评估和风险提示要求

**使用场景**：验证多Agent分析结果的整合逻辑

## 执行流程说明

测试程序采用**并行执行**架构，提升性能：

1. **数据收集阶段**：获取股票价格、新闻等原始数据
2. **并行分析阶段**：同时执行技术分析、基本面分析、新闻情感分析
3. **状态整合阶段**：收集所有分析结果到统一状态
4. **Prompt生成阶段**：根据指定Agent类型生成对应Prompt
5. **结果输出阶段**：显示完整Prompt内容和分析摘要

## 输出格式示例

### 分析状态摘要
```
📋 分析状态摘要:
  - 股票代码: AAPL
  - 结束日期: 默认(市场感知日期)
  - 可用数据集: ['daily_prices', 'weekly_prices', 'news']
  - 日线数据: 252 行，最新收盘价: $150.25
  - 已完成分析: ['technical_analyst', 'news_sentiment_analyst']
    * technical_analyst: 2867 字符
    * news_sentiment_analyst: 2468 字符
  - 市场感知日期: 2025-09-09
  - 目标周五: 2025-09-12
  - 交易日数量: 3
```

### Prompt输出格式
```
================================================================================
🎯 STRUCTURED PREDICTION PROMPT OUTPUT
================================================================================
# AI Stock Analysis and Prediction System

## Current Market Context
- Analysis Date: 2025-09-09
- Target Date: 2025-09-12 (3 trading days ahead)
- Stock: AAPL (Apple Inc.)

## Stock Price Data
Current Price: $150.25
Upside Target (+4%): $156.26
Downside Target (-4%): $144.24

[完整Prompt内容...]
================================================================================
🎯 STRUCTURED PREDICTION PROMPT END  
================================================================================
```

## 常用测试场景

### 验证新功能
```bash
# 测试新增的价格目标计算
uv run python tests/test_prompt_output.py --agent structured_prediction --ticker AAPL

# 测试市场感知日期逻辑
uv run python tests/test_prompt_output.py --agent synthesis --ticker MSFT --end_date 2024-12-27
```

### 性能测试  
```bash
# 测试并行执行效果
time uv run python tests/test_prompt_output.py --agent structured_prediction --ticker GOOGL
```

### 调试分析
```bash
# 保存详细输出便于分析
uv run python tests/test_prompt_output.py --agent technical_analysis --ticker TSLA --save_to_file debug_output.txt
```

## 常见问题排查

### 1. LLM调用超时
- **现象**：HTTP 524 错误或长时间无响应
- **原因**：Prompt过长或网络问题
- **解决**：程序已使用流式调用避免超时

### 2. 价格数据获取失败
- **现象**：显示"日线数据: 不可用"
- **原因**：股票代码错误或数据源问题
- **解决**：检查股票代码拼写，确认数据源可用

### 3. 分析结果不完整
- **现象**：某些分析Agent显示跳过
- **原因**：外部API调用失败或数据不足
- **解决**：这是正常现象，程序会继续使用可用的分析结果

### 4. 列名错误
- **现象**："日线数据解析错误: 'Close'"
- **原因**：列名大小写不一致
- **解决**：已修复，统一使用小写'close'

## 技术架构

- **并行执行**：使用 `asyncio.gather()` 并行执行多个分析Agent
- **流式调用**：使用 `agent_stream()` 方法避免LLM超时
- **异常处理**：每个分析Agent独立异常处理，不影响整体流程
- **状态管理**：统一的GraphState管理所有分析状态和结果

## 扩展建议

### 添加新的测试场景
1. 在 `PromptTester` 类中添加新的测试方法
2. 在 `main()` 函数中添加新的Agent选项
3. 更新命令行参数解析和帮助信息

### 优化性能
1. 考虑添加结果缓存机制
2. 支持批量股票测试
3. 添加并发限制避免API限流
