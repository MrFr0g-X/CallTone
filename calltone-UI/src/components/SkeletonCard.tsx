import { cn } from "@/lib/utils";

interface SkeletonCardProps {
  className?: string;
  lines?: number;
}

const SkeletonCard = ({ className, lines = 3 }: SkeletonCardProps) => (
  <div className={cn("glass rounded-2xl p-6 space-y-4 animate-pulse", className)}>
    <div className="h-4 w-1/3 rounded-lg bg-white/[0.06]" />
    {Array.from({ length: lines }).map((_, i) => (
      <div key={i} className="h-3 rounded-lg bg-white/[0.04]" style={{ width: `${70 - i * 15}%` }} />
    ))}
  </div>
);

export default SkeletonCard;
