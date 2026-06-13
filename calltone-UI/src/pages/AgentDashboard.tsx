import { useState, useMemo } from "react";
import { useTheme } from "@/components/ThemeProvider";
import AnimatedNumber from "@/components/AnimatedNumber";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Clock, Shield, Heart, AlertTriangle, CheckCircle, ChevronRight } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import BubbleToggle from "@/components/BubbleToggle";
import PageTransition from "@/components/PageTransition";
import DateRangePicker from "@/components/DateRangePicker";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { agentApi } from "@/services/api";
import type { QaCallItem } from "@/services/api";
import { cn, cleanCallTitle } from "@/lib/utils";

const timeRanges = ["Per Call", "Weekly", "Monthly", "Quarterly", "Yearly", "Custom"];

const AgentDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [selectedRange, setSelectedRange] = useState("Weekly");
  const [sortBy, setSortBy] = useState<"time" | "rating">("time");

  const { data: dashData } = useQuery({
    queryKey: ["agent-dashboard", selectedRange],
    queryFn: () => agentApi.getDashboard(selectedRange).then(r => r.data),
  });

  const { data: callsData } = useQuery({
    queryKey: ["agent-calls", selectedRange],
    queryFn: () => agentApi.getCalls({ range: selectedRange }).then(r => r.data),
  });

  const agentCalls: QaCallItem[] = useMemo(() => callsData?.calls ?? [], [callsData?.calls]);
  const trendData = dashData?.trend ?? [];

  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  const sortedCalls = useMemo(() => {
    const sorted = [...agentCalls];
    if (sortBy === "rating") {
      sorted.sort((a, b) => (b.overallScore ?? 0) - (a.overallScore ?? 0));
    } else {
      sorted.sort((a, b) => {
        const da = a.callTime ? new Date(a.callTime).getTime() : 0;
        const db = b.callTime ? new Date(b.callTime).getTime() : 0;
        return db - da;
      });
    }
    return sorted;
  }, [agentCalls, sortBy]);

  const scores = dashData?.scores;
  const avgScore = scores?.overall ?? 0;

  const scoreCards = [
    { label: "Overall Score", value: avgScore, icon: Shield, glow: "primary" as const },
    { label: "Politeness", value: String(scores?.politeness ?? 0), icon: Heart, glow: "accent" as const },
    { label: "Empathy", value: String(scores?.empathy ?? 0), icon: Heart, glow: "accent" as const },
    { label: "Conflict Rate", value: `${scores?.conflictRate ?? 0}%`, icon: AlertTriangle, glow: "warning" as const },
    { label: "Resolution Rate", value: `${scores?.resolutionRate ?? 0}%`, icon: CheckCircle, glow: "success" as const },
  ];

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole="agent" />

        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8 sm:space-y-12">
          {/* Header */}
          <header>
            <h1 className="text-3xl sm:text-4xl font-light text-foreground tracking-tight">
              {greeting},{" "}
              <span className="font-semibold gradient-text">
                {(user?.name ?? "").split(" ")[0]}
              </span>
            </h1>
            <motion.p
              className="text-muted-foreground mt-2 text-sm font-light"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.6 }}
            >
              {today}
            </motion.p>
          </header>

          {/* Time Range Selector */}
          <div className="flex flex-wrap items-center gap-3">
            <BubbleToggle
              options={timeRanges}
              value={selectedRange}
              onChange={setSelectedRange}
            />
            {selectedRange === "Custom" && <DateRangePicker />}
          </div>

          {/* Score Cards */}
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
            {scoreCards.map((card, i) => (
              <GlassCard key={card.label} glow={card.glow} className="p-5 sm:p-6">
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: i * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
                >
                  <div className="flex items-center justify-between mb-4">
                    <card.icon className="w-4 h-4 text-muted-foreground/60" />
                  </div>
                  <p className="text-3xl sm:text-4xl font-extralight text-foreground tracking-tight">
                    {typeof card.value === "number" ? (
                      <AnimatedNumber value={card.value} duration={1400} />
                    ) : card.value.includes("%") ? (
                      <AnimatedNumber value={parseFloat(card.value)} duration={1400} suffix="%" />
                    ) : card.value.includes(".") ? (
                      <AnimatedNumber value={parseFloat(card.value)} duration={1400} decimals={1} />
                    ) : (
                      <AnimatedNumber value={parseFloat(card.value)} duration={1400} />
                    )}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-2 font-medium uppercase tracking-wider">{card.label}</p>
                </motion.div>
              </GlassCard>
            ))}
          </section>

          {/* Performance Chart */}
          <section>
            <GlassCard className="p-6 sm:p-8">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-6">Performance Trend</h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={11} fontWeight={300} tickLine={false} axisLine={false} />
                  <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} fontWeight={300} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "12px",
                      color: "hsl(var(--foreground))",
                      fontSize: "12px",
                      padding: "10px 14px",
                    }}
                  />
                  <Line type="monotone" dataKey="overall" stroke="hsl(187 92% 43%)" strokeWidth={2} dot={{ fill: "hsl(187 92% 43%)", r: 3, strokeWidth: 0 }} activeDot={{ r: 5, fill: "hsl(187 92% 43%)", strokeWidth: 0 }} />
                </LineChart>
              </ResponsiveContainer>
            </GlassCard>
          </section>

          {/* Calls List — Apple card-based style */}
          <section>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-5 gap-3">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Recent Calls</h2>
              <BubbleToggle
                options={["By Time", "By Rating"]}
                value={sortBy === "time" ? "By Time" : "By Rating"}
                onChange={(v) => setSortBy(v === "By Time" ? "time" : "rating")}
              />
            </div>
            <div className="space-y-2">
              {sortedCalls.map((call, i) => {
                const score = call.overallScore ?? 0;
                const sev = (call.severity ?? "").toLowerCase();
                return (
                  <motion.div
                    key={call.callId}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.04, ease: [0.25, 0.46, 0.45, 0.94] }}
                    whileHover={{ scale: 1.01, y: -2 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => navigate(`/qa/call/${call.callId}`)}
                    className={cn(
                      "glass rounded-2xl p-4 sm:p-5 flex items-center gap-4 cursor-pointer transition-colors duration-300 hover:bg-foreground/[0.04] group",
                      score < 50 && "border-destructive/20 bg-destructive/[0.03]"
                    )}
                  >
                    <div className="flex-shrink-0 w-12 sm:w-14 text-center">
                      <span className={cn(
                        "text-2xl sm:text-3xl font-extralight",
                        score >= 80 ? "text-success" : score >= 60 ? "text-warning" : "text-destructive"
                      )}>
                        {score}
                      </span>
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-sm font-medium text-foreground">{cleanCallTitle(call.filename)}</span>
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="w-3 h-3" />
                          {call.callTime ? new Date(call.callTime).toLocaleDateString() : "—"}
                        </span>
                        <span className={cn(
                          "text-[10px] px-2 py-0.5 rounded-full font-medium capitalize",
                          sev === "minor" && "bg-success/10 text-success",
                          sev === "moderate" && "bg-warning/10 text-warning",
                          (sev === "major" || sev === "critical") && "bg-destructive/10 text-destructive",
                          !sev && "bg-muted/30 text-muted-foreground"
                        )}>
                          {call.severity ?? call.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 mt-1.5 text-xs text-muted-foreground">
                        <span>{call.agentName}</span>
                        <span className="hidden sm:inline">{call.status}</span>
                      </div>
                    </div>

                    <ChevronRight className="w-4 h-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors flex-shrink-0" />
                  </motion.div>
                );
              })}
            </div>
          </section>
        </main>
      </div>
    </PageTransition>
  );
};

export default AgentDashboard;
