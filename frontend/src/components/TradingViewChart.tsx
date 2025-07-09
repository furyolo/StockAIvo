import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries } from 'lightweight-charts';

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

interface TradingViewChartProps {
  data: ChartData[];
  height?: number;
  onOHLCChange?: (ohlc: ChartData | null) => void;
}

const TradingViewChart: React.FC<TradingViewChartProps> = ({ data, height = 400, onOHLCChange }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const candlestickSeriesRef = useRef<any>(null);

  // 状态管理当前显示的 OHLC 数据
  const [currentOHLC, setCurrentOHLC] = useState<ChartData | null>(
    data.length > 0 ? data[data.length - 1] : null
  );

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 创建图表
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#cccccc',
      },
      timeScale: {
        borderColor: '#cccccc',
        timeVisible: true,
        secondsVisible: false,
      },
      localization: {
        timeFormatter: (time: any) => {
          try {
            // TradingView 的时间可能是字符串格式 "2025-07-08" 或时间戳
            let date: Date;

            if (typeof time === 'string') {
              // 如果是字符串格式，直接解析
              date = new Date(time);
            } else if (typeof time === 'number') {
              // 如果是时间戳，需要判断是秒还是毫秒
              date = time > 1000000000000 ? new Date(time) : new Date(time * 1000);
            } else {
              // 其他情况，尝试直接转换
              date = new Date(time);
            }

            // 检查日期是否有效
            if (isNaN(date.getTime())) {
              return time.toString(); // 如果转换失败，返回原始值
            }

            // 中文星期名称映射
            const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
            const weekday = weekdays[date.getDay()];

            // 格式化为 "周二 2025-07-08"
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');

            return `${weekday} ${year}-${month}-${day}`;
          } catch (error) {
            console.error('Time formatting error:', error, 'time:', time);
            return time.toString(); // 出错时返回原始值
          }
        },
      },
    });

    // 创建K线系列
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    chartRef.current = chart;
    candlestickSeriesRef.current = candlestickSeries;

    // 添加鼠标悬停事件监听器
    chart.subscribeCrosshairMove((param: any) => {
      if (param.time) {
        const ohlcData = param.seriesData.get(candlestickSeries);
        if (ohlcData) {
          // 从原始数据中找到对应的数据项
          const timeStr = typeof param.time === 'string' ? param.time : param.time.toString();
          const originalDataItem = data.find(item =>
            item.time.split('T')[0] === timeStr
          );

          const newOHLC = {
            time: param.time,
            open: ohlcData.open,
            high: ohlcData.high,
            low: ohlcData.low,
            close: ohlcData.close,
            price_change: originalDataItem?.price_change,
            price_change_percent: originalDataItem?.price_change_percent,
          };
          setCurrentOHLC(newOHLC);
          onOHLCChange?.(newOHLC);
        }
      }
    });

    // 处理窗口大小变化
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
  }, [height]);

  useEffect(() => {
    if (!candlestickSeriesRef.current || !data.length) return;

    // 转换数据格式
    const chartData = data.map(item => ({
      time: item.time.split('T')[0], // 将 "2025-05-22T00:00:00" 转换为 "2025-05-22"
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));

    // 设置数据
    candlestickSeriesRef.current.setData(chartData);

    // 更新当前显示的 OHLC 为最新数据
    if (data.length > 0) {
      const latestData = data[data.length - 1];
      setCurrentOHLC(latestData);
      onOHLCChange?.(latestData);
    }

    // 自动调整视图
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  // 计算涨跌颜色
  const getPriceColor = (current: number, reference: number) => {
    if (current > reference) return 'text-green-600'; // 涨绿
    if (current < reference) return 'text-red-600'; // 跌红
    return 'text-gray-600'; // 平盘
  };

  return (
    <div className="w-full">
      {/* 图表容器 */}
      <div
        ref={chartContainerRef}
        className="w-full border rounded-lg"
        style={{ height: `${height}px` }}
      />
    </div>
  );
};

export default TradingViewChart;
