import React, { useState, useEffect, useRef, useCallback } from 'react';
import { TextInput, Paper, Stack, Group, Text, Loader, Center, rem } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';

interface SearchResult {
  symbol: string;
  name: string;
  cname?: string;
  relevance_score: number;
}

interface StockSearchProps {
  onSelectStock: (symbol: string, name: string) => void;
}

const StockSearch: React.FC<StockSearchProps> = ({ onSelectStock }) => {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [showingFullResults, setShowingFullResults] = useState(false);
  const [fullResults, setFullResults] = useState<SearchResult[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 防抖获取建议
  useEffect(() => {
    const timer = setTimeout(() => {
      if (query.trim().length >= 2) {
        getSuggestions(query.trim());
        setShowingFullResults(false); // 重置为建议模式
      } else {
        setSuggestions([]);
        setFullResults([]);
        setShowSuggestions(false);
        setSelectedIndex(-1);
        setShowingFullResults(false);
      }
    }, 200); // 减少延迟以提供更快的响应

    return () => clearTimeout(timer);
  }, [query]);

  // 点击外部关闭建议
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
        setSelectedIndex(-1);
        setShowingFullResults(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 获取搜索建议（自动完成）
  const getSuggestions = useCallback(async (searchQuery: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/search/stocks/suggestions?q=${encodeURIComponent(searchQuery)}&limit=5`
      );

      if (response.ok) {
        const data = await response.json();
        setSuggestions(data || []);
        setShowSuggestions(true);
        setSelectedIndex(-1);
      } else {
        console.error('获取建议失败:', response.statusText);
        setSuggestions([]);
      }
    } catch (error) {
      console.error('获取建议错误:', error);
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 获取完整搜索结果
  const getFullResults = useCallback(async (searchQuery: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/search/stocks?q=${encodeURIComponent(searchQuery)}&limit=20&offset=0`
      );

      if (response.ok) {
        const data = await response.json();
        setFullResults(data.results || []);
        setTotalCount(data.total_count || 0);
        setShowingFullResults(true);
        setSelectedIndex(-1);
      } else {
        console.error('获取搜索结果失败:', response.statusText);
        setFullResults([]);
      }
    } catch (error) {
      console.error('获取搜索结果错误:', error);
      setFullResults([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 处理键盘导航
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!showSuggestions) return;

    const currentResults = showingFullResults ? fullResults : suggestions;
    if (currentResults.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev =>
          prev < currentResults.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && selectedIndex < currentResults.length) {
          handleSelectStock(currentResults[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowSuggestions(false);
        setSelectedIndex(-1);
        setShowingFullResults(false);
        inputRef.current?.blur();
        break;
    }
  }, [showSuggestions, suggestions, fullResults, showingFullResults, selectedIndex]);

  const handleSelectStock = useCallback((result: SearchResult) => {
    setQuery(''); // 清空输入框，避免再次触发搜索
    setShowSuggestions(false);
    setSelectedIndex(-1);
    setShowingFullResults(false);
    onSelectStock(result.symbol, result.name);
  }, [onSelectStock]);

  const handleShowMoreResults = useCallback(() => {
    if (query.trim()) {
      getFullResults(query.trim());
    }
  }, [query, getFullResults]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setQuery(value);

    // 如果用户清空了输入，重置状态
    if (!value.trim()) {
      setSuggestions([]);
      setFullResults([]);
      setShowSuggestions(false);
      setSelectedIndex(-1);
      setShowingFullResults(false);
    }
  }, []);

  const handleInputFocus = useCallback(() => {
    if ((suggestions.length > 0 || fullResults.length > 0) && query.trim().length >= 2) {
      setShowSuggestions(true);
    }
  }, [suggestions.length, fullResults.length, query]);

  return (
    <div ref={searchRef} style={{ position: 'relative', width: '100%', maxWidth: '32rem' }}>
      <TextInput
        ref={inputRef}
        placeholder="搜索股票代码或公司名称..."
        value={query}
        onChange={handleInputChange}
        onFocus={handleInputFocus}
        onKeyDown={handleKeyDown}
        leftSection={<IconSearch size={16} color="#8a8a8a" />}
        size="md"
        styles={{
          input: {
            backgroundColor: '#ffffff',
            border: '1px solid #e1e4e8',
            borderRadius: '8px',
            fontSize: '15px',
            padding: '12px 16px 12px 40px',
            '&:focus': {
              borderColor: '#0066cc',
              boxShadow: '0 0 0 3px rgba(0, 102, 204, 0.1)',
            },
            '&::placeholder': {
              color: '#8a8a8a',
            }
          }
        }}
      />

      {showSuggestions && (
        <Paper
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: rem(4),
            maxHeight: rem(384),
            overflowY: 'auto',
            zIndex: 1000,
            backgroundColor: '#ffffff',
            border: '1px solid #e1e4e8',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
          }}
        >
          {isLoading ? (
            <Center p="md">
              <Stack gap="xs" align="center">
                <Loader size="sm" />
                <Text size="sm" c="dimmed">搜索中...</Text>
              </Stack>
            </Center>
          ) : showingFullResults ? (
            // 显示完整搜索结果
            <Stack gap={0}>
              <div style={{ padding: '12px 16px', backgroundColor: '#f6f8fa', borderBottom: '1px solid #e1e4e8' }}>
                <Text size="sm" c="#0066cc" fw={500}>
                  找到 {totalCount} 个结果，显示前 20 个
                </Text>
              </div>
              {fullResults.map((result, index) => (
                <div
                  key={result.symbol}
                  style={{
                    padding: '12px 16px',
                    cursor: 'pointer',
                    borderBottom: '1px solid #f0f0f0',
                    backgroundColor: index === selectedIndex 
                      ? '#f6f8fa' 
                      : 'transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                  onClick={() => handleSelectStock(result)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = '#f6f8fa';
                  }}
                  onMouseOut={(e) => {
                    if (index !== selectedIndex) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  <Group justify="space-between" align="flex-start">
                    <Stack gap="xs" style={{ flex: 1 }}>
                      <Text fw={600} size="sm" c="#1a1a1a">
                        {result.symbol}
                      </Text>
                      <Text size="xs" c="#8a8a8a">
                        {result.name}
                      </Text>
                      {result.cname && (
                        <Text size="xs" c="#8a8a8a">
                          {result.cname}
                        </Text>
                      )}
                    </Stack>
                    <Text size="xs" c="#0066cc" fw={500}>
                      {(result.relevance_score * 100).toFixed(0)}%
                    </Text>
                  </Group>
                </div>
              ))}
              {totalCount > 20 && (
                <Center p="sm" style={{ backgroundColor: 'var(--mantine-color-gray-0)' }}>
                  <Text size="xs" c="dimmed">
                    还有 {totalCount - 20} 个结果未显示
                  </Text>
                </Center>
              )}
            </Stack>
          ) : suggestions.length > 0 ? (
            // 显示搜索建议
            <Stack gap={0}>
              {suggestions.map((suggestion, index) => (
                <div
                  key={suggestion.symbol}
                  style={{
                    padding: '12px 16px',
                    cursor: 'pointer',
                    borderBottom: '1px solid #f0f0f0',
                    backgroundColor: index === selectedIndex 
                      ? '#f6f8fa' 
                      : 'transparent',
                    transition: 'background-color 0.15s ease',
                  }}
                  onClick={() => handleSelectStock(suggestion)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = '#f6f8fa';
                  }}
                  onMouseOut={(e) => {
                    if (index !== selectedIndex) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  <Group justify="space-between" align="flex-start">
                    <Stack gap="xs" style={{ flex: 1 }}>
                      <Text fw={600} size="sm" c="#1a1a1a">
                        {suggestion.symbol}
                      </Text>
                      <Text size="xs" c="#8a8a8a">
                        {suggestion.name}
                      </Text>
                      {suggestion.cname && (
                        <Text size="xs" c="#8a8a8a">
                          {suggestion.cname}
                        </Text>
                      )}
                    </Stack>
                    <Text size="xs" c="#0066cc" fw={500}>
                      {(suggestion.relevance_score * 100).toFixed(0)}%
                    </Text>
                  </Group>
                </div>
              ))}
              <div
                onClick={handleShowMoreResults}
                style={{
                  padding: '12px 16px',
                  borderTop: '1px solid #f0f0f0',
                  backgroundColor: '#fafbfc',
                  cursor: 'pointer',
                  textAlign: 'center',
                  transition: 'background-color 0.15s ease',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = '#f6f8fa';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = '#fafbfc';
                }}
              >
                <Text size="sm" c="#0066cc" fw={500}>
                  查看更多搜索结果
                </Text>
              </div>
            </Stack>
          ) : query.trim().length >= 2 ? (
            <Center p="md">
              <Stack gap="xs" align="center">
                <Text size="sm" c="dimmed">未找到相关股票</Text>
                <Text size="xs" c="dimmed">请尝试输入股票代码或公司名称</Text>
              </Stack>
            </Center>
          ) : null}
        </Paper>
      )}
    </div>
  );
};

export default StockSearch;
