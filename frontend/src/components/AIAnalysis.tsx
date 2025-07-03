import React, { useState, useRef } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Calendar, Play, Square } from 'lucide-react';

interface AIAnalysisProps {
  selectedStock: string | null;
  stockName: string | null;
}

const AIAnalysis: React.FC<AIAnalysisProps> = ({ selectedStock, stockName }) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState('');
  const [dateRange, setDateRange] = useState('past_30_days');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);

  const handleStartAnalysis = async () => {
    if (!selectedStock) {
      alert('请先选择一只股票');
      return;
    }

    setIsAnalyzing(true);
    setAnalysisResult('');

    try {
      // 准备请求数据
      const requestData = {
        summary: `分析股票 ${selectedStock}`,
        value: {
          ticker: selectedStock,
          ...(dateRange === 'custom' && startDate && endDate
            ? {
                start_date: startDate,
                end_date: endDate,
              }
            : {
                date_range_option: dateRange,
              }),
        },
      };

      // 发送 POST 请求启动分析
      const response = await fetch('http://127.0.0.1:8000/ai/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // 建立 EventSource 连接
      const eventSource = new EventSource('http://127.0.0.1:8000/ai/analyze');
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.content) {
            setAnalysisResult((prev) => prev + data.content);
          }
        } catch (error) {
          console.error('解析消息失败:', error);
        }
      };

      eventSource.addEventListener('end', () => {
        setIsAnalyzing(false);
        eventSource.close();
        eventSourceRef.current = null;
      });

      eventSource.onerror = (error) => {
        console.error('EventSource 错误:', error);
        setIsAnalyzing(false);
        eventSource.close();
        eventSourceRef.current = null;
      };
    } catch (error) {
      console.error('启动分析失败:', error);
      setIsAnalyzing(false);
      setAnalysisResult('分析启动失败，请检查网络连接或稍后重试。');
    }
  };

  const handleStopAnalysis = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsAnalyzing(false);
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          AI 智能分析
          {selectedStock && (
            <span className="text-sm font-normal text-gray-600">
              - {selectedStock} {stockName}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 日期范围选择 */}
        <div className="space-y-2">
          <label className="text-sm font-medium">分析时间范围</label>
          <Select value={dateRange} onValueChange={setDateRange}>
            <SelectTrigger>
              <SelectValue placeholder="选择时间范围" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="past_30_days">过去30天</SelectItem>
              <SelectItem value="past_60_days">过去60天</SelectItem>
              <SelectItem value="past_90_days">过去90天</SelectItem>
              <SelectItem value="past_8_weeks">过去8周</SelectItem>
              <SelectItem value="past_16_weeks">过去16周</SelectItem>
              <SelectItem value="past_24_weeks">过去24周</SelectItem>
              <SelectItem value="custom">自定义日期</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* 自定义日期输入 */}
        {dateRange === 'custom' && (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">开始日期</label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">结束日期</label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
        )}

        {/* 分析按钮 */}
        <div className="flex gap-2">
          <Button
            onClick={handleStartAnalysis}
            disabled={isAnalyzing || !selectedStock}
            className="flex items-center gap-2"
          >
            <Play className="h-4 w-4" />
            {isAnalyzing ? '分析中...' : '开始分析'}
          </Button>
          {isAnalyzing && (
            <Button
              onClick={handleStopAnalysis}
              variant="outline"
              className="flex items-center gap-2"
            >
              <Square className="h-4 w-4" />
              停止分析
            </Button>
          )}
        </div>

        {/* 分析结果显示 */}
        <div className="space-y-2">
          <label className="text-sm font-medium">分析结果</label>
          <div className="min-h-[200px] max-h-[400px] overflow-y-auto p-4 border rounded-md bg-gray-50">
            {analysisResult ? (
              <pre className="whitespace-pre-wrap text-sm">{analysisResult}</pre>
            ) : (
              <div className="text-gray-500 text-sm">
                {isAnalyzing ? '正在分析中，请稍候...' : '点击"开始分析"按钮开始AI分析'}
              </div>
            )}
          </div>
        </div>

        {isAnalyzing && (
          <div className="text-xs text-gray-500">
            💡 分析过程中会实时显示结果，请耐心等待分析完成
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default AIAnalysis;
