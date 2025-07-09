import { useState, useEffect } from 'react';
import StockSearch from './components/StockSearch';
import TradingViewChart from './components/TradingViewChart';
import AIAnalysis from './components/AIAnalysis';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select';
import { Button } from './components/ui/button';
import { TrendingUp, BarChart3, RefreshCw } from 'lucide-react';

interface ChartData {
  time: string;
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
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'hourly'>('daily');
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
        const formattedData: ChartData[] = data.data.map((item: any) => ({
          time: item.date || item.hour_timestamp,
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
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* 头部 */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center justify-center gap-2">
            <TrendingUp className="h-8 w-8 text-blue-600" />
            StockAIvo
          </h1>
          <p className="text-gray-600">智能美股数据与分析平台</p>
        </div>

        {/* 搜索栏 */}
        <div className="flex justify-center">
          <StockSearch onSelectStock={handleSelectStock} />
        </div>

        {/* 主要内容区域 - 上下布局 */}
        <div className="space-y-6">
          {/* 图表区域 */}
          <div className="w-full">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 flex-wrap">
                    <BarChart3 className="h-5 w-5" />
                    股票图表
                    {selectedStock && (
                      <span className="text-sm font-normal text-gray-600">
                        - {selectedStock} {stockName}
                      </span>
                    )}
                    {/* OHLC 信息显示 */}
                    {currentOHLC && (
                      <div className="flex items-center gap-3 text-sm font-mono ml-4">
                        <span>
                          <span className="text-black">开=</span>
                          <span className={getPriceColor(currentOHLC)}>
                            {currentOHLC.open.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span className="text-black">高=</span>
                          <span className={getPriceColor(currentOHLC)}>
                            {currentOHLC.high.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span className="text-black">低=</span>
                          <span className={getPriceColor(currentOHLC)}>
                            {currentOHLC.low.toFixed(2)}
                          </span>
                        </span>
                        <span>
                          <span className="text-black">收=</span>
                          <span className={getPriceColor(currentOHLC)}>
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
                      </div>
                    )}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Select value={period} onValueChange={(value: any) => setPeriod(value)}>
                      <SelectTrigger className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="daily">日线</SelectItem>
                        <SelectItem value="weekly">周线</SelectItem>
                        <SelectItem value="hourly">小时线</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button
                      onClick={handleRefresh}
                      disabled={!selectedStock || isLoading}
                      size="sm"
                      variant="outline"
                    >
                      <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {selectedStock ? (
                  isLoading ? (
                    <div className="flex items-center justify-center h-96">
                      <div className="text-gray-500">加载中...</div>
                    </div>
                  ) : chartData.length > 0 ? (
                    <TradingViewChart
                      data={chartData}
                      height={500}
                      onOHLCChange={handleOHLCChange}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-96">
                      <div className="text-gray-500">暂无数据</div>
                    </div>
                  )
                ) : (
                  <div className="flex items-center justify-center h-96">
                    <div className="text-gray-500">请选择一只股票查看图表</div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* AI 分析区域 */}
          <div className="w-full">
            <AIAnalysis selectedStock={selectedStock} stockName={stockName} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
