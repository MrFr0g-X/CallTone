/**
 * SampleReport — PUBLIC, read-only sample QA report.
 *
 * SECURITY: this page is intentionally self-contained. It imports NO api client,
 * NO auth context, NO data hooks, and reads NO token/localStorage. Every value
 * below is a hardcoded illustrative constant, so there is no route parameter,
 * query, or network call an attacker could manipulate, and nothing real can leak
 * through it. It mirrors the look of the authenticated call-detail view using only
 * presentational components, on its own public route (/sample), separate from the
 * protected /call/:callId view.
 */
import { Link } from "react-router-dom";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  FileText,
  Shield,
  PlayCircle,
  Gavel,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import PageTransition from "@/components/PageTransition";
import ScoreGauge from "@/components/ScoreGauge";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneIcon from "@/assets/calltone-icon.png";
import calltoneLogo from "@/assets/calltone-logo.png";
import { cn } from "@/lib/utils";

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

// ---------------------------------------------------------------------------
// SAMPLE DATA — illustrative only. Mirrors the verified demo call (70/100, C).
// Not a real customer recording; no personal data.
// ---------------------------------------------------------------------------
const SAMPLE = {
  filename: "sample_support_call.wav",
  agentName: "Jordan Lee (sample agent)",
  callTime: "2026-05-18T10:24:00Z",
  durationSeconds: 506,
  report: {
    overallScore: 70,
    grade: "C",
    severity: "moderate",
    dimensionScores: {
      script_compliance: 75,
      factual_accuracy: 50,
      politeness_tone: 75,
      empathy: 75,
      conflict_detection: 75,
      issue_resolution: 100,
      overall_severity: 25,
    } as Record<string, number>,
    dimensionReports: {
      script_compliance:
        "Agent opened with the approved greeting and verified the account, but skipped the closing recap script before ending the call.",
      factual_accuracy:
        "Quoted the upgrade fee as $40 when company context lists $45; the rest of the policy information was correct.",
      politeness_tone:
        "Professional and respectful throughout; tone stayed calm even as the customer's frustration rose.",
      empathy:
        "Acknowledged the customer's frustration once, but moved to problem-solving before fully validating the feeling.",
      conflict_detection:
        "Recognized rising tension and de-escalated by slowing down and confirming next steps.",
      issue_resolution:
        "The billing dispute was fully resolved on the call with a confirmed adjustment and a reference number.",
      overall_severity:
        "A single factual slip on the fee; no compliance or conduct breach. Low overall severity.",
    } as Record<string, string>,
    confidenceScores: {
      script_compliance: 0.88,
      factual_accuracy: 0.62,
      politeness_tone: 0.91,
      empathy: 0.74,
      conflict_detection: 0.83,
      issue_resolution: 0.9,
      overall_severity: 0.86,
    } as Record<string, number>,
    reportJson: {
      summary:
        "A competent billing-support call. The agent verified the customer, stayed professional under pressure, and fully resolved the dispute. The main deduction is a factual error on the upgrade fee, and the closing recap was skipped.",
      strengths: [
        "Verified the account before discussing any account details.",
        "Maintained a calm, professional tone as the customer's frustration rose.",
        "Fully resolved the billing dispute and provided a reference number.",
      ],
      weaknesses: [
        "Stated the upgrade fee as $40; company context lists $45 (factual accuracy).",
        "Did not deliver the closing recap script before ending the call.",
        "Moved to problem-solving before fully acknowledging the customer's feelings.",
      ],
      recommended_actions: [
        "Re-check current pricing in the knowledge base before quoting fees.",
        "Use the approved closing recap on every call.",
        "Add one explicit empathy statement before pivoting to the fix.",
      ],
    },
    evidence: [
      {
        dimension: "factual_accuracy",
        quote: "The upgrade is a one-time forty dollar charge on your next bill.",
        speaker: "Agent",
        reason: "Fee quoted as $40; company context lists $45.",
      },
      {
        dimension: "issue_resolution",
        quote:
          "I've applied the credit now — you'll see it within one billing cycle, and your reference is 4821.",
        speaker: "Agent",
        reason: "Dispute resolved with a confirmed adjustment and reference number.",
      },
      {
        dimension: "politeness_tone",
        quote: "I completely understand, and I'm going to stay on with you until this is sorted.",
        speaker: "Agent",
        reason: "Reassuring, professional tone while the customer was upset.",
      },
      {
        dimension: "conflict_detection",
        quote: "Let's slow down for a second so I can make sure I get this exactly right for you.",
        speaker: "Agent",
        reason: "De-escalation as tension rose.",
      },
      {
        dimension: "script_compliance",
        quote: "Alright, you're all set — have a good one!",
        speaker: "Agent",
        reason: "Call ended without the approved closing recap.",
      },
    ],
  },
  transcript: [
    { role: "Agent", start: 0.0, end: 6.4, emotion: null as string | null, signals: [] as string[],
      text: "Thank you for calling MetroBoost support, my name is Jordan. Can I start with your account number?" },
    { role: "Customer", start: 6.4, end: 13.2, emotion: "anger", signals: ["FRUSTRATED"],
      text: "Yeah — it's 5-5-2-9. I've been charged twice this month and nobody can tell me why." },
    { role: "Agent", start: 13.2, end: 20.8, emotion: null, signals: ["APOLOGETIC"],
      text: "I'm sorry about that, and I completely understand. I'm going to stay on with you until this is sorted." },
    { role: "Customer", start: 20.8, end: 26.1, emotion: "sadness", signals: [],
      text: "Okay. I just don't want to keep paying for something I didn't agree to." },
    { role: "Agent", start: 26.1, end: 34.7, emotion: null, signals: [],
      text: "Let's slow down for a second so I can make sure I get this exactly right for you. I can see the duplicate charge here." },
    { role: "Agent", start: 34.7, end: 41.0, emotion: null, signals: [],
      text: "The upgrade is a one-time forty dollar charge on your next bill — but the second charge was an error on our side." },
    { role: "Customer", start: 41.0, end: 45.6, emotion: "neutral", signals: [],
      text: "Okay, that makes more sense. So can you remove it?" },
    { role: "Agent", start: 45.6, end: 54.2, emotion: null, signals: ["SATISFIED"],
      text: "I've applied the credit now — you'll see it within one billing cycle, and your reference is 4821." },
    { role: "Customer", start: 54.2, end: 58.0, emotion: "joy", signals: ["SATISFIED"],
      text: "Oh, perfect. Thank you, I really appreciate that." },
    { role: "Agent", start: 58.0, end: 61.5, emotion: null, signals: [],
      text: "Alright, you're all set — have a good one!" },
  ],
  appeal: {
    status: "Overturned",
    agentReason:
      "The fee I quoted matched the script card I was given at the time; the $45 update wasn't published to us yet.",
    qaResponse:
      "Confirmed the pricing card was updated mid-shift. Factual-accuracy deduction reduced; AI score preserved for the record.",
    correctedScore: 78,
    submittedAt: "2026-05-19",
  },
} as const;

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
  const r = SAMPLE.report;

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />

        {/* Public header — links only to home + login, never anything protected */}
        <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/60 backdrop-blur-2xl">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-5 sm:px-8">
            <Link to="/" className="flex items-center gap-2">
              <img src={calltoneIcon} alt="CallTone" className="-my-8 h-28 w-28 md:hidden" />
              <img src={calltoneLogo} alt="CallTone" className="-my-12 hidden h-36 md:block" />
            </Link>
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link
                to="/login"
                className="rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2 text-[13px] font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:brightness-110"
              >
                Sign In
              </Link>
            </div>
          </div>
        </nav>

        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-6 sm:space-y-8">
          <nav aria-label="Breadcrumb">
            <Link
              to="/"
              className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors duration-300"
            >
              <ArrowLeft className="w-4 h-4" /> Back to Home
            </Link>
          </nav>

          {/* Honest "this is a sample" banner */}
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-2xl p-4 sm:p-5 border-accent/20 bg-accent/[0.04] flex items-center gap-4"
          >
            <div className="p-2 rounded-xl bg-accent/10">
              <Sparkles className="w-5 h-5 text-accent" />
            </div>
            <div>
              <p className="text-sm font-medium text-accent">Sample QA report</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                A read-only example of CallTone's output — illustrative data, not a real customer call.
                Sign in to analyze your own calls.
              </p>
            </div>
          </motion.div>

          <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-light text-foreground tracking-tight">
                Sample Support Call
              </h1>
              <p className="text-muted-foreground text-sm font-light mt-1">
                {SAMPLE.agentName} · {new Date(SAMPLE.callTime).toLocaleString()} ·{" "}
                {SAMPLE.durationSeconds}s
              </p>
              <p className="text-[11px] text-muted-foreground/70 mt-1 font-mono">{SAMPLE.filename}</p>
            </div>

            <ScoreGauge score={r.overallScore} grade={r.grade} size={200} />
          </header>

          {/* Appeal panel — illustrative "overturned" record (reviewer view styling) */}
          <GlassCard className="p-5 sm:p-6">
            <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
              <Gavel className="w-4 h-4" /> Appeal
            </h2>
            <div className="flex items-center gap-3 mb-3 flex-wrap">
              <span className="text-[11px] font-semibold px-3 py-1 rounded-full bg-success/10 text-success">
                {SAMPLE.appeal.status}
              </span>
              <span className="text-[11px] font-semibold px-3 py-1 rounded-full bg-accent/10 text-accent inline-flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Human-reviewed
              </span>
              <span className="text-[11px] text-muted-foreground">
                Submitted {new Date(SAMPLE.appeal.submittedAt).toLocaleDateString()}
              </span>
            </div>
            <p className="text-sm text-foreground/75 mb-1.5">
              <span className="text-muted-foreground">Agent reason:</span> {SAMPLE.appeal.agentReason}
            </p>
            <p className="text-sm text-foreground/75 mb-1.5">
              <span className="text-muted-foreground">Reviewer note:</span> {SAMPLE.appeal.qaResponse}
            </p>
            <p className="text-sm text-foreground/75">
              <span className="text-muted-foreground">Human-adjusted score:</span>{" "}
              <span className="font-semibold">{SAMPLE.appeal.correctedScore}</span>{" "}
              <span className="text-[11px] text-muted-foreground">
                (original AI score {r.overallScore} preserved)
              </span>
            </p>
          </GlassCard>

          {/* Tabs */}
          <div className="flex flex-wrap gap-1 border-b border-border/40">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveTab(key)}
                className={cn(
                  "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                  activeTab === key
                    ? "border-accent text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {activeTab === "overview" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="mb-4 text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                <PlayCircle className="w-4 h-4" /> Call Audio
              </h2>
              <audio
                controls
                preload="none"
                src="/sample-call.mp3"
                className="w-full rounded-2xl border border-border/70 bg-background/40"
              >
                Your browser does not support the audio element.
              </audio>
              <p className="mt-2 text-[11px] text-muted-foreground">
                A real customer-service recording, included here as a sample. On live calls the same
                player streams the original audio alongside the scores below.
              </p>
              <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                {Object.entries(r.dimensionScores).map(([key, value]) => (
                  <div key={key} className="p-3 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
                      {key.replace(/_/g, " ")}
                    </p>
                    <span className={cn("text-lg font-semibold", scoreClass(value))}>{value}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {activeTab === "transcript" && (
            <GlassCard className="p-5 sm:p-6 max-h-[700px] overflow-y-auto">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
                <FileText className="w-4 h-4" /> Transcript
              </h2>
              <div className="space-y-2.5">
                {SAMPLE.transcript.map((line, i) => {
                  const isAgent = line.role.toLowerCase().includes("agent");
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.02, duration: 0.2 }}
                      className={cn(
                        "p-3 rounded-2xl border",
                        isAgent ? "bg-accent/[0.06] border-accent/15" : "bg-primary/[0.04] border-primary/10"
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span
                          className={cn(
                            "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                            isAgent ? "bg-accent/15 text-accent" : "bg-primary/15 text-primary"
                          )}
                        >
                          {line.role}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {line.start.toFixed(1)}s – {line.end.toFixed(1)}s
                        </span>
                        {line.emotion && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium bg-warning/10 text-warning">
                            {line.emotion}
                          </span>
                        )}
                        {line.signals.map((sig, si) => (
                          <span
                            key={si}
                            className={cn(
                              "text-[9px] px-1.5 py-0.5 rounded-full font-medium",
                              sig === "FRUSTRATED" || sig === "ESCALATION"
                                ? "bg-destructive/10 text-destructive"
                                : sig === "APOLOGETIC" || sig === "SATISFIED"
                                ? "bg-success/10 text-success"
                                : "bg-muted/30 text-muted-foreground"
                            )}
                          >
                            {sig}
                          </span>
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
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
                <Shield className="w-4 h-4" /> QA Scores
              </h2>

              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-muted-foreground">Grade</span>
                <span className="text-lg font-semibold text-foreground">{r.grade}</span>
              </div>

              <div className="flex items-center justify-between mb-6">
                <span className="text-sm text-muted-foreground">Severity</span>
                <span
                  className={cn(
                    "text-[11px] px-3 py-1.5 rounded-full font-semibold capitalize",
                    severityClass(r.severity)
                  )}
                >
                  {r.severity}
                </span>
              </div>

              <div className="space-y-3">
                {Object.entries(r.dimensionScores).map(([key, value]) => {
                  const conf = r.confidenceScores[key];
                  const lowConf = conf != null && conf < 0.7;
                  return (
                    <div key={key} className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                          {key.replace(/_/g, " ")}
                        </p>
                        <span className={cn("text-sm font-semibold", scoreClass(value))}>{value}</span>
                      </div>
                      <p className="text-xs text-foreground/70 leading-relaxed">{r.dimensionReports[key]}</p>
                      <p className="text-[10px] text-muted-foreground mt-2">
                        Confidence: {conf != null ? `${Math.round(conf * 100)}%` : "N/A"}
                        {lowConf && (
                          <span className="ml-2 text-warning">· flagged for human review (&lt; 70%)</span>
                        )}
                      </p>
                    </div>
                  );
                })}
              </div>
            </GlassCard>
          )}

          {activeTab === "report" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">
                AI Quality Report
              </h2>
              <div className="space-y-4 text-sm text-foreground/75">
                <div>
                  <p className="font-semibold text-foreground mb-1">Summary</p>
                  <p>{r.reportJson.summary}</p>
                </div>
                <div>
                  <p className="font-semibold text-foreground mb-1">Strengths</p>
                  <ul className="list-disc pl-5 space-y-1">
                    {r.reportJson.strengths.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-semibold text-foreground mb-1">Weaknesses</p>
                  <ul className="list-disc pl-5 space-y-1">
                    {r.reportJson.weaknesses.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-semibold text-foreground mb-1">Recommended Actions</p>
                  <ul className="list-disc pl-5 space-y-1">
                    {r.reportJson.recommended_actions.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </GlassCard>
          )}

          {activeTab === "evidence" && (
            <GlassCard className="p-5 sm:p-6">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">
                Evidence
              </h2>
              <div className="space-y-3">
                {r.evidence.map((item, i) => (
                  <div key={i} className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
                      {item.dimension.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs italic text-foreground/75 mb-1">"{item.quote}"</p>
                    <p className="text-[11px] text-muted-foreground">
                      {item.speaker} · {item.reason}
                    </p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <div className="pt-2 text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-primary to-accent px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-xl shadow-primary/25 transition-all hover:brightness-110"
            >
              Analyze your own calls — Sign In
              <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </div>
        </main>
      </div>
    </PageTransition>
  );
};

export default SampleReport;
