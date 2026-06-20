/**
 * SampleReport — PUBLIC, read-only sample QA report at /sample.
 *
 * SECURITY: self-contained. Imports NO api client, NO auth context, NO data hooks,
 * reads NO token/localStorage, makes NO network calls. All data is a static module
 * (sampleCall.ts) generated from ONE real processed call, so the audio, transcript,
 * and scores are all coherent. Separate public route from the protected /call/:callId.
 */
import { Link } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft, FileText, Shield, PlayCircle, Pause, Download,
  Gavel, CheckCircle2, Sparkles, AlertTriangle,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import PageTransition from "@/components/PageTransition";
import ScoreGauge from "@/components/ScoreGauge";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneIcon from "@/assets/calltone-icon.png";
import calltoneLogo from "@/assets/calltone-logo.png";
import { cn } from "@/lib/utils";
import { SAMPLE_CALL } from "@/data/sampleCall";

// --- local copies of the call-detail color helpers (kept in sync by hand) ---
const severityClass = (severity?: string | null) => {
  const s = (severity || "").toLowerCase();
  if (s === "minor") return "bg-success/10 text-success";
  if (s === "moderate") return "bg-warning/10 text-warning";
  if (s === "major") return "bg-orange-500/10 text-orange-500";
  if (s === "critical") return "bg-destructive/10 text-destructive";
  return "bg-muted/30 text-muted-foreground";
};
const scoreClass = (score: number) => {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-destructive";
};
const formatAudioTime = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
};

/** Exact same audio player UI as the authenticated call-detail view. */
const SampleAudioPlayer = ({ audioSrc }: { audioSrc: string }) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setDuration(0); setCurrentTime(0); setIsPlaying(false); setHasError(false);
  }, [audioSrc]);

  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;
  const seekToPointer = (clientX: number) => {
    const audio = audioRef.current; const track = progressRef.current;
    if (!audio || !track || !duration) return;
    const b = track.getBoundingClientRect();
    audio.currentTime = Math.min(1, Math.max(0, (clientX - b.left) / b.width)) * duration;
  };
  const togglePlayback = async () => {
    const audio = audioRef.current; if (!audio) return;
    if (audio.paused) { try { await audio.play(); } catch { setHasError(true); } } else { audio.pause(); }
  };

  return (
    <div className="rounded-2xl border border-border/70 bg-card/80 px-4 py-3 shadow-sm">
      <audio
        ref={audioRef}
        preload="metadata"
        src={audioSrc}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onError={() => setHasError(true)}
      />
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlayback}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground shadow-sm transition-transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          aria-label={isPlaying ? "Pause call audio" : "Play call audio"}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
        </button>
        <span className="w-[76px] shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatAudioTime(currentTime)} / {formatAudioTime(duration)}
        </span>
        <div
          ref={progressRef}
          className="relative h-2 flex-1 cursor-pointer rounded-full bg-muted"
          role="slider"
          aria-label="Call audio progress"
          aria-valuemin={0}
          aria-valuemax={Math.max(0, Math.floor(duration))}
          aria-valuenow={Math.floor(currentTime)}
          tabIndex={0}
          onClick={(e) => seekToPointer(e.clientX)}
          onKeyDown={(e) => {
            const audio = audioRef.current; if (!audio || !duration) return;
            if (e.key === "ArrowLeft") audio.currentTime = Math.max(0, audio.currentTime - 5);
            if (e.key === "ArrowRight") audio.currentTime = Math.min(duration, audio.currentTime + 5);
          }}
        >
          <div className="absolute left-0 top-0 h-full rounded-full bg-accent transition-[width]" style={{ width: `${progress}%` }} />
        </div>
        <a
          href={audioSrc}
          target="_blank"
          rel="noreferrer"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border bg-background/70 text-muted-foreground transition-colors hover:text-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          aria-label="Open call audio"
          title="Open audio"
        >
          <Download className="h-4 w-4" />
        </a>
      </div>
      {hasError && (
        <p className="mt-3 text-xs text-destructive">Audio could not be loaded. Refresh the page and try again.</p>
      )}
    </div>
  );
};

type SampleTab = "overview" | "transcript" | "scores" | "report" | "evidence";
const TABS: [SampleTab, string][] = [
  ["overview", "Overview"],
  ["transcript", "Transcript"],
  ["scores", "QA Scores"],
  ["report", "AI Report"],
  ["evidence", "Evidence"],
];

