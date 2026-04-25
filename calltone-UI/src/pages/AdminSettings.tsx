import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArchiveX, Cpu, Loader2, RefreshCw, RotateCcw, Save, ShieldCheck } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { apiErrorMessage, contextApi, pipelineApi } from "@/services/api";
import type { CompanyContextSummary, PipelineJobResponse, PipelineQueueResponse, PipelineSettingsResponse } from "@/services/api";

const AdminSettings = () => {
  const { toast } = useToast();
  const [pipeline, setPipeline] = useState<PipelineSettingsResponse>({
    audioMode: "denoise",
    injectionScan: "static",
    numSpeakers: null,
    reportMode: "narrative",
    useConsensus: false,
    companyName: "",
  });
  const [companies, setCompanies] = useState<CompanyContextSummary[]>([]);
  const [queue, setQueue] = useState<PipelineQueueResponse | null>(null);
  const [jobs, setJobs] = useState<PipelineJobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [jobActionCallId, setJobActionCallId] = useState<string | null>(null);

  const loadQueueState = async () => {
    setQueueLoading(true);
    try {
      const [queueRes, jobsRes] = await Promise.all([
        pipelineApi.getQueue(),
        pipelineApi.getJobs(undefined, 20),
      ]);
      setQueue(queueRes.data);
      setJobs(jobsRes.data.jobs);
    } catch (error: unknown) {
      toast({
        title: "Queue unavailable",
        description: apiErrorMessage(error, "Could not load pipeline queue."),
        variant: "destructive",
      });
    } finally {
      setQueueLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([pipelineApi.getSettings(), contextApi.listCompanies(), pipelineApi.getQueue(), pipelineApi.getJobs(undefined, 20)])
      .then(([settingsRes, companiesRes, queueRes, jobsRes]) => {
        if (cancelled) return;
        setPipeline(settingsRes.data);
        setCompanies(companiesRes.data.companies || []);
        setQueue(queueRes.data);
        setJobs(jobsRes.data.jobs);
      })
      .catch(() => {
        toast({
          title: "Settings unavailable",
          description: "Could not load live pipeline configuration.",
          variant: "destructive",
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const handlePipelineSave = async () => {
    setSaving(true);
    try {
      const response = await pipelineApi.updateSettings(pipeline);
      setPipeline(response.data);
      toast({ title: "Pipeline settings saved", description: "Future uploads will use this configuration." });
    } catch (error: unknown) {
      toast({
        title: "Save failed",
        description: apiErrorMessage(error, "Could not save pipeline settings."),
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleRetryJob = async (callId: string) => {
    setJobActionCallId(callId);
    try {
      await pipelineApi.retryJob(callId);
      await loadQueueState();
      toast({ title: "Job requeued", description: `Call ${callId} is back in the GPU queue.` });
    } catch (error: unknown) {
      toast({
        title: "Retry failed",
        description: apiErrorMessage(error, "Could not retry this pipeline job."),
        variant: "destructive",
      });
    } finally {
      setJobActionCallId(null);
    }
  };

  const handleDeadLetterJob = async (callId: string) => {
    setJobActionCallId(callId);
    try {
      await pipelineApi.deadLetterJob(callId);
      await loadQueueState();
      toast({ title: "Job dead-lettered", description: `Call ${callId} will not be retried automatically.` });
    } catch (error: unknown) {
      toast({
        title: "Dead-letter failed",
        description: apiErrorMessage(error, "Could not dead-letter this pipeline job."),
        variant: "destructive",
      });
    } finally {
      setJobActionCallId(null);
    }
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Platform <span className="font-bold gradient-text">Settings</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Only live, backend-backed settings are shown here.
        </p>
      </header>

      <GlassCard className="rounded-2xl p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 text-success" />
          <div>
            <p className="text-sm font-semibold text-foreground">Admin-only control surface</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              User management and pipeline changes are server-enforced for admin and super admin accounts only.
              Manager and viewer accounts can inspect platform data but cannot mutate system settings.
            </p>
          </div>
        </div>
      </GlassCard>

      <GlassCard className="rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
          <Cpu className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">AI Pipeline</h2>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading pipeline settings...
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Default Company Context
              </label>
              <select
                value={pipeline.companyName}
                onChange={(event) => setPipeline((p) => ({ ...p, companyName: event.target.value }))}
                className="w-full max-w-sm h-10 px-4 rounded-xl glass-input text-sm"
              >
                {companies.length === 0 ? (
                  <option value={pipeline.companyName}>{pipeline.companyName || "No company contexts found"}</option>
                ) : (
                  companies.map((company) => (
                    <option key={company.file || company.name} value={company.name}>
                      {company.name}
                    </option>
                  ))
                )}
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">
                The selected context is synced to the GPU model server before scoring.
              </p>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Audio Processing
              </label>
              <div className="flex flex-wrap gap-2">
                {(["none", "denoise", "enhance"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, audioMode: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                      pipeline.audioMode === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "none" ? "Skip" : option === "denoise" ? "Denoise" : "Enhance"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Prompt Injection Scan
              </label>
              <div className="flex gap-2">
                {(["static", "llm"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, injectionScan: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all uppercase",
                      pipeline.injectionScan === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "static" ? "Static" : "LLM"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Speaker Count
              </label>
              <div className="flex gap-2 flex-wrap">
                {[null, 2, 3, 4].map((count) => (
                  <button
                    key={String(count)}
                    onClick={() => setPipeline((p) => ({ ...p, numSpeakers: count }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all",
                      pipeline.numSpeakers === count
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {count === null ? "Auto-detect" : `${count} Speakers`}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Report Generation
              </label>
              <div className="flex gap-2 flex-wrap">
                {(["none", "simple", "narrative", "both"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, reportMode: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                      pipeline.reportMode === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "none" ? "Skip" : option === "both" ? "Both" : option}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-4 py-2">
              <div>
                <p className="text-sm font-medium">Consensus Scoring</p>
                <p className="text-xs text-muted-foreground">
                  Runs each QA criterion multiple times and stores median confidence; slower but more stable.
                </p>
              </div>
              <button
                onClick={() => setPipeline((p) => ({ ...p, useConsensus: !p.useConsensus }))}
                className={cn(
                  "w-10 h-6 rounded-full transition-colors flex items-center px-0.5 shrink-0",
                  pipeline.useConsensus ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start",
                )}
                aria-label="Toggle consensus scoring"
              >
                <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
              </button>
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handlePipelineSave}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all disabled:opacity-60"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Pipeline Settings
            </motion.button>
          </div>
        )}
      </GlassCard>

      <GlassCard className="rounded-2xl p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-5">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              GPU Queue Operations
            </h2>
          </div>
          <button
            onClick={loadQueueState}
            disabled={queueLoading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-accent/50 disabled:opacity-60"
          >
            {queueLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
          {[
            ["Active", queue?.activeCallId ? "1" : "0"],
            ["Queued", String(queue?.queuedCount ?? 0)],
            ["Running", String(queue?.runningCallIds?.length ?? 0)],
            ["Failed", String(queue?.failedCount ?? 0)],
            ["Drain ETA", `${Math.ceil((queue?.estimatedDrainSeconds ?? 0) / 60)}m`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border/50 bg-muted/10 p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
              <p className="mt-1 text-lg font-semibold text-foreground">{value}</p>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-xl border border-border/50">
          <table className="min-w-full text-sm">
            <thead className="bg-muted/20 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Call</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Attempts</th>
                <th className="px-3 py-2 text-left">Engine</th>
                <th className="px-3 py-2 text-left">Company</th>
                <th className="px-3 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-5 text-center text-muted-foreground">
                    No pipeline jobs found.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.id} className="border-t border-border/40">
                    <td className="px-3 py-2 font-mono text-xs">{job.callId.slice(0, 8)}...</td>
                    <td className="px-3 py-2">
                      <span className={cn(
                        "rounded-full px-2 py-1 text-[11px] font-semibold uppercase",
                        job.status === "completed" && "bg-success/15 text-success",
                        job.status === "failed" && "bg-destructive/15 text-destructive",
                        job.status === "running" && "bg-accent/15 text-accent",
                        job.status === "queued" && "bg-muted/30 text-muted-foreground",
                      )}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{job.attempts}/{job.maxAttempts}</td>
                    <td className="px-3 py-2 text-muted-foreground">{job.asrEngine}</td>
                    <td className="px-3 py-2 text-muted-foreground">{job.companyName || "-"}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleRetryJob(job.callId)}
                          disabled={job.status === "running" || job.status === "completed" || jobActionCallId === job.callId}
                          className="inline-flex items-center gap-1 rounded-lg border border-border/50 px-2 py-1 text-[11px] hover:border-accent/60 disabled:opacity-40"
                        >
                          <RotateCcw className="w-3 h-3" />
                          Retry
                        </button>
                        <button
                          onClick={() => handleDeadLetterJob(job.callId)}
                          disabled={job.status === "running" || job.status === "completed" || jobActionCallId === job.callId}
                          className="inline-flex items-center gap-1 rounded-lg border border-border/50 px-2 py-1 text-[11px] hover:border-destructive/60 disabled:opacity-40"
                        >
                          <ArchiveX className="w-3 h-3" />
                          Dead-letter
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
};

export default AdminSettings;
