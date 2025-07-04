"use client"

import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"

interface DateRange {
  from: Date | undefined
  to: Date | undefined
}

interface CalendarProps {
  className?: string
  selected?: DateRange
  onSelect?: (range: DateRange | undefined) => void
  mode?: "single" | "range"
  defaultMonth?: Date
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
]

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]

function Calendar({
  className,
  selected,
  onSelect,
  mode = "range",
  defaultMonth = new Date(),
  ...props
}: CalendarProps) {
  const [currentMonth, setCurrentMonth] = React.useState(defaultMonth)

  const year = currentMonth.getFullYear()
  const month = currentMonth.getMonth()

  // 获取当月第一天和最后一天
  const firstDayOfMonth = new Date(year, month, 1)
  const lastDayOfMonth = new Date(year, month + 1, 0)
  
  // 获取当月第一天是星期几（0=Sunday）
  const firstDayWeekday = firstDayOfMonth.getDay()
  
  // 获取当月天数
  const daysInMonth = lastDayOfMonth.getDate()

  // 生成日历网格
  const calendarDays = []
  
  // 添加上个月的空白天数
  for (let i = 0; i < firstDayWeekday; i++) {
    calendarDays.push(null)
  }
  
  // 添加当月的天数
  for (let day = 1; day <= daysInMonth; day++) {
    calendarDays.push(new Date(year, month, day))
  }

  const navigateMonth = (direction: "prev" | "next") => {
    setCurrentMonth(prev => {
      const newMonth = new Date(prev)
      if (direction === "prev") {
        newMonth.setMonth(prev.getMonth() - 1)
      } else {
        newMonth.setMonth(prev.getMonth() + 1)
      }
      return newMonth
    })
  }

  const isDateDisabled = (date: Date) => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return date >= today
  }

  const handleDayClick = (date: Date) => {
    if (!onSelect || isDateDisabled(date)) return

    if (mode === "single") {
      // 如果点击的是已选中的日期，则撤销选择
      if (selected?.from && date.toDateString() === selected.from.toDateString()) {
        onSelect(undefined)
      } else {
        onSelect({ from: date, to: date })
      }
      return
    }

    // Range mode
    if (!selected?.from || (selected.from && selected.to)) {
      // 如果已有完整范围，检查是否点击了起始或结束日期来撤销
      if (selected?.from && selected?.to) {
        const isClickingStart = date.toDateString() === selected.from.toDateString()
        const isClickingEnd = date.toDateString() === selected.to.toDateString()

        if (isClickingStart || isClickingEnd) {
          // 撤销选择
          onSelect(undefined)
          return
        }
      }

      // Start new selection
      onSelect({ from: date, to: undefined })
    } else if (selected.from && !selected.to) {
      // 如果点击的是已选中的起始日期，撤销选择
      if (date.toDateString() === selected.from.toDateString()) {
        onSelect(undefined)
        return
      }

      // Complete the range
      if (date < selected.from) {
        onSelect({ from: date, to: selected.from })
      } else {
        onSelect({ from: selected.from, to: date })
      }
    }
  }

  const isDaySelected = (date: Date) => {
    if (!selected?.from) return false
    
    if (mode === "single") {
      return date.toDateString() === selected.from.toDateString()
    }

    // Range mode
    if (!selected.to) {
      return date.toDateString() === selected.from.toDateString()
    }

    return date >= selected.from && date <= selected.to
  }

  const isDayInRange = (date: Date) => {
    if (!selected?.from || !selected?.to) return false
    return date > selected.from && date < selected.to
  }

  const isDayRangeStart = (date: Date) => {
    return selected?.from && date.toDateString() === selected.from.toDateString()
  }

  const isDayRangeEnd = (date: Date) => {
    return selected?.to && date.toDateString() === selected.to.toDateString()
  }

  return (
    <div className={cn("p-4 bg-white rounded-lg border shadow-sm", className)} {...props}>
      {/* Header with month navigation */}
      <div className="flex items-center justify-between mb-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigateMonth("prev")}
          className="h-8 w-8 p-0"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        
        <h2 className="text-lg font-semibold">
          {MONTHS[month]} {year}
        </h2>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigateMonth("next")}
          className="h-8 w-8 p-0"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 mb-2">
        {WEEKDAYS.map((day) => (
          <div
            key={day}
            className="h-8 w-8 flex items-center justify-center text-sm font-medium text-gray-500"
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {calendarDays.map((date, index) => (
          <div key={index} className="h-8 w-8 flex items-center justify-center">
            {date ? (
              <button
                onClick={() => handleDayClick(date)}
                disabled={isDateDisabled(date)}
                className={cn(
                  "h-8 w-8 rounded-md text-sm font-normal transition-colors",
                  !isDateDisabled(date) && "hover:bg-gray-100",
                  isDateDisabled(date) && "text-gray-400 cursor-not-allowed",
                  !isDateDisabled(date) && isDayInRange(date) && "bg-gray-100",
                  !isDateDisabled(date) && isDaySelected(date) && !isDayRangeStart(date) && !isDayRangeEnd(date) && "!bg-gray-300 !text-gray-900 hover:!bg-gray-400 font-medium",
                  !isDateDisabled(date) && (isDayRangeStart(date) || isDayRangeEnd(date)) && "!bg-black !text-white hover:!bg-black font-medium",
                  isDayRangeStart(date) && "rounded-r-none",
                  isDayRangeEnd(date) && "rounded-l-none"
                )}
              >
                {date.getDate()}
              </button>
            ) : (
              <div className="h-8 w-8" />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

Calendar.displayName = "Calendar"

export { Calendar, type DateRange }