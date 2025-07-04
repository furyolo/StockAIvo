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
}

function App() {
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const [stockName, setStockName] = useState<string | null>(null);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'hourly'>('daily');
  const [isLoading, setIsLoading] = useState(false);

  const handleSelectStock = (symbol: string, name: string) => {
    setSelectedStock(symbol);
    setStockName(name);
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
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    股票图表
                    {selectedStock && (
                      <span className="text-sm font-normal text-gray-600">
                        - {selectedStock} {stockName}
                      </span>
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
                    <TradingViewChart data={chartData} height={500} />
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
