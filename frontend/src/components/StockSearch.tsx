import React, { useState, useEffect, useRef } from 'react';
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
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // 防抖搜索
  useEffect(() => {
    const timer = setTimeout(() => {
      if (query.trim().length >= 1) {
        searchStocks(query.trim());
      } else {
        setResults([]);
        setShowResults(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // 点击外部关闭搜索结果
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const searchStocks = async (searchQuery: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/search/stocks?q=${encodeURIComponent(searchQuery)}&limit=10`
      );
      
      if (response.ok) {
        const data = await response.json();
        setResults(data.results || []);
        setShowResults(true);
      } else {
        console.error('搜索失败:', response.statusText);
        setResults([]);
      }
    } catch (error) {
      console.error('搜索错误:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectStock = (result: SearchResult) => {
    setQuery('');
    setShowResults(false);
    onSelectStock(result.symbol, result.name);
  };

  return (
    <div ref={searchRef} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-4 w-4" />
        <Input
          type="text"
          placeholder="搜索股票代码或公司名称..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) {
              setShowResults(true);
            }
          }}
          className="pl-10"
        />
      </div>

      {showResults && (
        <Card className="absolute top-full left-0 right-0 mt-1 max-h-80 overflow-y-auto z-50 bg-white shadow-lg">
          {isLoading ? (
            <div className="p-4 text-center text-gray-500">搜索中...</div>
          ) : results.length > 0 ? (
            <div className="py-2">
              {results.map((result) => (
                <div
                  key={result.symbol}
                  className="px-4 py-2 hover:bg-gray-100 cursor-pointer border-b last:border-b-0"
                  onClick={() => handleSelectStock(result)}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <div className="font-semibold text-sm">{result.symbol}</div>
                      <div className="text-xs text-gray-600">{result.name}</div>
                      {result.cname && (
                        <div className="text-xs text-gray-500">{result.cname}</div>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      {(result.relevance_score * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : query.trim().length >= 1 ? (
            <div className="p-4 text-center text-gray-500">未找到相关股票</div>
          ) : null}
        </Card>
      )}
    </div>
  );
};

export default StockSearch;
