"""
测试新的 LangGraph Orchestrator 实现
"""

import asyncio
import json
from unittest.mock import patch
import pytest

from stockaivo.ai.orchestrator import run_ai_analysis

# 由于这是一个异步生成器，我们将使用 async for 来测试
@pytest.mark.asyncio
async def test_run_ai_analysis():
    """测试 run_ai_analysis 函数的基本功能"""
    print("=== 测试 LangGraph AI 分析工作流 ===")
    
    ticker = "FAKE"
    agent_outputs = []

    try:
        # 使用 mock 来模拟 agent 的输出，避免实际的 LLM 调用和数据获取
        with patch('stockaivo.ai.orchestrator.orchestrator.app') as mock_app:

            async def mock_astream(initial_state, config=None): # 添加 config=None 以匹配 astream 的新签名
                # 模拟来自不同 agent 的输出
                yield {"data_collector": {"analysis_results": {"data_collector": "Collected data for FAKE"}}}
                yield {"technical_analyst": {"analysis_results": {"technical_analyst": "Technical analysis complete"}}}
                yield {"fundamental_analyst": {"analysis_results": {"fundamental_analyst": "Fundamental analysis complete"}}}
                yield {"news_sentiment_analyst": {"analysis_results": {"news_sentiment_analyst": "News analysis complete"}}}
                yield {"synthesis": {"final_report": "Final synthesis report."}}

            mock_app.astream.side_effect = mock_astream

            # 运行分析并收集结果
            async for chunk in run_ai_analysis(ticker):
                print(f"收到数据块: {chunk.strip()}")
                if chunk.startswith("data:"):
                    try:
                        data_content = chunk[len("data:"):].strip()
                        if data_content: # 确保不解析空字符串
                            agent_outputs.append(json.loads(data_content))
                    except json.JSONDecodeError as e:
                        print(f"JSON 解码错误: {e}, 数据: '{data_content}'")


        print("\n=== 分析流产出 ===")
        for i, output in enumerate(agent_outputs, 1):
            print(f"{i}. Agent: {output.get('agent')}, Output: {output.get('output')}")

        # 验证结果
        assert len(agent_outputs) == 5, f"预期有 5 个 agent 的输出, 但收到了 {len(agent_outputs)} 个"
        print("✅ 收到了预期数量的 Agent 输出")

        agent_names = [output['agent'] for output in agent_outputs]
        expected_agents = ['data_collector', 'technical_analyst', 'fundamental_analyst', 'news_sentiment_analyst', 'synthesis']
        assert all(name in agent_names for name in expected_agents), f"输出的 Agent 名称不匹配: {agent_names}"
        print("✅ 所有预期的 Agent 都已执行")

        final_report = agent_outputs[-1]['output']
        assert final_report == "Final synthesis report.", "最终报告内容不符合预期"
        print("✅ 最终报告已正确生成")
        
        print("\n🎉 AI 分析工作流测试通过！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    print("StockAIvo LangGraph Orchestrator 测试")
    print("=" * 50)
    
    await test_run_ai_analysis()

if __name__ == "__main__":
    asyncio.run(main())