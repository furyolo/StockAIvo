import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Paper, 
  Stack, 
  Group, 
  Text, 
  Button, 
  Grid,
  Center,
  Loader,
  Badge,
  Title,
  Alert,
  ScrollArea
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconPlayerPlay, IconSquare, IconSparkles, IconTrendingUp, IconBolt } from '@tabler/icons-react';
import { apiFetch } from '../lib/api';

interface AIAnalysisProps {
  selectedStock: string | null;
  stockName: string | null;
  onAnalysisStateChange?: (isAnalyzing: boolean) => void;
}

const AIAnalysis: React.FC<AIAnalysisProps> = ({ selectedStock, stockName, onAnalysisStateChange }) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState('');
  const [endDate, setEndDate] = useState<string | null>(null);
  const useParallelAnalysis = true; // 固定使用并行分析模式
  console.log('Using parallel analysis:', useParallelAnalysis); // 避免未使用变量警告
  const [parallelProgress, setParallelProgress] = useState<{[key: string]: boolean}>({}); // 跟踪并行任务进度
  const [availableAnalyses, setAvailableAnalyses] = useState<string[]>([]); // 跟踪可用的分析类型
  // 用于存储流式响应的取消函数
  const readerCancelRef = useRef<(() => void) | null>(null);

  // 通知父组件分析状态变化
  useEffect(() => {
    onAnalysisStateChange?.(isAnalyzing);
  }, [isAnalyzing, onAnalysisStateChange]);

  const handleStartAnalysis = async (e: React.MouseEvent) => {
    e.preventDefault(); // 防止表单提交或页面跳转

    if (!selectedStock) {
      alert('请先选择一只股票');
      return;
    }

    setIsAnalyzing(true);
    setAnalysisResult('');
    setParallelProgress({}); // 重置并行进度
    setAvailableAnalyses([]); // 重置可用分析列表

    try {
      // 准备请求数据 - 使用扁平JSON格式
      const requestData = {
        ticker: selectedStock,
        // 如果用户选择了结束日期，则使用用户选择的日期；否则不传日期，让后端使用默认值
        ...(endDate && {
          end_date: endDate,
        }),
      };

      // 固定使用并行分析
      const endpoint = 'analyze-parallel';

      // 发送 POST 请求并直接获取流式响应
      const response = await apiFetch(`/ai/${endpoint}`, {
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
      readerCancelRef.current = () => reader.cancel();

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          setIsAnalyzing(false);
          readerCancelRef.current = null;
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
                  // 更新并行进度跟踪
                  if (data.phase === 'parallel_analysis') {
                    setParallelProgress(prev => ({
                      ...prev,
                      [data.agent]: true
                    }));
                  }

                  // 检查是否是数据可用性信息
                  if (data.phase === 'data_collection' && data.available_analyses) {
                    setAvailableAnalyses(data.available_analyses);
                  }

                  // 检查是否是流式数据
                  if (data.streaming) {
                    // 流式数据：实时更新对应agent的内容
                    setAnalysisResult((prev) => {
                      const agentName = data.agent?.toUpperCase() || 'UNKNOWN';
                      // 为并行分析添加特殊标识
                      const parallelIndicator = data.phase === 'parallel_analysis' ? ' 🔄' : '';
                      const agentHeader = `\n## ${agentName}${parallelIndicator}\n\n`;

                      // 查找是否已经有这个agent的内容
                      const agentHeaderIndex = prev.indexOf(`\n## ${agentName}`);

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
                    const agentName = data.agent?.toUpperCase() || 'UNKNOWN';
                    const parallelIndicator = data.phase === 'parallel_analysis' ? ' ✅' : '';
                    const formattedOutput = `\n## ${agentName}${parallelIndicator}\n\n${data.output}\n\n`;
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

    if (readerCancelRef.current) {
      readerCancelRef.current();
      readerCancelRef.current = null;
    }
    setIsAnalyzing(false);
  };

  return (
    <Stack gap="xs">
      {/* AI分析控制面板 */}
      <Paper 
        p="lg" 
        style={{ 
          backgroundColor: '#ffffff',
          border: '1px solid #e1e4e8',
          borderRadius: '8px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <Group justify="space-between" align="center" wrap="wrap">
          {/* 左侧标题和股票信息 */}
          <Group gap="md" align="center">
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
              <IconSparkles size={18} color="white" />
            </div>
            <Group gap="sm" align="center">
              <Title order={3} c="#1a1a1a" style={{ fontWeight: 600 }}>
                AI 智能分析
              </Title>
              {selectedStock && (
                <Group gap="xs">
                  <IconTrendingUp size={12} color="#8a8a8a" />
                  <Text size="sm" c="#8a8a8a" fw={500}>
                    {selectedStock} {stockName}
                  </Text>
                </Group>
              )}
            </Group>
          </Group>

          {/* 右侧控制区域 */}
          <Group gap="md" align="center">
            <DateInput
              value={endDate}
              onChange={setEndDate}
              placeholder="选择结束日期（可选）"
              clearable
              size="sm"
              w={200}
              styles={{
                input: {
                  backgroundColor: '#ffffff',
                  border: '1px solid #e1e4e8',
                  borderRadius: '6px',
                  '&:focus': {
                    borderColor: '#0066cc',
                    boxShadow: '0 0 0 3px rgba(0, 102, 204, 0.1)',
                  }
                }
              }}
            />
            <Button
              onClick={handleStartAnalysis}
              disabled={isAnalyzing || !selectedStock}
              leftSection={<IconPlayerPlay size={16} />}
              size="sm"
              style={{
                backgroundColor: '#0066cc',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                fontWeight: 500,
                transition: 'all 0.15s ease',
              }}
              styles={{
                root: {
                  '&:hover': {
                    backgroundColor: '#0052a3',
                  },
                  '&:disabled': {
                    backgroundColor: '#f0f0f0',
                    color: '#8a8a8a',
                  }
                }
              }}
            >
              {isAnalyzing ? '分析中...' : '开始分析'}
            </Button>
            {isAnalyzing && (
              <Button
                onClick={handleStopAnalysis}
                variant="outline"
                leftSection={<IconSquare size={16} />}
                size="sm"
                styles={{
                  root: {
                    borderColor: '#e1e4e8',
                    color: '#1a1a1a',
                    borderRadius: '6px',
                    '&:hover': {
                      backgroundColor: '#f6f8fa',
                      borderColor: '#d0d7de',
                    }
                  }
                }}
              >
                停止
              </Button>
            )}
          </Group>
        </Group>

        {/* 并行分析进度指示器 */}
        {isAnalyzing && (
          <Alert
            icon={<IconBolt size={16} />}
            color="blue"
            variant="light"
            mt="sm"
          >
            {availableAnalyses.length > 0 ? (
              <Grid gutter="sm">
                {availableAnalyses.map((analysisType) => {
                  const agentMap = {
                    'technical_analysis': 'technical_analyst',
                    'fundamental_analysis': 'fundamental_analyst',
                    'news_sentiment': 'news_sentiment_analyst'
                  };
                  const agent = agentMap[analysisType as keyof typeof agentMap];
                  const isActive = parallelProgress[agent];
                  const agentNames = {
                    'technical_analysis': '技术分析',
                    'fundamental_analysis': '基本面分析',
                    'news_sentiment': '新闻情感分析'
                  };
                  
                  return (
                    <Grid.Col key={analysisType} span={{ base: 12, sm: availableAnalyses.length === 1 ? 12 : availableAnalyses.length === 2 ? 6 : 4 }}>
                      <Group
                        gap="xs"
                        p="sm"
                        style={{
                          borderRadius: '8px',
                          backgroundColor: isActive ? 'var(--mantine-color-green-0)' : 'var(--mantine-color-gray-0)',
                          border: `1px solid ${isActive ? 'var(--mantine-color-green-2)' : 'var(--mantine-color-gray-2)'}`,
                        }}
                      >
                        <div
                          style={{
                            width: '12px',
                            height: '12px',
                            borderRadius: '50%',
                            backgroundColor: isActive ? 'var(--mantine-color-green-5)' : 'var(--mantine-color-gray-4)',
                            animation: !isActive ? 'pulse 1.5s infinite' : 'none',
                          }}
                        />
                        <Text size="sm" fw={500} style={{ flex: 1 }}>
                          {agentNames[analysisType as keyof typeof agentNames]}
                        </Text>
                        {isActive && <Badge size="xs" color="green">✓</Badge>}
                      </Group>
                    </Grid.Col>
                  );
                })}
              </Grid>
            ) : (
              <Group gap="xs" p="sm" style={{ backgroundColor: 'var(--mantine-color-gray-0)', borderRadius: '8px' }}>
                <Loader size="xs" />
                <Text size="sm" fw={500}>
                  正在检查数据可用性...
                </Text>
              </Group>
            )}
          </Alert>
        )}
      </Paper>

      {/* 分析结果 - 独立的Paper组件 */}
      {(analysisResult || isAnalyzing) && (
        <Paper 
          p="lg" 
          style={{ 
            backgroundColor: 'transparent',
            border: 'none',
            borderRadius: '12px',
            boxShadow: 'none',
          }}
        >
          <Stack gap="sm">
            <ScrollArea.Autosize
              mah={500}
              style={{
                minHeight: analysisResult ? '150px' : '100px',
                border: '1px solid #e1e4e8',
                borderRadius: '8px',
                backgroundColor: '#ffffff',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
              }}
            >
              {analysisResult ? (
                <div style={{ padding: '30px', backgroundColor: '#ffffff' }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({children}) => (
                        <Title 
                          order={2} 
                          mb="md" 
                          mt="md" 
                          c="dark.9"
                          style={{ 
                            borderBottom: '1px solid var(--mantine-color-gray-3)',
                            paddingBottom: '8px',
                            fontWeight: 600,
                          }}
                        >
                          {children}
                        </Title>
                      ),
                      h2: ({children}) => (
                        <Title 
                          order={3} 
                          mb="md" 
                          mt="md" 
                          c="dark.8"
                          style={{ fontWeight: 600 }}
                        >
                          {children}
                        </Title>
                      ),
                      h3: ({children}) => (
                        <Title 
                          order={4} 
                          mb="xs" 
                          mt="xs" 
                          c="dark.7"
                          style={{ fontWeight: 600 }}
                        >
                          {children}
                        </Title>
                      ),
                      p: ({children}) => (
                        <Text 
                          mb="sm" 
                          size="md" 
                          lh={1.6} 
                          c="dark.7"
                        >
                          {children}
                        </Text>
                      ),
                      ul: ({children}) => (
                        <div style={{ marginBottom: '8px', fontSize: '16px' }}>
                          {children}
                        </div>
                      ),
                      ol: ({children}) => (
                        <div style={{ marginBottom: '8px', fontSize: '16px', paddingLeft: '20px' }}>
                          {children}
                        </div>
                      ),
                      li: ({children}) => (
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '2px' }}>
                          <div
                            style={{
                              width: '6px',
                              height: '6px',
                              borderRadius: '50%',
                              backgroundColor: 'var(--mantine-color-blue-6)',
                              marginTop: '8px',
                              flexShrink: 0,
                            }}
                          />
                          <Text c="dark.7" size="sm">{children}</Text>
                        </div>
                      ),
                      strong: ({children}) => (
                        <Text component="strong" fw={600} c="dark.8" inherit>
                          {children}
                        </Text>
                      ),
                      em: ({children}) => (
                        <Text component="em" fs="italic" c="blue.7" fw={500} inherit>
                          {children}
                        </Text>
                      ),
                      code: ({children}) => (
                        <code
                          style={{
                            backgroundColor: '#f1f3f4',
                            color: '#1a73e8',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '13px',
                            fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", "Cascadia Code", "Roboto Mono", Consolas, "Liberation Mono", Menlo, monospace',
                          }}
                        >
                          {children}
                        </code>
                      ),
                      pre: ({children}) => (
                        <pre
                          style={{
                            backgroundColor: '#f6f8fa',
                            border: '1px solid #e1e4e8',
                            padding: '16px',
                            borderRadius: '8px',
                            fontSize: '13px',
                            lineHeight: '1.5',
                            overflowX: 'auto',
                            marginBottom: '16px',
                            fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", "Cascadia Code", "Roboto Mono", Consolas, "Liberation Mono", Menlo, monospace',
                            color: '#24292f',
                          }}
                        >
                          {children}
                        </pre>
                      ),
                    }}
                  >
                    {analysisResult}
                  </ReactMarkdown>
                </div>
              ) : !isAnalyzing ? (
                <Center h="100%" mih={100}>
                  <Stack align="center" gap="md">
                    <div
                      style={{
                        width: '48px',
                        height: '48px',
                        background: 'linear-gradient(to bottom right, var(--mantine-color-gray-1), var(--mantine-color-gray-2))',
                        borderRadius: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <IconSparkles size={24} color="var(--mantine-color-gray-4)" />
                    </div>
                    <Stack align="center" gap="xs">
                      <Text fw={500} c="gray.6" size="sm">
                        点击开始分析按钮
                      </Text>
                    </Stack>
                  </Stack>
                </Center>
              ) : null
              }
            </ScrollArea.Autosize>
          </Stack>
        </Paper>
      )}
    </Stack>
  );
};

export default AIAnalysis;
