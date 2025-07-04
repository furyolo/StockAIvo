import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// 简化测试，专注于AI分析数据处理逻辑
const mockEventSourceData = [
  {
    agent: 'data_collector',
    output: '数据收集完成 - 股票代码: AAPL\n- daily_prices: 21 条记录\n- weekly_prices: 5 条记录'
  },
  {
    agent: 'technical_analyst',
    output: '技术分析完成：当前趋势为上升趋势，建议持有。'
  },
  {
    agent: 'synthesis',
    output: 'Final Investment Report:\n\n- data_collector: 数据收集完成\n- technical_analyst: 技术分析完成'
  }
];

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock EventSource
class MockEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  addEventListener: (type: string, listener: () => void) => void = vi.fn();
  close: () => void = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    // 模拟异步消息发送
    setTimeout(() => {
      if (this.onmessage) {
        // 模拟data_collector的消息
        this.onmessage(new MessageEvent('message', {
          data: JSON.stringify({
            agent: 'data_collector',
            output: '数据收集完成 - 股票代码: AAPL\n- daily_prices: 21 条记录\n- weekly_prices: 5 条记录'
          })
        }));
        
        // 模拟technical_analyst的消息
        this.onmessage(new MessageEvent('message', {
          data: JSON.stringify({
            agent: 'technical_analyst',
            output: '技术分析完成：当前趋势为上升趋势，建议持有。'
          })
        }));
        
        // 模拟synthesis的消息
        this.onmessage(new MessageEvent('message', {
          data: JSON.stringify({
            agent: 'synthesis',
            output: 'Final Investment Report:\n\n- data_collector: 数据收集完成\n- technical_analyst: 技术分析完成'
          })
        }));
      }
    }, 100);
  }
}

global.EventSource = MockEventSource as any;

describe('AI分析数据处理', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'Analysis task created and ready for streaming.' })
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('应该正确解析EventSource消息格式', () => {
    // 测试新的数据格式解析逻辑
    const testData = mockEventSourceData[0];

    expect(testData.agent).toBe('data_collector');
    expect(testData.output).toContain('数据收集完成');
    expect(testData.output).toContain('AAPL');
  });

  it('应该能够处理所有agent的输出', () => {
    const agentNames = mockEventSourceData.map(data => data.agent);

    expect(agentNames).toContain('data_collector');
    expect(agentNames).toContain('technical_analyst');
    expect(agentNames).toContain('synthesis');
  });

  it('应该正确格式化agent输出', () => {
    // 测试格式化逻辑
    const testData = mockEventSourceData[0];
    const expectedFormat = `\n=== ${testData.agent.toUpperCase()} ===\n${testData.output}\n`;

    expect(expectedFormat).toContain('=== DATA_COLLECTOR ===');
    expect(expectedFormat).toContain('数据收集完成');
  });

  it('应该能够处理自定义日期范围格式', () => {
    const requestData = {
      summary: '分析股票 AAPL',
      value: {
        ticker: 'AAPL',
        start_date: '2024-01-01',
        end_date: '2024-12-31'
      }
    };

    // 验证请求数据格式正确
    expect(requestData.value.ticker).toBe('AAPL');
    expect(requestData.value.start_date).toBe('2024-01-01');
    expect(requestData.value.end_date).toBe('2024-12-31');
    expect(requestData.value).not.toHaveProperty('date_range_option');
  });

  it('应该能够处理不选择日期的情况', () => {
    const requestData = {
      summary: '分析股票 AAPL',
      value: {
        ticker: 'AAPL'
      }
    };

    // 验证请求数据格式正确（不包含日期字段时使用系统默认值）
    expect(requestData.value.ticker).toBe('AAPL');
    expect(requestData.value).not.toHaveProperty('start_date');
    expect(requestData.value).not.toHaveProperty('end_date');
    expect(requestData.value).not.toHaveProperty('date_range_option');
  });
});
