import { useState } from "react";
import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface DateRangePickerProps {
  className?: string;
}

const DateRangePicker = ({ className }: DateRangePickerProps) => {
  const [from, setFrom] = useState<Date | undefined>();
  const [to, setTo] = useState<Date | undefined>();
  const [open, setOpen] = useState(false);

  const label =
    from && to
      ? `${format(from, "MMM d")} – ${format(to, "MMM d, yyyy")}`
      : from
      ? `${format(from, "MMM d, yyyy")} – …`
      : "Pick dates";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-[13px] font-medium transition-all duration-300",
            "border border-border/60 bg-muted/35 backdrop-blur-xl",
            "text-muted-foreground hover:text-foreground",
            from && "text-foreground",
            className
          )}
        >
          <CalendarIcon className="w-3.5 h-3.5" />
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <div className="flex flex-col sm:flex-row gap-0 sm:gap-2 p-1">
          <div>
            <p className="text-[11px] text-muted-foreground px-3 pt-2 font-medium uppercase tracking-wider">From</p>
            <Calendar
              mode="single"
              selected={from}
              onSelect={setFrom}
              className={cn("p-3 pointer-events-auto")}
            />
          </div>
          <div>
            <p className="text-[11px] text-muted-foreground px-3 pt-2 font-medium uppercase tracking-wider">To</p>
            <Calendar
              mode="single"
              selected={to}
              onSelect={(d) => {
                setTo(d);
                if (d && from) setOpen(false);
              }}
              disabled={(date) => (from ? date < from : false)}
              className={cn("p-3 pointer-events-auto")}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default DateRangePicker;
