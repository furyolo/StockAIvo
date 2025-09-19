import React, { useState, useEffect, useCallback } from 'react';
import { Group, Title, Paper, Box } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconTrendingUp } from '@tabler/icons-react';
import StockSearch from './StockSearch';

interface DynamicNavbarProps {
  onSelectStock: (symbol: string, name: string) => void;
  onSearchDropdownStateChange?: (isOpen: boolean) => void;
  isAIAnalyzing?: boolean;
}

const DynamicNavbar: React.FC<DynamicNavbarProps> = ({ onSelectStock, onSearchDropdownStateChange, isAIAnalyzing = false }) => {
  const [isVisible, setIsVisible] = useState(true);
  const [scrollDirection, setScrollDirection] = useState<'up' | 'down' | 'none'>('none');
  const [lastScrollY, setLastScrollY] = useState(0);
  const [isHovering, setIsHovering] = useState(false);
  const [isSearchDropdownOpen, setIsSearchDropdownOpen] = useState(false);
  const [ignoreScrollEvents, setIgnoreScrollEvents] = useState(false);
  
  // 响应式断点检测
  const isMobile = useMediaQuery('(max-width: 768px)');
  const isTablet = useMediaQuery('(max-width: 1024px)');

  // 滚动检测钩子
  const handleScroll = useCallback(() => {
    // 如果正在忽略滚动事件，暂停滚动隐藏功能
    if (ignoreScrollEvents || isSearchDropdownOpen) {
      return;
    }

    const currentScrollY = window.scrollY;
    const scrollThreshold = 30; // 降低滚动阈值，提升响应性

    if (Math.abs(currentScrollY - lastScrollY) < scrollThreshold) {
      return;
    }

    if (currentScrollY > lastScrollY && currentScrollY > 80) {
      // 向下滚动且超过80px时隐藏
      setScrollDirection('down');
    } else if (currentScrollY < lastScrollY) {
      // 向上滚动时显示
      setScrollDirection('up');
    }

    setLastScrollY(currentScrollY);
  }, [lastScrollY, isSearchDropdownOpen, ignoreScrollEvents]);

  // 鼠标位置检测钩子 (移动端禁用)
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (isMobile) return; // 移动端禁用鼠标悬停检测
    
    const hoverThreshold = 80; // 顶部感应区域高度
    const mouseY = e.clientY;

    if (mouseY <= hoverThreshold) {
      setIsHovering(true);
    } else {
      setIsHovering(false);
    }
  }, [isMobile]);

  // 搜索下拉框状态处理
  const handleSearchDropdownStateChange = useCallback((isOpen: boolean) => {
    setIsSearchDropdownOpen(isOpen);
    onSearchDropdownStateChange?.(isOpen);
  }, [onSearchDropdownStateChange]);

  // AI分析状态变化处理
  useEffect(() => {
    if (isAIAnalyzing) {
      // AI分析开始时，可以设置一些状态
    } else {
      // AI分析结束时，暂时忽略滚动事件以避免内容高度变化导致的误触发
      setIgnoreScrollEvents(true);
      const timer = setTimeout(() => {
        setIgnoreScrollEvents(false);
      }, 1000); // 1秒后恢复滚动检测
      return () => clearTimeout(timer);
    }
  }, [isAIAnalyzing]);

  // 设置事件监听器
  useEffect(() => {
    const debouncedHandleScroll = debounce(handleScroll, 10);
    
    window.addEventListener('scroll', debouncedHandleScroll);
    window.addEventListener('mousemove', handleMouseMove);

    return () => {
      window.removeEventListener('scroll', debouncedHandleScroll);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, [handleScroll, handleMouseMove]);

  // 控制导航栏显示逻辑
  useEffect(() => {
    if (isSearchDropdownOpen) {
      // 搜索下拉框打开时保持导航栏可见
      setIsVisible(true);
    } else if (!isMobile && isHovering) {
      // 桌面端鼠标悬停优先级最高
      setIsVisible(true);
    } else if (scrollDirection === 'down') {
      // 向下滚动时隐藏
      setIsVisible(false);
    } else if (scrollDirection === 'up') {
      // 向上滚动时显示
      setIsVisible(true);
    }
  }, [scrollDirection, isHovering, isMobile, isSearchDropdownOpen]);

  return (
    <Paper
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        backgroundColor: '#ffffff',
        borderBottom: '1px solid #e1e4e8',
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        transform: isVisible ? 'translateY(0)' : 'translateY(-100%)',
        transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
      }}
      p={isMobile ? "sm" : "md"}
    >
      <Box style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <Group justify="space-between" align="center">
          {/* Logo 区域 */}
          <Group gap={isMobile ? "xs" : "sm"} style={{ flex: '0 0 auto' }}>
            <div
              style={{
                padding: isMobile ? '6px' : '8px',
                backgroundColor: '#0066cc',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <IconTrendingUp size={isMobile ? 20 : 24} color="white" />
            </div>
            <Title order={isMobile ? 4 : 3} c="#1a1a1a" style={{ fontWeight: 600 }}>
              StockAIvo
            </Title>
          </Group>

          {/* 搜索框区域 */}
          <Box style={{ 
            flex: '1 1 auto', 
            maxWidth: isMobile ? '200px' : isTablet ? '350px' : '500px', 
            margin: '0 auto' 
          }}>
            <StockSearch 
              onSelectStock={onSelectStock} 
              onDropdownStateChange={handleSearchDropdownStateChange}
            />
          </Box>

          {/* 右侧占位区域，保持布局平衡 (仅桌面端) */}
          {!isMobile && (
            <Box style={{ flex: '0 0 auto', width: '140px' }} />
          )}
        </Group>
      </Box>
    </Paper>
  );
};

// 防抖函数
function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  return function executedFunction(...args: Parameters<T>) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

export default DynamicNavbar;