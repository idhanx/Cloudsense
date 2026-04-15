import { cn } from '@/lib/utils';

const KPICard = ({ title, value, unit, icon: Icon, trend, status, className }) => {
  return (
    <div className={cn("bg-card rounded-lg p-6 border border-border", className)}>
      {/* Glow effect */}
      {status && (
        <div className={cn(
          "absolute inset-0 rounded-lg opacity-50 blur-sm",
          status === 'success' && "bg-green-500",
          status === 'warning' && "bg-yellow-500",
          status === 'critical' && "bg-red-500"
        )} />
      )}
      <div className="relative">
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm text-muted-foreground">{title}</span>
          {Icon && <Icon className="w-5 h-5 text-muted-foreground" />}
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold">{value}</span>
          {unit && <span className="text-muted-foreground">{unit}</span>}
        </div>
        {trend && (
          <div className={cn(
            "flex items-center gap-1 mt-2 text-sm",
            trend.direction === 'up' ? "text-green-500" : "text-red-500"
          )}>
            <span>{trend.direction === 'up' ? '↑' : '↓'}</span>
            <span>{Math.abs(trend.value)}%</span>
            <span className="text-muted-foreground">vs last period</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default KPICard;

