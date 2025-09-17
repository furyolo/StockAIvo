import { useState, useEffect } from 'react';
import { Container, Title, Text, Paper, Group, Select, Button, Stack, Center, Loader } from '@mantine/core';
import { IconTrendingUp, IconChartBar, IconRefresh } from '@tabler/icons-react';
import StockSearch from './components/StockSearch';
import TradingViewChart from './components/TradingViewChart';
import AIAnalysis from './components/AIAnalysis';

// 定义API响应数据类型
interface StockDataItem {
  date?: string;
  timestamp_10min?: string;
  minute_timestamp?: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume?: string;
  price_change?: string;
  price_change_percent?: string;
}

interface ChartData {
  time?: string;
  date?: string;
  minute_timestamp?: string;
  timestamp_10min?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  price_change?: number;
  price_change_percent?: number;
}

function App() {
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const [stockName, setStockName] = useState<string | null>(null);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [period, setPeriod] = useState<'daily' | 'weekly' | '10min' | 'minute'>('daily');
  const [isLoading, setIsLoading] = useState(false);
  const [currentOHLC, setCurrentOHLC] = useState<ChartData | null>(null);

  const handleSelectStock = (symbol: string, name: string) => {
    setSelectedStock(symbol);
    setStockName(name);
    setCurrentOHLC(null); // 重置 OHLC 数据
  };

  const handleOHLCChange = (ohlc: ChartData | null) => {
    setCurrentOHLC(ohlc);
  };

  // 计算涨跌颜色 - 与K线一致，基于当日收盘价 vs 开盘价
  const getPriceColor = (ohlc: ChartData) => {
    const closePrice = ohlc.close;
    const openPrice = ohlc.open;
    if (closePrice > openPrice) return 'text-green-600'; // 当日上涨（收盘 > 开盘）
    if (closePrice < openPrice) return 'text-red-600'; // 当日下跌（收盘 < 开盘）
    return 'text-black'; // 平盘（收盘 = 开盘）
  };

  const fetchStockData = async (symbol: string, selectedPeriod: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/stocks/${symbol}/${selectedPeriod}`
      );

      if (response.ok) {
        const data = await response.json();
        const formattedData: ChartData[] = data.data.map((item: StockDataItem) => ({
          time: item.date || item.timestamp_10min || item.minute_timestamp,
          date: item.date,
          timestamp_10min: item.timestamp_10min,
          minute_timestamp: item.minute_timestamp,
          open: parseFloat(item.open),
          high: parseFloat(item.high),
          low: parseFloat(item.low),
          close: parseFloat(item.close),
          volume: item.volume ? parseInt(item.volume) : undefined,
          price_change: item.price_change ? parseFloat(item.price_change) : undefined,
          price_change_percent: item.price_change_percent ? parseFloat(item.price_change_percent) : undefined,
        }));
        setChartData(formattedData);
      } else {
        console.error('获取股票数据失败:', response.statusText);
        setChartData([]);
      }
    } catch (error) {
      console.error('获取股票数据错误:', error);
      setChartData([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedStock) {
      fetchStockData(selectedStock, period);
    }
  }, [selectedStock, period]);

  const handleRefresh = () => {
    if (selectedStock) {
      fetchStockData(selectedStock, period);
    }
  };



  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f7f8fa' }}>
      <Container size="xl" py="md">
        <Stack gap="lg">
          {/* 头部 */}
          <Paper 
            p="lg" 
            style={{ 
              backgroundColor: '#ffffff',
              border: '1px solid #e1e4e8',
              borderRadius: '8px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            }}
          >
            <Center>
              <Stack gap="xs" align="center">
                <Group gap="sm">
                  <div
                    style={{
                      padding: '8px',
                      backgroundColor: '#0066cc',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <IconTrendingUp size={24} color="white" />
                  </div>
                  <Title order={1} c="#1a1a1a" style={{ fontWeight: 600 }}>StockAIvo</Title>
                </Group>
                <Text c="#8a8a8a" size="sm">智能美股数据与分析平台</Text>
              </Stack>
            </Center>
          </Paper>

          {/* 搜索栏 */}
          <Center>
            <StockSearch onSelectStock={handleSelectStock} />
          </Center>

          {/* 主要内容区域 */}
          <Stack gap="lg">
            {/* 图表区域 */}
            <Paper 
              p="lg" 
              style={{ 
                backgroundColor: '#ffffff',
                border: '1px solid #e1e4e8',
                borderRadius: '8px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
              }}
            >
              <Stack gap="md">
                {/* 标题行包含图表名称、股票信息、OHLC信息、时间选择器和刷新按钮 */}
                <Group justify="space-between" align="center" wrap="wrap">
                  <Group gap="sm" align="center" wrap="wrap">
                    <Group gap="xs" align="center">
                      <IconChartBar size={20} />
                      <Text fw={500}>股票图表</Text>
                    </Group>
                    {selectedStock && (
                      <Text size="sm" c="dimmed">
                        - {selectedStock} {stockName}
                      </Text>
                    )}
                    {/* OHLC 信息显示 */}
                    {currentOHLC && (
                      <Group gap="md" style={{ fontSize: '0.875rem', fontFamily: 'monospace' }}>
                        <span>
                          <span style={{ color: 'black' }}>开=</span>
                          <span style={{ color: getPriceColor(currentOHLC) === 'text-green-600' ? 'var(--mantine-color-green-6)' : getPriceColor(currentOHLC) === 'text-red-600' ? 'var(--mantine-color-red-6)' : 'black' }}>
                            {currentOHLC.open.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: 'black' }}>高=</span>
                          <span style={{ color: getPriceColor(currentOHLC) === 'text-green-600' ? 'var(--mantine-color-green-6)' : getPriceColor(currentOHLC) === 'text-red-600' ? 'var(--mantine-color-red-6)' : 'black' }}>
                            {currentOHLC.high.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: 'black' }}>低=</span>
                          <span style={{ color: getPriceColor(currentOHLC) === 'text-green-600' ? 'var(--mantine-color-green-6)' : getPriceColor(currentOHLC) === 'text-red-600' ? 'var(--mantine-color-red-6)' : 'black' }}>
                            {currentOHLC.low.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span style={{ color: 'black' }}>收=</span>
                          <span style={{ color: getPriceColor(currentOHLC) === 'text-green-600' ? 'var(--mantine-color-green-6)' : getPriceColor(currentOHLC) === 'text-red-600' ? 'var(--mantine-color-red-6)' : 'black' }}>
                            {currentOHLC.close.toFixed(2)}
                            {currentOHLC.price_change !== undefined && currentOHLC.price_change_percent !== undefined && (
                              <>
                                {' '}
                                {currentOHLC.price_change >= 0 ? '+' : ''}
                                {currentOHLC.price_change.toFixed(2)}
                                （{currentOHLC.price_change_percent >= 0 ? '+' : ''}
                                {currentOHLC.price_change_percent.toFixed(2)}%）
                              </>
                            )}
                          </span>
                        </span>
                      </Group>
                    )}
                  </Group>
                  
                  {/* 右侧控制区域 */}
                  <Group gap="xs" align="center">
                    <Select
                      value={period}
                      onChange={(value) => setPeriod(value as 'daily' | 'weekly' | '10min' | 'minute')}
                      data={[
                        { value: 'daily', label: '日线' },
                        { value: 'weekly', label: '周线' },
                        { value: '10min', label: '10分钟线' },
                        { value: 'minute', label: '分钟线' },
                      ]}
                      w={120}
                      size="sm"
                    />
                    <Button
                      onClick={handleRefresh}
                      disabled={!selectedStock || isLoading}
                      size="compact-sm"
                      variant="light"
                    >
                      <IconRefresh size={16} style={{ animation: isLoading ? 'spin 1s linear infinite' : 'none' }} />
                    </Button>
                  </Group>
                </Group>
                
                <div style={{ minHeight: '400px' }}>
                  {selectedStock ? (
                    isLoading ? (
                      <Center h={400}>
                        <Stack gap="sm" align="center">
                          <Loader />
                          <Text c="dimmed">加载中...</Text>
                        </Stack>
                      </Center>
                    ) : chartData.length > 0 ? (
                      <TradingViewChart
                        data={chartData}
                        height={500}
                        period={period}
                        onOHLCChange={handleOHLCChange}
                      />
                    ) : (
                      <Center h={400}>
                        <Text c="dimmed">暂无数据</Text>
                      </Center>
                    )
                  ) : (
                    <Center h={400}>
                      <Text c="dimmed">请选择一只股票查看图表</Text>
                    </Center>
                  )}
                </div>
              </Stack>
            </Paper>

            {/* AI 分析区域 */}
            <AIAnalysis selectedStock={selectedStock} stockName={stockName} />
          </Stack>
        </Stack>
      </Container>
    </div>
  );
}

export default App;
