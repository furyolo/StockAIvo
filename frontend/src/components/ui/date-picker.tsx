"use client"

import { format } from "date-fns"
import { Calendar as CalendarIcon, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"
import { Calendar } from "./calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./popover"

interface DatePickerProps {
  className?: string
  date?: Date
  onDateChange?: (date: Date | undefined) => void
  placeholder?: string
}

export function DatePicker({
  className,
  date,
  onDateChange,
  placeholder = "选择结束日期"
}: DatePickerProps) {
  return (
    <div className={cn("grid gap-2", className)}>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            id="date"
            variant="outline"
            className={cn(
              "justify-between text-left font-normal min-w-[200px] w-auto",
              !date && "text-muted-foreground"
            )}
          >
            <div className="flex items-center">
              <CalendarIcon className="mr-2 h-4 w-4" />
              {date ? (
                format(date, "yyyy-MM-dd")
              ) : (
                <span>{placeholder}</span>
              )}
            </div>
            {date && (
              <X
                className="h-4 w-4 opacity-50 hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  onDateChange?.(undefined)
                }}
              />
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 bg-white border shadow-lg" align="start">
          <Calendar
            mode="single"
            defaultMonth={date}
            selected={date ? { from: date, to: date } : undefined}
            onSelect={(range) => {
              // 处理单日期选择
              if (range?.from) {
                onDateChange?.(range.from)
              } else {
                onDateChange?.(undefined)
              }
            }}
            className="rounded-md bg-white"
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
