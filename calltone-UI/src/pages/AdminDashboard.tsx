import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Building2,
  Users,
  Phone,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  ArrowUpRight,
  CheckCircle2,
} from "lucide-react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import AnimatedNumber from "@/components/AnimatedNumber";
import GlassCard from "@/components/GlassCard";
import BubbleToggle from "@/components/BubbleToggle";
import { adminApi } from "@/services/api";
import { cn } from "@/lib/utils";

const AdminDashboard = () => {
  const [chartView, setChartView] = useState("Revenue");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-dashboard"],
    queryFn: async () => {
      const response = await adminApi.getDashboard();
      return response.data;
    },
  });

  const chartData = useMemo(() => {
    if (!data) return [];
    return chartView === "Revenue" ? data.trends.revenue : data.trends.calls;
  }, [data, chartView]);

  const chartKey = chartView === "Revenue" ? "revenue" : "calls";

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <span className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-destructive text-sm">
        Failed to load admin dashboard data.
      </div>
    );
  }

  return (
    <div className="space-y-8 sm:space-y-12">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Platform <span className="font-bold gradient-text">Overview</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">CallTone Admin Dashboard</p>
      </header>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {
            icon: Building2,
            label: "ACTIVE CLIENTS",
            value: data.kpis.activeClients,
            suffix: data.kpis.trialClients > 0 ? ` (+${data.kpis.trialClients} trial)` : "",
            trend: "+12%",
            up: true,
          },
          {
            icon: Users,
            label: "TOTAL AGENTS",
            value: data.kpis.totalAgents,
            trend: "+8%",
            up: true,
          },
          {
            icon: Phone,
            label: "CALLS THIS MONTH",
            value: data.kpis.callsThisMonth,
            trend: "+9.2%",
            up: true,
          },
          {
            icon: DollarSign,
            label: "MONTHLY REVENUE",
            value: data.kpis.monthlyRevenue,
            prefix: "$",
            trend: "+15%",
            up: true,
          },
        ].map((kpi) => (
          <GlassCard key={kpi.label} className="rounded-2xl p-5 sm:p-6">
            <div className="flex items-start justify-between mb-3">
              <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center">
                <kpi.icon className="w-4 h-4 text-accent" />
              </div>
              <span
                className={cn(
                  "flex items-center gap-0.5 text-xs font-medium",
                  kpi.up ? "text-success" : "text-destructive"
                )}
              >
                {kpi.up ? (
                  <TrendingUp className="w-3 h-3" />
                ) : (
                  <TrendingDown className="w-3 h-3" />
                )}
                {kpi.trend}
              </span>
            </div>
            <p className="text-2xl sm:text-3xl font-bold">
              {kpi.prefix || ""}
              <AnimatedNumber value={kpi.value} />
            </p>
            <p className="text-[11px] text-muted-foreground uppercase tracking-wider mt-1">
              {kpi.label}
              {kpi.suffix || ""}
            </p>
          </GlassCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <GlassCard className="lg:col-span-3 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Platform Trends
            </h2>
            <BubbleToggle
              options={["Revenue", "Calls"]}
              value={chartView}
              onChange={setChartView}
            />
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="adminGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(187, 92%, 43%)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="hsl(187, 92%, 43%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 20%, 18%)" />
                <XAxis
                  dataKey="month"
                  tick={{ fill: "hsl(215, 16%, 54%)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: "hsl(215, 16%, 54%)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) =>
                    chartView === "Revenue" ? `$${(v / 1000).toFixed(0)}k` : `${(v / 1000).toFixed(0)}k`
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: "hsl(222, 40%, 11%)",
                    border: "1px solid hsl(222, 20%, 18%)",
                    borderRadius: "12px",
                    fontSize: "13px",
                  }}
                  labelStyle={{ color: "hsl(215, 16%, 54%)" }}
                  formatter={(value: number) => [
                    chartView === "Revenue" ? `$${value.toLocaleString()}` : value.toLocaleString(),
                    chartView,
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey={chartKey}
                  stroke="hsl(187, 92%, 43%)"
                  strokeWidth={2}
                  fill="url(#adminGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-2 rounded-2xl p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-6">
            Platform Health
          </h2>
          <div className="space-y-5">
            {[
              {
                label: "Avg. Quality Score",
                value: `${data.health.avgQualityScore}`,
                icon: Activity,
                color: "text-success",
              },
              {
                label: "Active Clients",
                value: `${data.health.activeClients}`,
                icon: Building2,
                color: "text-accent",
              },
              {
                label: "Trial Conversions",
                value: `${data.health.trialConversions}%`,
                icon: ArrowUpRight,
                color: "text-primary",
              },
              {
                label: "Churn Rate",
                value: `${data.health.churnRate}%`,
                icon: TrendingDown,
                color: "text-destructive",
              },
              {
                label: "Uptime",
                value: `${data.health.uptime}%`,
                icon: CheckCircle2,
                color: "text-success",
              },
            ].map((stat) => (
              <div key={stat.label} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <stat.icon className={cn("w-4 h-4", stat.color)} />
                  <span className="text-sm text-muted-foreground">{stat.label}</span>
                </div>
                <span className="text-sm font-semibold">{stat.value}</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  );
};

export default AdminDashboard;