const SampleReport = () => {
  const [activeTab, setActiveTab] = useState<SampleTab>("overview");
  const c = SAMPLE_CALL;
  const r = c.report;
  const flagged = (r.severity || "").toLowerCase() === "major" || (r.severity || "").toLowerCase() === "critical";

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />

        <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/60 backdrop-blur-2xl">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-5 sm:px-8">
            <Link to="/" className="flex items-center gap-2">
              <img src={calltoneIcon} alt="CallTone" className="-my-8 h-28 w-28 md:hidden" />
              <img src={calltoneLogo} alt="CallTone" className="-my-12 hidden h-36 md:block" />
            </Link>
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link to="/login" className="rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2 text-[13px] font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:brightness-110">
                Sign In
              </Link>
            </div>
          </div>
        </nav>

        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-6 sm:space-y-8">
          <nav aria-label="Breadcrumb">
            <Link to="/" className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors duration-300">
              <ArrowLeft className="w-4 h-4" /> Back to Home
            </Link>
          </nav>

          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-4 sm:p-5 border-accent/20 bg-accent/[0.04] flex items-center gap-4">
            <div className="p-2 rounded-xl bg-accent/10"><Sparkles className="w-5 h-5 text-accent" /></div>
            <div>
              <p className="text-sm font-medium text-accent">Sample QA report</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                A read-only example from one real processed call — the audio, transcript, and scores all
                belong to this same call. Sign in to analyze your own.
              </p>
            </div>
          </motion.div>

          <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-light text-foreground tracking-tight">Sample Support Call</h1>
              <p className="text-muted-foreground text-sm font-light mt-1">
                {c.agentName} · {new Date(c.callTime).toLocaleString()} · {c.durationSeconds}s
              </p>
              <p className="text-[11px] text-muted-foreground/70 mt-1 font-mono">{c.filename}</p>
            </div>
            <ScoreGauge score={r.overallScore} grade={r.grade} size={200} />
          </header>

          {flagged && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-2xl p-4 sm:p-5 border-warning/20 bg-warning/[0.03] flex items-center gap-4">
              <div className="p-2 rounded-xl bg-warning/10"><AlertTriangle className="w-5 h-5 text-warning" /></div>
              <div>
                <p className="text-sm font-medium text-warning">Flagged for Review</p>
                <p className="text-xs text-muted-foreground mt-0.5 hidden sm:block">This call requires extra QA attention due to severity.</p>
              </div>
            </motion.div>
          )}

          <GlassCard className="p-5 sm:p-6">
            <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2"><Gavel className="w-4 h-4" /> Appeal</h2>
            <div className="flex items-center gap-3 mb-3 flex-wrap">
              <span className="text-[11px] font-semibold px-3 py-1 rounded-full bg-success/10 text-success">{c.appeal.status}</span>
              <span className="text-[11px] font-semibold px-3 py-1 rounded-full bg-accent/10 text-accent inline-flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Human-reviewed</span>
              <span className="text-[11px] text-muted-foreground">Submitted {new Date(c.appeal.submittedAt).toLocaleDateString()}</span>
            </div>
            <p className="text-sm text-foreground/75 mb-1.5"><span className="text-muted-foreground">Agent reason:</span> {c.appeal.agentReason}</p>
            <p className="text-sm text-foreground/75 mb-1.5"><span className="text-muted-foreground">Reviewer note:</span> {c.appeal.qaResponse}</p>
            <p className="text-sm text-foreground/75"><span className="text-muted-foreground">Human-adjusted score:</span> <span className="font-semibold">{c.appeal.correctedScore}</span> <span className="text-[11px] text-muted-foreground">(original AI score {r.overallScore} preserved)</span></p>
          </GlassCard>

          <div className="flex flex-wrap gap-1 border-b border-border/40">
            {TABS.map(([key, label]) => (
              <button key={key} type="button" onClick={() => setActiveTab(key)}
                className={cn("px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                  activeTab === key ? "border-accent text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                {label}
              </button>
            ))}
          </div>

          {activeTab === "overview" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="mb-4 text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-2"><PlayCircle className="w-4 h-4" /> Call Audio</h2>
              <SampleAudioPlayer audioSrc={c.audioSrc} />
              <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                {Object.entries(r.dimensionScores).map(([key, value]) => (
                  <div key={key} className="p-3 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">{key.replace(/_/g, " ")}</p>
                    <span className={cn("text-lg font-semibold", scoreClass(value))}>{value}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {activeTab === "transcript" && (
            <GlassCard className="p-5 sm:p-6 max-h-[700px] overflow-y-auto">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2"><FileText className="w-4 h-4" /> Transcript</h2>
              <div className="space-y-2.5">
                {c.transcript.map((line, i) => {
                  const isAgent = line.role.toLowerCase().includes("agent");
                  return (
                    <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 20) * 0.02, duration: 0.2 }}
                      className={cn("p-3 rounded-2xl border", isAgent ? "bg-accent/[0.06] border-accent/15" : "bg-primary/[0.04] border-primary/10")}>
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", isAgent ? "bg-accent/15 text-accent" : "bg-primary/15 text-primary")}>{line.role}</span>
                        <span className="text-[10px] text-muted-foreground">{line.start.toFixed(1)}s – {line.end.toFixed(1)}s</span>
                        {line.emotion && <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium bg-warning/10 text-warning">{line.emotion}</span>}
                        {line.signals.map((sig, si) => (
                          <span key={si} className={cn("text-[9px] px-1.5 py-0.5 rounded-full font-medium",
                            sig === "FRUSTRATED" || sig === "ESCALATION" ? "bg-destructive/10 text-destructive"
                              : sig === "APOLOGETIC" || sig === "SATISFIED" ? "bg-success/10 text-success"
                              : "bg-muted/30 text-muted-foreground")}>{sig}</span>
                        ))}
                      </div>
                      <p className="text-[13px] text-foreground/75 leading-relaxed">{line.text}</p>
                    </motion.div>
                  );
                })}
              </div>
            </GlassCard>
          )}

          {activeTab === "scores" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2"><Shield className="w-4 h-4" /> QA Scores</h2>
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-muted-foreground">Grade</span>
                <span className="text-lg font-semibold text-foreground">{r.grade}</span>
              </div>
              <div className="flex items-center justify-between mb-6">
                <span className="text-sm text-muted-foreground">Severity</span>
                <span className={cn("text-[11px] px-3 py-1.5 rounded-full font-semibold capitalize", severityClass(r.severity))}>{r.severity}</span>
              </div>
              <div className="space-y-3">
                {Object.entries(r.dimensionScores).map(([key, value]) => (
                  <div key={key} className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                        {key.replace(/_/g, " ")}
                        <span className="ml-2 normal-case text-muted-foreground/60">weight {Math.round((r.dimensionWeights[key] ?? 0) * 100)}%</span>
                      </p>
                      <span className={cn("text-sm font-semibold", scoreClass(value))}>{value}</span>
                    </div>
                    <p className="text-xs text-foreground/70 leading-relaxed">{r.dimensionReports[key] || "No report available."}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-4">Deterministic single-run scoring (temperature 0, fixed seed) — identical input reproduces identical scores.</p>
            </GlassCard>
          )}

          {activeTab === "report" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">AI Quality Report</h2>
              <div className="space-y-4 text-sm text-foreground/75">
                <div><p className="font-semibold text-foreground mb-1">Summary</p><p>{r.reportJson.summary}</p></div>
                <div><p className="font-semibold text-foreground mb-1">Strengths</p><ul className="list-disc pl-5 space-y-1">{r.reportJson.strengths.map((it, i) => <li key={i}>{it}</li>)}</ul></div>
                <div><p className="font-semibold text-foreground mb-1">Weaknesses</p><ul className="list-disc pl-5 space-y-1">{r.reportJson.weaknesses.map((it, i) => <li key={i}>{it}</li>)}</ul></div>
                <div><p className="font-semibold text-foreground mb-1">Recommended Actions</p><ul className="list-disc pl-5 space-y-1">{r.reportJson.recommended_actions.map((it, i) => <li key={i}>{it}</li>)}</ul></div>
              </div>
            </GlassCard>
          )}

          {activeTab === "evidence" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">Evidence</h2>
              <div className="space-y-3">
                {r.evidence.map((item, i) => (
                  <div key={i} className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1">{item.dimension.replace(/_/g, " ")}</p>
                    <p className="text-xs italic text-foreground/75 mb-1">"{item.quote}"</p>
                    <p className="text-[11px] text-muted-foreground">{item.speaker} · {item.reason}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <div className="pt-2 text-center">
            <Link to="/login" className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-primary to-accent px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-xl shadow-primary/25 transition-all hover:brightness-110">
              Analyze your own calls — Sign In <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </div>
        </main>
      </div>
    </PageTransition>
  );
};

export default SampleReport;
