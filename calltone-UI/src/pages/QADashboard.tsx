import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import AnimatedNumber from "@/components/AnimatedNumber";
import { motion, AnimatePresence } from "framer-motion";
import { Users, BarChart3, AlertTriangle, Clock, X, Phone, Search, ChevronDown, ChevronRight } from "lucide-react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import SplitText from "@/components/SplitText";
import BubbleToggle from "@/components/BubbleToggle";
import DateRangePicker from "@/components/DateRangePicker";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { qaApi } from "@/services/api";
import type { Call, Agent } from "@/data/mockData";
import { cn } from "@/lib/utils";

const timeRanges = ["Weekly", "Monthly", "Quarterly", "Yearly", "Custom"];

const QADashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [selectedRange, setSelectedRange] = useState("Monthly");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"time" | "rating">("time");
  const [agentSearch, setAgentSearch] = useState("");
  const [agentSort, setAgentSort] = useState<"score-desc" | "score-asc" | "name" | "calls">("score-desc");
  const [showAll, setShowAll] = useState(false);
  const AGENTS_LIMIT = 6;

  const { data: summaryData } = useQuery({
    queryKey: ["qa-summary", selectedRange],
    queryFn: () => qaApi.getSummary(selectedRange).then(r => r.data),
  });

  const { data: agentsData } = useQuery({
    queryKey: ["qa-agents", selectedRange],
    queryFn: () => qaApi.getAgents(selectedRange).then(r => r.data),
  });

  const { data: selectedAgentCalls = [] } = useQuery({
    queryKey: ["qa-agent-calls", selectedAgent, selectedRange, sortBy],
    queryFn: () => qaApi.getAgentCalls(selectedAgent!, { range: selectedRange, sortBy }).then(r => r.data),
    enabled: !!selectedAgent,
  });

  const agents: Agent[] = agentsData ?? [];
  const totalCalls = summaryData?.totalCalls ?? 0;
  const avgScore = summaryData?.avgScore ?? 0;
  const flaggedCalls = summaryData?.flaggedCalls ?? 0;

  const selectedAgentData = agents.find(a => a.id === selectedAgent);

  const sortedCalls = useMemo(() => {
    const sorted = [...selectedAgentCalls];
    if (sortBy === "rating") sorted.sort((a, b) => b.overallScore - a.overallScore);
    return sorted;
  }, [selectedAgentCalls, sortBy]);

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole="qa" />

        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8 sm:space-y-12">
          {/* Greeting */}
          <header>
            <h1 className="text-3xl sm:text-4xl font-light text-foreground tracking-tight">
              <SplitText
                text={`${new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 17 ? "Good afternoon" : "Good evening"}, `}
                splitType="chars"
                delay={40}
                duration={0.8}
                from={{ opacity: 0, y: 30 }}
                to={{ opacity: 1, y: 0 }}
              >
                <span className="font-semibold gradient-text">
                  <SplitText
                    text={(user?.name ?? "").split(" ")[0]}
                    splitType="chars"
                    delay={40}
                    duration={0.8}
                    from={{ opacity: 0, y: 30 }}
                    to={{ opacity: 1, y: 0 }}
                  />
                </span>
              </SplitText>
            </h1>
            <motion.p
              className="text-muted-foreground mt-2 text-sm font-light"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.6 }}
            >
              {new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
            </motion.p>
          </header>

          {/* Summary Bar */}
          <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            {[
              { icon: Phone, value: totalCalls, label: "Total Calls Reviewed", glow: "primary" as const, iconColor: "text-accent" },
              { icon: BarChart3, value: avgScore, label: "Average Team Score", glow: "success" as const, iconColor: "text-success" },
              { icon: AlertTriangle, value: flaggedCalls, label: "Flagged Calls", glow: "warning" as const, iconColor: "text-warning" },
            ].map((item) => (
              <GlassCard key={item.label} glow={item.glow} className="p-5 sm:p-6">
                <div className="flex items-center gap-4">
                  <div className="p-2.5 rounded-xl bg-white/[0.04]">
                    <item.icon className={cn("w-5 h-5", item.iconColor)} />
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-foreground tracking-tight">
                      <AnimatedNumber value={item.value} duration={1400} />
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1 font-medium uppercase tracking-wider">{item.label}</p>
                  </div>
                </div>
              </GlassCard>
            ))}
          </section>

          {/* Time Range */}
          <div className="flex flex-wrap items-center gap-3">
            <BubbleToggle
              options={timeRanges}
              value={selectedRange}
              onChange={setSelectedRange}
            />
            {selectedRange === "Custom" && <DateRangePicker />}
          </div>
          

          {/* Agent Grid with Overlay Drill-Down */}
          <section className="relative">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                <Users className="w-4 h-4" />
                <SplitText
                  text="Agents Overview"
                  splitType="chars"
                  delay={30}
                  duration={0.6}
                  from={{ opacity: 0, y: 20 }}
                  to={{ opacity: 1, y: 0 }}
                />
              </h2>
              <div className="flex flex-col sm:flex-row gap-2">
                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/60" />
                  <input
                    type="text"
                    placeholder="Search agents..."
                    value={agentSearch}
                    onChange={(e) => setAgentSearch(e.target.value)}
                    className="h-9 pl-9 pr-3 rounded-xl glass-input text-xs sm:text-[13px] w-full sm:w-48"
                    aria-label="Search agents"
                  />
                </div>
                {/* Sort */}
                <BubbleToggle
                  options={["Top", "Low", "A-Z", "Calls"]}
                  value={agentSort === "score-desc" ? "Top" : agentSort === "score-asc" ? "Low" : agentSort === "name" ? "A-Z" : "Calls"}
                  onChange={(v) => {
                    const map: Record<string, typeof agentSort> = { Top: "score-desc", Low: "score-asc", "A-Z": "name", Calls: "calls" };
                    setAgentSort(map[v]);
                  }}
                />
              </div>
            </div>

            <div className={cn("relative", selectedAgent && "min-h-[420px]")}>
              {/* Agent Cards */}
              {(() => {
                let filtered = agents.filter(a =>
                  a.name.toLowerCase().includes(agentSearch.toLowerCase())
                );
                if (agentSort === "score-desc") filtered.sort((a, b) => b.overallScore - a.overallScore);
                else if (agentSort === "score-asc") filtered.sort((a, b) => a.overallScore - b.overallScore);
                else if (agentSort === "name") filtered.sort((a, b) => a.name.localeCompare(b.name));
                else if (agentSort === "calls") filtered.sort((a, b) => b.callCount - a.callCount);

                const visible = showAll || agentSearch ? filtered : filtered.slice(0, AGENTS_LIMIT);
                const hasMore = !agentSearch && filtered.length > AGENTS_LIMIT;

                return (
                  <>
                    {filtered.length === 0 ? (
                      <div className="glass rounded-2xl py-16 text-center">
                        <p className="text-muted-foreground text-sm font-light">No agents found matching "{agentSearch}"</p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                        {visible.map((agent, i) => (
                          <GlassCard
                            key={agent.id}
                            hover
                            glow={agent.overallScore >= 90 ? "success" : agent.overallScore < 70 ? "destructive" : "none"}
                            className={cn("p-5 sm:p-6", selectedAgent === agent.id && "ring-1 ring-accent/30")}
                          >
                            <motion.div
                              initial={{ opacity: 0, y: 12 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: i * 0.06, ease: [0.25, 0.46, 0.45, 0.94] }}
                              onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
                              className="cursor-pointer"
                            >
                              <div className="flex items-center justify-between mb-4">
                                <h3 className="font-medium text-foreground text-sm">{agent.name}</h3>
                                <span className={cn(
                                  "text-2xl font-extralight",
                                  agent.overallScore >= 90 ? "text-success" : agent.overallScore >= 70 ? "text-accent" : "text-destructive"
                                )}>
                                  {agent.overallScore}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] text-muted-foreground font-medium">{agent.callCount} calls</span>
                                <div className="w-20 sm:w-24 h-8">
                                  <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={agent.trend.map((v, j) => ({ v, i: j }))}>
                                      <Line
                                        type="monotone"
                                        dataKey="v"
                                        stroke={agent.overallScore >= 90 ? "hsl(160 84% 39%)" : agent.overallScore >= 70 ? "hsl(187 92% 43%)" : "hsl(0 72% 56%)"}
                                        strokeWidth={1.5}
                                        dot={false}
                                      />
                                    </LineChart>
                                  </ResponsiveContainer>
                                </div>
                              </div>
                            </motion.div>
                          </GlassCard>
                        ))}
                      </div>
                    )}
                    {hasMore && !showAll && (
                      <motion.button
                        whileHover={{ y: -1 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => setShowAll(true)}
                        className="mt-6 mx-auto flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.04] transition-all duration-300"
                      >
                        Show all {filtered.length} agents <ChevronDown className="w-4 h-4" />
                      </motion.button>
                    )}
                    {showAll && hasMore && (
                      <motion.button
                        whileHover={{ y: -1 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => setShowAll(false)}
                        className="mt-6 mx-auto flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.04] transition-all duration-300"
                      >
                        Show less
                      </motion.button>
                    )}
                  </>
                );
              })()}

              {/* Calls Overlay */}
              <AnimatePresence mode="wait">
                {selectedAgent && selectedAgentData && (
                  <motion.div
                    key={selectedAgent}
                    initial={{ opacity: 0, y: 12, filter: "blur(6px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
                    transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                    className="absolute inset-0 z-10 rounded-2xl backdrop-blur-2xl bg-background/70 border border-white/[0.06] p-5 sm:p-8 overflow-auto custom-scrollbar shadow-2xl"
                  >
                    
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-3">
                        <h2 className="text-base font-medium text-foreground">
                          {selectedAgentData.name}'s Calls
                        </h2>
                        <div className="flex items-center gap-3">
                          <BubbleToggle
                            options={["By Time", "By Rating"]}
                            value={sortBy === "time" ? "By Time" : "By Rating"}
                            onChange={(v) => setSortBy(v === "By Time" ? "time" : "rating")}
                          />
                          <button onClick={() => setSelectedAgent(null)} className="p-1.5 rounded-lg hover:bg-white/[0.06] text-muted-foreground hover:text-foreground transition-all duration-300" aria-label="Close">
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      {sortedCalls.length === 0 ? (
                        <div className="py-12 text-center">
                          <p className="text-muted-foreground text-sm font-light">No calls found for this agent.</p>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {sortedCalls.map((call, i) => (
                            <motion.div
                              key={call.id}
                              initial={{ opacity: 0, x: -12 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: 0.15 + i * 0.05, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                              onClick={() => navigate(`/qa/call/${call.id}`)}
                              className={cn(
                                "rounded-xl p-4 flex items-center gap-4 cursor-pointer transition-all duration-300 hover:bg-white/[0.04] group",
                                call.overallScore < 50 && "bg-destructive/[0.03] border border-destructive/10",
                                call.status === "flagged" && call.overallScore >= 50 && "bg-warning/[0.03] border border-warning/10",
                                !call.overallScore || (call.overallScore >= 50 && call.status !== "flagged") ? "border border-transparent" : ""
                              )}
                            >
                              <div className="flex-shrink-0 w-12 text-center">
                                <span className={cn("text-2xl font-extralight", call.overallScore >= 80 ? "text-success" : call.overallScore >= 60 ? "text-warning" : "text-destructive")}>
                                  {call.overallScore}
                                </span>
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 flex-wrap">
                                  <span className="text-sm font-medium text-foreground">{call.date}</span>
                                  <span className="flex items-center gap-1 text-xs text-muted-foreground"><Clock className="w-3 h-3" />{call.duration}</span>
                                  <span className={cn(
                                    "text-[10px] px-2 py-0.5 rounded-full font-medium",
                                    call.status === "reviewed" && "bg-success/10 text-success",
                                    call.status === "pending" && "bg-warning/10 text-warning",
                                    call.status === "flagged" && "bg-destructive/10 text-destructive"
                                  )}>
                                    {call.status}
                                  </span>
                                </div>
                                <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                                  <span>Politeness {call.politeness}/5</span>
                                  <span>Empathy {call.empathy}/5</span>
                                </div>
                              </div>
                              <ChevronRight className="w-4 h-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors flex-shrink-0" />
                            </motion.div>
                          ))}
                        </div>
                      )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </section>
        </main>
      </div>
    </PageTransition>
  );
};

export default QADashboard;
