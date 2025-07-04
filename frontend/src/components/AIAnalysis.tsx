import { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { DateRangePicker, type DateRange } from './ui/date-range-picker';
import { Play, Square, Sparkles, TrendingUp } from 'lucide-react';

interface AIAnalysisProps {
  selectedStock: string | null;
  stockName: string | null;
}

const AIAnalysis: React.FC<AIAnalysisProps> = ({ selectedStock, stockName }) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState('');
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const eventSourceRef = useRef<EventSource | null>(null);

  const handleStartAnalysis = async (e: React.MouseEvent) => {
    e.preventDefault(); // 防止表单提交或页面跳转

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
          // 如果用户选择了日期范围，则使用用户选择的日期；否则不传日期，让后端使用默认值
          ...(dateRange?.from && dateRange?.to && {
            start_date: dateRange.from.toISOString().split('T')[0],
            end_date: dateRange.to.toISOString().split('T')[0],
          }),
        },
      };

      // 发送 POST 请求并直接获取流式响应
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

      // 处理流式响应
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('无法获取响应流');
      }

      // 存储reader引用以便停止分析时使用
      eventSourceRef.current = { close: () => reader.cancel() } as any;

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          setIsAnalyzing(false);
          eventSourceRef.current = null;
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6); // 移除 "data: " 前缀
              if (jsonStr.trim()) {
                const data = JSON.parse(jsonStr);
                console.log('收到AI分析数据:', data);

                if (data.error) {
                  setAnalysisResult((prev) => prev + `\n**错误:** ${data.error}\n`);
                } else if (data.output) {
                  // 检查是否是流式数据
                  if (data.streaming) {
                    // 流式数据：实时更新对应agent的内容
                    setAnalysisResult((prev) => {
                      const agentName = data.agent?.toUpperCase() || 'UNKNOWN';
                      const agentHeader = `\n## ${agentName}\n\n`;

                      // 查找是否已经有这个agent的内容
                      const agentHeaderIndex = prev.indexOf(agentHeader);

                      if (agentHeaderIndex !== -1) {
                        // 找到下一个agent的开始位置或文本结尾
                        const nextAgentIndex = prev.indexOf('\n## ', agentHeaderIndex + agentHeader.length);
                        const endIndex = nextAgentIndex !== -1 ? nextAgentIndex : prev.length;

                        // 替换这个agent的内容
                        return prev.substring(0, agentHeaderIndex) +
                               agentHeader + data.output + '\n\n' +
                               prev.substring(endIndex);
                      } else {
                        // 第一次添加这个agent的内容
                        return prev + agentHeader + data.output + '\n\n';
                      }
                    });
                  } else {
                    // 非流式数据：一次性添加完整内容
                    const formattedOutput = `\n## ${data.agent?.toUpperCase() || 'UNKNOWN'}\n\n${data.output}\n\n`;
                    setAnalysisResult((prev) => prev + formattedOutput);
                  }
                }
              }
            } catch (error) {
              console.error('解析消息失败:', error, 'Raw data:', line);
            }
          }
        }
      }
    } catch (error) {
      console.error('启动分析失败:', error);
      setIsAnalyzing(false);
      setAnalysisResult('分析启动失败，请检查网络连接或稍后重试。');
    }
  };

  const handleStopAnalysis = (e: React.MouseEvent) => {
    e.preventDefault(); // 防止表单提交或页面跳转

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsAnalyzing(false);
  };

  return (
    <Card className="w-full border-0 shadow-lg bg-gradient-to-br from-white to-gray-50/50">
      <CardHeader className="pb-6">
        <CardTitle className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl shadow-lg">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="text-xl font-semibold bg-gradient-to-r from-gray-900 to-gray-700 bg-clip-text text-transparent">
              AI 智能分析
            </span>
            {selectedStock && (
              <span className="text-sm font-medium text-gray-500 flex items-center gap-1">
                <TrendingUp className="h-3 w-3" />
                {selectedStock} {stockName}
              </span>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 控制面板 - 日期范围和分析按钮在同一行 */}
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">
              分析时间范围
            </label>
            <DateRangePicker
              date={dateRange}
              onDateChange={setDateRange}
              placeholder="选择日期范围（可选）"
              className=""
            />
          </div>

          <div className="flex gap-3 w-full sm:w-auto">
            <Button
              type="button"
              onClick={handleStartAnalysis}
              disabled={isAnalyzing || !selectedStock}
              className="flex-1 sm:flex-none bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white border-0 shadow-lg hover:shadow-xl transition-all duration-200 px-6 py-2.5 rounded-xl font-medium"
            >
              <Play className="h-4 w-4 mr-2" />
              {isAnalyzing ? '分析中...' : '开始分析'}
            </Button>
            {isAnalyzing && (
              <Button
                type="button"
                onClick={handleStopAnalysis}
                variant="outline"
                className="border-gray-300 hover:bg-gray-50 text-gray-700 rounded-xl px-4 py-2.5 transition-all duration-200"
              >
                <Square className="h-4 w-4 mr-2" />
                停止
              </Button>
            )}
          </div>
        </div>

        {/* 分析结果显示 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <label className="text-sm font-semibold text-gray-800">分析结果</label>
            {isAnalyzing && (
              <div className="flex items-center gap-2 text-xs text-blue-600">
                <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
                实时更新中
              </div>
            )}
          </div>

          <div className="min-h-[300px] max-h-[500px] overflow-y-auto rounded-2xl border border-gray-200/60 bg-white/80 backdrop-blur-sm shadow-inner">
            {analysisResult ? (
              <div className="p-6">
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      // Apple风格的自定义样式
                      h1: ({children}) => (
                        <h1 className="text-xl font-bold mb-4 text-gray-900 border-b border-gray-200 pb-2">
                          {children}
                        </h1>
                      ),
                      h2: ({children}) => (
                        <h2 className="text-lg font-semibold mb-3 text-gray-800 mt-6 first:mt-0">
                          {children}
                        </h2>
                      ),
                      h3: ({children}) => (
                        <h3 className="text-base font-medium mb-2 text-gray-700 mt-4">
                          {children}
                        </h3>
                      ),
                      p: ({children}) => (
                        <p className="mb-3 text-sm leading-relaxed text-gray-700">
                          {children}
                        </p>
                      ),
                      ul: ({children}) => (
                        <ul className="list-none mb-4 space-y-1 text-sm">
                          {children}
                        </ul>
                      ),
                      ol: ({children}) => (
                        <ol className="list-decimal list-inside mb-4 space-y-1 text-sm">
                          {children}
                        </ol>
                      ),
                      li: ({children}) => (
                        <li className="text-gray-700 flex items-start gap-2">
                          <span className="w-1.5 h-1.5 bg-blue-500 rounded-full mt-2 flex-shrink-0"></span>
                          <span>{children}</span>
                        </li>
                      ),
                      strong: ({children}) => (
                        <strong className="font-semibold text-gray-900">
                          {children}
                        </strong>
                      ),
                      em: ({children}) => (
                        <em className="italic text-blue-700 font-medium">
                          {children}
                        </em>
                      ),
                      code: ({children}) => (
                        <code className="bg-gray-100 text-blue-800 px-2 py-1 rounded-md text-xs font-mono">
                          {children}
                        </code>
                      ),
                      pre: ({children}) => (
                        <pre className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-xs overflow-x-auto mb-4 font-mono">
                          {children}
                        </pre>
                      ),
                    }}
                  >
                    {analysisResult}
                  </ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full min-h-[200px]">
                <div className="text-center space-y-3">
                  <div className="w-16 h-16 mx-auto bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl flex items-center justify-center">
                    <Sparkles className="h-8 w-8 text-gray-400" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-gray-600 font-medium">
                      {isAnalyzing ? '正在分析中...' : '准备开始AI分析'}
                    </p>
                    <p className="text-xs text-gray-500">
                      {isAnalyzing
                        ? '分析结果将实时显示在这里'
                        : '选择股票并点击"开始分析"按钮'
                      }
                    </p>
                  </div>
                  {isAnalyzing && (
                    <div className="flex justify-center">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {isAnalyzing && (
          <div className="flex items-center gap-2 text-xs text-gray-500 bg-blue-50 px-4 py-3 rounded-xl border border-blue-100">
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse"></div>
            分析过程中会实时显示结果，请耐心等待分析完成
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default AIAnalysis;
