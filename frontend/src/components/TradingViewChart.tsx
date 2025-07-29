import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries } from 'lightweight-charts';

interface ChartData {
  time?: string;
  date?: string;
  minute_timestamp?: string;
  timestamp_10min?: string;
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
  period?: 'daily' | 'weekly' | '10min' | 'minute';
  onOHLCChange?: (ohlc: ChartData | null) => void;
}

const TradingViewChart: React.FC<TradingViewChartProps> = ({ data, height = 400, period = 'daily', onOHLCChange }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const candlestickSeriesRef = useRef<any>(null);

  // 状态管理当前显示的 OHLC 数据
  const [, setCurrentOHLC] = useState<ChartData | null>(
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
        timeVisible: period === 'minute' || period === '10min',
        secondsVisible: false,
        rightOffset: period === 'daily' || period === 'weekly' ? 0 : 12,
        barSpacing: period === 'minute' ? 6 : period === '10min' ? 8 : 12,
        fixLeftEdge: false,
        fixRightEdge: period === 'daily' || period === 'weekly',
        lockVisibleTimeRangeOnResize: false,
        rightBarStaysOnScroll: !(period === 'daily' || period === 'weekly'),
        borderVisible: true,
        visible: true,
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

            // 根据period类型格式化时间显示
            if (period === 'minute') {
              // 分钟线：只显示时间 "HH:mm"，使用UTC时间避免时区转换
              const hours = String(date.getUTCHours()).padStart(2, '0');
              const minutes = String(date.getUTCMinutes()).padStart(2, '0');
              return `${hours}:${minutes}`;
            } else if (period === '10min') {
              // 10分钟线：显示时间 "HH:mm"，使用UTC时间
              const hours = String(date.getUTCHours()).padStart(2, '0');
              const minutes = String(date.getUTCMinutes()).padStart(2, '0');
              return `${hours}:${minutes}`;
            } else {
              // 日线和周线：显示 "周二 2025-07-08"
              const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
              const weekday = weekdays[date.getDay()];
              const year = date.getFullYear();
              const month = String(date.getMonth() + 1).padStart(2, '0');
              const day = String(date.getDate()).padStart(2, '0');
              return `${weekday} ${year}-${month}-${day}`;
            }
          } catch (error) {
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

          let originalDataItem;
          if (period === 'minute') {
            // 分钟线：匹配minute_timestamp字段
            originalDataItem = data.find(item => {
              const itemTime = item.minute_timestamp || item.time;
              return itemTime === timeStr || itemTime?.split('T')[0] === timeStr.split('T')[0];
            });
          } else if (period === '10min') {
            // 10分钟线：匹配timestamp_10min字段
            originalDataItem = data.find(item => {
              const itemTime = item.timestamp_10min || item.time;
              return itemTime === timeStr || itemTime?.split('T')[0] === timeStr.split('T')[0];
            });
          } else {
            // 日线和周线：匹配date或time字段的日期部分
            originalDataItem = data.find(item => {
              const itemTime = item.date || item.time || '';
              const itemDatePart = itemTime.includes('T') ? itemTime.split('T')[0] : itemTime;
              return itemDatePart === timeStr;
            });
          }

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

    // 转换数据格式 - 根据TradingView要求使用正确格式
    const chartData = data.map(item => {
      let timeValue: string | number;

      if (period === 'minute') {
        // 分钟线：转换为Unix时间戳，避免时区转换
        const timestamp = item.minute_timestamp || item.time || '';
        if (timestamp) {
          // 直接解析时间字符串，不进行时区转换
          // 格式: "2025-07-25T15:00:00" -> 保持15:00不变
          const date = new Date(timestamp + 'Z'); // 添加Z表示UTC时间，避免本地时区转换
          timeValue = Math.floor(date.getTime() / 1000);
        } else {
          timeValue = '';
        }
      } else if (period === '10min') {
        // 10分钟线：转换为Unix时间戳，避免时区转换
        const timestamp = item.timestamp_10min || item.time || '';
        if (timestamp) {
          const date = new Date(timestamp + 'Z');
          timeValue = Math.floor(date.getTime() / 1000);
        } else {
          timeValue = '';
        }
      } else {
        // 日线和周线：使用日期字符串
        const dateField = item.date || item.time || '';
        timeValue = dateField.includes('T') ? dateField.split('T')[0] : dateField;
      }

      const result = {
        time: timeValue,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      };

      // 验证数据有效性
      if (!timeValue || timeValue === '') {
        return null;
      }

      return result;
    }).filter(item => item !== null); // 过滤掉无效的数据项

    // 设置数据 - 先清空避免格式冲突
    try {
      candlestickSeriesRef.current.setData([]);
      setTimeout(() => {
        if (candlestickSeriesRef.current) {
          candlestickSeriesRef.current.setData(chartData);
        }
      }, 10);
    } catch (error) {
      // 如果出错，尝试重新创建图表
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candlestickSeriesRef.current = null;
      }
    }

    // 更新当前显示的 OHLC 为最新数据
    if (data.length > 0) {
      const latestData = data[data.length - 1];
      setCurrentOHLC(latestData);
      onOHLCChange?.(latestData);
    }

    // 自动调整视图 - 延迟执行确保数据设置完成
    setTimeout(() => {
      if (chartRef.current && chartData.length > 0) {
        const timeScale = chartRef.current.timeScale();

        if (period === 'minute' || period === '10min') {
          // 分钟线和10分钟线：显示全部数据点
          if (chartData.length > 0) {
            const from = chartData[0].time;
            const to = chartData[chartData.length - 1].time;
            timeScale.setVisibleRange({ from, to });
          }
        } else {
          // 日线和周线：完全铺满，不留右侧空白
          if (chartData.length > 0) {
            const from = chartData[0].time;
            const to = chartData[chartData.length - 1].time;
            timeScale.setVisibleRange({ from, to });
          }
        }
      }
    }, 50);
  }, [data, period]);



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
