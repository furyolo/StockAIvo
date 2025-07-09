import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Search } from 'lucide-react';
import { Input } from './ui/input';
import { Card } from './ui/card';

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
    <div ref={searchRef} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-4 w-4" />
        <Input
          ref={inputRef}
          type="text"
          placeholder="搜索股票代码或公司名称..."
          value={query}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          className="pl-10"
          autoComplete="off"
        />
      </div>

      {showSuggestions && (
        <Card className="absolute top-full left-0 right-0 mt-1 max-h-96 overflow-y-auto z-50 bg-white shadow-lg border">
          {isLoading ? (
            <div className="p-4 text-center text-gray-500">
              <div className="flex items-center justify-center space-x-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                <span>搜索中...</span>
              </div>
            </div>
          ) : showingFullResults ? (
            // 显示完整搜索结果
            <div className="py-1">
              <div className="px-4 py-2 bg-blue-50 border-b text-sm text-blue-800">
                找到 {totalCount} 个结果，显示前 20 个
              </div>
              {fullResults.map((result, index) => (
                <div
                  key={result.symbol}
                  className={`px-4 py-3 cursor-pointer border-b last:border-b-0 transition-colors ${
                    index === selectedIndex
                      ? 'bg-blue-50 border-blue-200'
                      : 'hover:bg-gray-50'
                  }`}
                  onClick={() => handleSelectStock(result)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <div className="flex justify-between items-center">
                    <div className="flex-1">
                      <div className="font-semibold text-sm text-gray-900">
                        {result.symbol}
                      </div>
                      <div className="text-xs text-gray-600 mt-0.5">
                        {result.name}
                      </div>
                      {result.cname && (
                        <div className="text-xs text-gray-500 mt-0.5">
                          {result.cname}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-gray-400 ml-2">
                      匹配度 {(result.relevance_score * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              ))}
              {totalCount > 20 && (
                <div className="px-4 py-2 bg-gray-50 border-t text-xs text-gray-500 text-center">
                  还有 {totalCount - 20} 个结果未显示
                </div>
              )}
            </div>
          ) : suggestions.length > 0 ? (
            // 显示搜索建议
            <div className="py-1">
              {suggestions.map((suggestion, index) => (
                <div
                  key={suggestion.symbol}
                  className={`px-4 py-3 cursor-pointer border-b last:border-b-0 transition-colors ${
                    index === selectedIndex
                      ? 'bg-blue-50 border-blue-200'
                      : 'hover:bg-gray-50'
                  }`}
                  onClick={() => handleSelectStock(suggestion)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <div className="flex justify-between items-center">
                    <div className="flex-1">
                      <div className="font-semibold text-sm text-gray-900">
                        {suggestion.symbol}
                      </div>
                      <div className="text-xs text-gray-600 mt-0.5">
                        {suggestion.name}
                      </div>
                      {suggestion.cname && (
                        <div className="text-xs text-gray-500 mt-0.5">
                          {suggestion.cname}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-gray-400 ml-2">
                      匹配度 {(suggestion.relevance_score * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              ))}
              <div className="border-t bg-gray-50">
                <button
                  onClick={handleShowMoreResults}
                  className="w-full px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 transition-colors"
                >
                  查看更多搜索结果
                </button>
              </div>
            </div>
          ) : query.trim().length >= 2 ? (
            <div className="p-4 text-center text-gray-500">
              <div className="text-sm">未找到相关股票</div>
              <div className="text-xs mt-1">请尝试输入股票代码或公司名称</div>
            </div>
          ) : null}
        </Card>
      )}
    </div>
  );
};

export default StockSearch;
