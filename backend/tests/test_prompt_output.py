"""
测试AI Agent Prompt输出

这个测试程序用于验证和展示各个AI Agent的完整Prompt输出，
可以真实获取数据并生成实际的Prompt内容。

使用方法:
    uv run python tests/test_prompt_output.py --agent structured_prediction --ticker AAPL
    uv run python tests/test_prompt_output.py --agent technical_analysis --ticker MSFT
    uv run python tests/test_prompt_output.py --agent synthesis --ticker TSLA
"""

import asyncio
import argparse
import logging
from datetime import date, datetime
from typing import Optional

# 设置日志级别为INFO，避免过多debug信息
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入相关模块
from stockaivo.ai.state import GraphState
from stockaivo.ai.agents import (
    data_collection_agent,
    technical_analysis_agent,
    fundamental_analysis_agent,
    news_sentiment_analysis_agent,
    _build_structured_prediction_prompt,
    _build_technical_analysis_prompt,
    _build_synthesis_prompt,
    _process_technical_analysis_data,
    _extract_analysis_results
)


class PromptTester:
    """AI Agent Prompt测试器"""
    
    def __init__(self, ticker: str, end_date: Optional[str] = None):
        self.ticker = ticker.upper()
        self.end_date = end_date
        self.state: Optional[GraphState] = None
    
    async def setup_analysis_state(self, agent_type=None):
        """设置分析状态，执行必要的数据收集和分析
        
        Args:
            agent_type: 目标Agent类型，用于优化依赖执行
        """
        print(f"\n🚀 开始为 {self.ticker} 设置分析状态...")
        
        # 初始化GraphState
        custom_date_range = None
        if self.end_date:
            custom_date_range = {"end_date": self.end_date}
        
        self.state = GraphState(
            ticker=self.ticker,
            custom_date_range=custom_date_range,
            raw_data={},
            analysis_results={},
            final_report="",
            market_analysis=None
        )
        
        try:
            # 步骤1: 数据收集（所有Agent都需要）
            print("📊 执行数据收集...")
            data_result = await data_collection_agent(self.state)
            for key, value in data_result.items():
                if key in self.state:
                    self.state[key] = value
            
            # 根据目标Agent类型，智能执行依赖分析
            if agent_type == 'technical_analysis':
                print("🎯 目标: 技术分析Prompt - 只执行技术分析")
                await self._run_technical_analysis_only()
            elif agent_type == 'synthesis':
                print("🎯 目标: 综合分析Prompt - 执行所有分析")
                await self._run_all_analyses()
            elif agent_type == 'structured_prediction':
                print("🎯 目标: 结构化预测Prompt - 执行所有分析") 
                await self._run_all_analyses()
            else:
                # 默认执行所有分析
                print("🚀 并行执行所有分析...")
                await self._run_all_analyses()
            
            print("✅ 分析状态设置完成!\n")
            
        except Exception as e:
            print(f"❌ 设置分析状态时出错: {e}")
            raise
    
    async def _run_technical_analysis_only(self):
        """只执行技术分析"""
        from stockaivo.ai.agents import technical_analysis_agent_stream

        if self.state is None:
            raise ValueError("分析状态未初始化，请先调用setup_analysis_state()")
        state = self.state
        
        print("📈 执行技术分析...")
        try:
            result = None
            async for chunk_result in technical_analysis_agent_stream(state):
                for key, value in chunk_result.items():
                    if key == 'analysis_results':
                        # 合并analysis_results而不是替换，保留data_collector信息
                        current_analysis = state.get("analysis_results", {})
                        current_analysis.update(value)
                        state[key] = current_analysis
                    else:
                        state[key] = value
                    # 保存最后的技术分析结果
                    if key == 'analysis_results' and 'technical_analyst' in value:
                        result = value['technical_analyst']
            
            # 确保结果保存到state
            analysis_results = state.get("analysis_results", {})
            if result is not None:
                analysis_results["technical_analyst"] = result
                state["analysis_results"] = analysis_results
            
            print("✅ 技术分析完成")
        except Exception as e:
            print(f"❌ 技术分析失败: {e}")
    
    async def _run_all_analyses(self):
        """并行执行所有分析"""
        from stockaivo.ai.agents import (
            technical_analysis_agent_stream,
            fundamental_analysis_agent_stream, 
            news_sentiment_analysis_agent_stream
        )

        if self.state is None:
            raise ValueError("分析状态未初始化，请先调用setup_analysis_state()")
        state = self.state
        
        # 定义并行分析任务
        async def run_technical_analysis():
            """执行技术分析"""
            print("📈 开始技术分析...")
            try:
                result = None
                async for chunk_result in technical_analysis_agent_stream(state):
                    for key, value in chunk_result.items():
                        if key == 'analysis_results':
                            # 合并analysis_results而不是替换，保留data_collector信息
                            current_analysis = state.get("analysis_results", {})
                            current_analysis.update(value)
                            state[key] = current_analysis
                        else:
                            state[key] = value
                        # 保存最后的技术分析结果
                        if key == 'analysis_results' and 'technical_analyst' in value:
                            result = value['technical_analyst']
                print("✅ 技术分析完成")
                return ('technical_analyst', result)
            except Exception as e:
                print(f"❌ 技术分析失败: {e}")
                return ('technical_analyst', None)
        
        async def run_fundamental_analysis():
            """执行基本面分析"""
            print("💼 开始基本面分析...")
            try:
                result = None
                async for chunk_result in fundamental_analysis_agent_stream(state):
                    for key, value in chunk_result.items():
                        if key == 'analysis_results':
                            # 合并analysis_results而不是替换，保留data_collector信息
                            current_analysis = state.get("analysis_results", {})
                            current_analysis.update(value)
                            state[key] = current_analysis
                        else:
                            state[key] = value
                        # 保存最后的基本面分析结果
                        if key == 'analysis_results' and 'fundamental_analyst' in value:
                            result = value['fundamental_analyst']
                print("✅ 基本面分析完成")
                return ('fundamental_analyst', result)
            except Exception as e:
                print(f"⚠️  基本面分析跳过: {e}")
                return ('fundamental_analyst', None)
        
        async def run_news_sentiment_analysis():
            """执行新闻情感分析"""
            print("📰 开始新闻情感分析...")
            try:
                result = None
                async for chunk_result in news_sentiment_analysis_agent_stream(state):
                    for key, value in chunk_result.items():
                        if key == 'analysis_results':
                            # 合并analysis_results而不是替换，保留data_collector信息
                            current_analysis = state.get("analysis_results", {})
                            current_analysis.update(value)
                            state[key] = current_analysis
                        else:
                            state[key] = value
                        # 保存最后的新闻分析结果
                        if key == 'analysis_results' and 'news_sentiment_analyst' in value:
                            result = value['news_sentiment_analyst']
                print("✅ 新闻情感分析完成")
                return ('news_sentiment_analyst', result)
            except Exception as e:
                print(f"⚠️  新闻情感分析跳过: {e}")
                return ('news_sentiment_analyst', None)
        
        # 并行执行所有分析
        analysis_tasks = [
            run_technical_analysis(),
            run_fundamental_analysis(), 
            run_news_sentiment_analysis()
        ]
        
        # 等待所有分析完成
        analysis_results_list = await asyncio.gather(*analysis_tasks, return_exceptions=True)
        
        # 整合分析结果到state中
        analysis_results = state.get("analysis_results", {})
        for item in analysis_results_list:
            if isinstance(item, BaseException):
                logger.warning("分析任务执行失败: %s", item)
                continue
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            agent_type, result = item
            if result is not None:
                analysis_results[agent_type] = result
        state["analysis_results"] = analysis_results
        
        print("🎉 并行分析全部完成!")
    
    def test_structured_prediction_prompt(self):
        """测试结构化预测Prompt"""
        if self.state is None:
            raise ValueError("分析状态未初始化，请先调用setup_analysis_state()")
        
        print("=" * 80)
        print("🎯 STRUCTURED PREDICTION PROMPT OUTPUT")
        print("=" * 80)
        
        prompt = _build_structured_prediction_prompt(self.state)
        
        print(prompt)
        print("\n" + "=" * 80)
        print("🎯 STRUCTURED PREDICTION PROMPT END")
        print("=" * 80)
        
        return prompt
    
    def test_technical_analysis_prompt(self):
        """测试技术分析Prompt"""
        if self.state is None:
            raise ValueError("分析状态未初始化，请先调用setup_analysis_state()")
        
        print("=" * 80)
        print("📈 TECHNICAL ANALYSIS PROMPT OUTPUT")
        print("=" * 80)
        
        # 处理技术分析数据
        ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(self.state)
        
        # 获取market_analysis
        market_analysis = self.state.get("market_analysis")
        market_aware_date = market_analysis.market_aware_date if market_analysis else None
        
        prompt = _build_technical_analysis_prompt(
            ticker, daily_price_str, weekly_price_str, tenmin_price_str,
            daily_indicators, weekly_indicators, tenmin_indicators, market_aware_date
        )
        
        print(prompt)
        print("\n" + "=" * 80)
        print("📈 TECHNICAL ANALYSIS PROMPT END")
        print("=" * 80)
        
        return prompt
    
    def test_synthesis_prompt(self):
        """测试综合分析Prompt"""
        if self.state is None:
            raise ValueError("分析状态未初始化，请先调用setup_analysis_state()")
        
        print("=" * 80)
        print("🔄 SYNTHESIS PROMPT OUTPUT")
        print("=" * 80)
        
        # 提取分析结果
        data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(self.state)
        
        # 获取market_analysis
        market_analysis = self.state.get("market_analysis")
        market_aware_date = market_analysis.market_aware_date if market_analysis else None
        
        prompt = _build_synthesis_prompt(
            self.ticker, data_collector_result, technical_result,
            fundamental_result, news_result, available_analyses, market_aware_date
        )
        
        print(prompt)
        print("\n" + "=" * 80)
        print("🔄 SYNTHESIS PROMPT END")
        print("=" * 80)
        
        return prompt
    
    def print_analysis_summary(self):
        """打印分析状态摘要信息"""
        if self.state is None:
            return
        
        print("\n📋 分析状态摘要:")
        print(f"  - 股票代码: {self.ticker}")
        print(f"  - 结束日期: {self.end_date or '默认(市场感知日期)'}")
        
        # 数据摘要
        raw_data = self.state.get("raw_data", {})
        print(f"  - 可用数据集: {list(raw_data.keys())}")
        
        # 详细检查价格数据状态
        daily_prices_data = raw_data.get("daily_prices")
        if daily_prices_data:
            import pandas as pd
            try:
                daily_price_df = pd.DataFrame(daily_prices_data['data'], columns=daily_prices_data['columns'], index=daily_prices_data['index'])
                if not daily_price_df.empty and 'close' in daily_price_df.columns:
                    latest_close = daily_price_df['close'].iloc[-1]
                    print(f"  - 日线数据: {len(daily_price_df)} 行，最新收盘价: ${latest_close:.2f}")
                else:
                    print("  - 日线数据: DataFrame为空或缺少close列")
            except Exception as e:
                print(f"  - 日线数据解析错误: {e}")
        else:
            print("  - 日线数据: 不可用")
        
        # 分析结果摘要
        analysis_results = self.state.get("analysis_results", {})
        print(f"  - 已完成分析: {list(analysis_results.keys())}")
        
        # 检查各分析结果的长度
        for key, value in analysis_results.items():
            if isinstance(value, str):
                print(f"    * {key}: {len(value)} 字符")
            else:
                print(f"    * {key}: {type(value)}")
        
        # 市场分析信息
        market_analysis = self.state.get("market_analysis")
        if market_analysis:
            print(f"  - 市场感知日期: {market_analysis.market_aware_date}")
            print(f"  - 目标周五: {market_analysis.target_friday}")
            print(f"  - 交易日数量: {market_analysis.trading_days_count}")
    
    def debug_structured_prediction_data(self):
        """调试结构化预测所需的数据状态"""
        if self.state is None:
            print("❌ 分析状态未初始化")
            return
            
        print("\n🔍 STRUCTURED PREDICTION 数据调试:")
        print("=" * 50)
        
        # 检查 raw_data
        raw_data = self.state.get("raw_data", {})
        print(f"1. raw_data 键: {list(raw_data.keys())}")
        
        # 检查日线价格数据
        daily_prices_data = raw_data.get("daily_prices")
        if daily_prices_data:
            print("2. daily_prices_data 结构:")
            print(f"   - 键: {list(daily_prices_data.keys())}")
            if 'data' in daily_prices_data and daily_prices_data['data']:
                print(f"   - 数据行数: {len(daily_prices_data['data'])}")
                print(f"   - 列: {daily_prices_data.get('columns', [])}")
                
                # 尝试解析DataFrame
                try:
                    import pandas as pd
                    daily_price_df = pd.DataFrame(
                        daily_prices_data['data'], 
                        columns=daily_prices_data['columns'], 
                        index=daily_prices_data['index']
                    )
                    if not daily_price_df.empty and 'close' in daily_price_df.columns:
                        latest_close = daily_price_df['close'].iloc[-1]
                        upside_target = latest_close * 1.03
                        downside_target = latest_close * 0.97
                        print(f"   ✅ 价格数据解析成功:")
                        print(f"      - 最新收盘价: ${latest_close:.2f}")
                        print(f"      - 上涨目标: ${upside_target:.2f} (+3%)")
                        print(f"      - 下跌目标: ${downside_target:.2f} (-3%)")
                    else:
                        print("   ❌ DataFrame为空或缺少close列")
                except Exception as e:
                    print(f"   ❌ DataFrame解析失败: {e}")
            else:
                print("   ❌ daily_prices_data 无数据")
        else:
            print("2. ❌ daily_prices_data 不存在")
            
        # 检查分析结果
        analysis_results = self.state.get("analysis_results", {})
        print(f"3. analysis_results 键: {list(analysis_results.keys())}")
        
        # 检查市场分析
        market_analysis = self.state.get("market_analysis")
        if market_analysis:
            print(f"4. market_analysis: ✅")
            print(f"   - 日期: {market_analysis.market_aware_date}")
            print(f"   - 目标: {market_analysis.target_friday}")
        else:
            print("4. market_analysis: ❌ 不存在")
            
        print("=" * 50)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='测试AI Agent Prompt输出')
    parser.add_argument('--agent', 
                       choices=['structured_prediction', 'technical_analysis', 'synthesis'], 
                       required=True, 
                       help='要测试的Agent类型')
    parser.add_argument('--ticker', 
                       required=True, 
                       help='股票代码 (例如: AAPL, MSFT, TSLA)')
    parser.add_argument('--end_date', 
                       help='自定义结束日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--save_to_file', 
                       help='保存Prompt到指定文件')
    
    args = parser.parse_args()
    
    # 验证日期格式
    if args.end_date:
        try:
            datetime.strptime(args.end_date, '%Y-%m-%d')
        except ValueError:
            print("❌ 错误: 日期格式必须是 YYYY-MM-DD")
            return
    
    print(f"🧪 开始测试 {args.agent} Agent 的 Prompt 输出")
    print(f"📊 股票代码: {args.ticker}")
    if args.end_date:
        print(f"📅 结束日期: {args.end_date}")
    
    try:
        # 创建测试器
        tester = PromptTester(args.ticker, args.end_date)
        
        # 设置分析状态（根据目标Agent优化执行）
        await tester.setup_analysis_state(agent_type=args.agent)
        
        # 打印分析摘要
        tester.print_analysis_summary()
        
        # 根据用户选择测试相应的Prompt
        prompt_output = None
        if args.agent == 'structured_prediction':
            prompt_output = tester.test_structured_prediction_prompt()
        elif args.agent == 'technical_analysis':
            prompt_output = tester.test_technical_analysis_prompt()
        elif args.agent == 'synthesis':
            prompt_output = tester.test_synthesis_prompt()
        
        # 保存到文件（如果指定）
        if args.save_to_file and prompt_output:
            with open(args.save_to_file, 'w', encoding='utf-8') as f:
                f.write(f"# {args.agent.upper()} PROMPT OUTPUT\n")
                f.write(f"# Stock: {args.ticker}\n")
                f.write(f"# Date: {args.end_date or 'Default'}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
                f.write(prompt_output)
            print(f"\n💾 Prompt已保存到: {args.save_to_file}")
        
        print(f"\n✅ {args.agent} Prompt 测试完成!")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        logger.exception("测试过程中出现异常")


if __name__ == "__main__":
    asyncio.run(main())
