import { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2, Upload, FileText, Ticket, CheckCircle, XCircle,
  Clock, AlertCircle, ChevronDown, ChevronUp, Loader2, Plus, X,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";
import { apiErrorMessage, contextApi } from "@/services/api";
import type { CompanyContextSummary, ContextTicket, IngestResult, IngestJobStatus } from "@/services/api";
import { cn } from "@/lib/utils";
import { toContextGroups } from "@/lib/contextSchema";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";

type Tab = "companies" | "upload" | "tickets";

const STATUS_COLORS: Record<string, string> = {
  pending:  "bg-warning/10 text-warning",
  approved: "bg-success/10 text-success",
  rejected: "bg-destructive/10 text-destructive",
};

// ─── Company card ─────────────────────────────────────────────────────────────
const CompanyCard = ({ company, defaultExpanded = false }: { company: CompanyContextSummary; defaultExpanded?: boolean }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const { data: detail, isLoading } = useQuery({
    queryKey: ["context-detail", company.name],
    queryFn: () => contextApi.getCompany(company.name).then(r => r.data),
    enabled: expanded,
  });

  return (
    <GlassCard className="rounded-2xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-5 text-left"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center gap-3">
          <Building2 className="w-5 h-5 text-accent flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-foreground">{company.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              v{company.version} · {company.updated || "—"} · {company.fieldCount} fields filled
            </p>
          </div>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 border-t border-border/30 pt-4">
              {isLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading context...
                </div>
              ) : detail ? (
                (() => {
                  const g = toContextGroups(detail as Record<string, unknown>);
                  return (
                    <div className="space-y-5">
                      {g.groups.map((grp) => (
                        <div key={grp.key}>
                          <p className="text-xs font-semibold text-foreground mb-2">{grp.label}</p>
                          <div className="grid sm:grid-cols-2 gap-3">
                            {grp.fields.map((f) => (
                              <div key={f.key} className="flex items-start gap-2">
                                {f.filled
                                  ? <CheckCircle className="w-3.5 h-3.5 text-success mt-0.5 flex-shrink-0" />
                                  : <XCircle className="w-3.5 h-3.5 text-muted-foreground/40 mt-0.5 flex-shrink-0" />}
                                <div className="min-w-0">
                                  <p className={cn("text-xs font-medium", f.filled ? "text-foreground" : "text-muted-foreground/50")}>{f.label}</p>
                                  {f.filled && <p className="text-[11px] text-muted-foreground line-clamp-2 mt-0.5">{f.value}</p>}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                      <p className="text-[11px] text-muted-foreground/70">{g.atomicNodeCount} knowledge nodes</p>
                    </div>
                  );
                })()
              ) : (
                <p className="text-sm text-muted-foreground">No detail available.</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
};

// ─── Upload Tab ───────────────────────────────────────────────────────────────
const UploadTab = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState(user?.roleScope === "tenant" ? user?.clientName ?? "" : "");
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<"idle" | "polling" | "success" | "error">("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<IngestJobStatus | null>(null);
  const [errMsg, setErrMsg] = useState("");
  const platformScope = user?.roleScope === "platform";

  useEffect(() => {
    if (!platformScope) {
      setCompanyName(user?.clientName ?? "");
    }
  }, [platformScope, user?.clientName]);

  // Poll for job status every 3 seconds while running
  useEffect(() => {
    if (status !== "polling" || !jobId) return;
    const interval = setInterval(async () => {
      try {
        const r = await contextApi.ingestStatus(jobId);
        setJobStatus(r.data);
        if (r.data.status === "completed") {
          clearInterval(interval);
          setStatus("success");
          queryClient.invalidateQueries({ queryKey: ["context-companies"] });
          toast({ title: "Context ingested!", description: `${companyName} context saved successfully.` });
        } else if (r.data.status === "failed") {
          clearInterval(interval);
          setErrMsg(r.data.error ?? "Ingestion failed.");
          setStatus("error");
        }
      } catch {
        // network hiccup — keep polling
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [status, jobId, companyName, queryClient, toast]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  const handleSubmit = async () => {
    if (!file || !companyName.trim()) {
      toast({ title: "Missing fields", description: "Please select a file and enter the company name.", variant: "destructive" });
      return;
    }
    setStatus("polling");
    setJobStatus(null);
    setJobId(null);
    setErrMsg("");
    try {
      const r = await contextApi.ingest(file, companyName.trim());
      setJobId(r.data.jobId);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to start ingestion.";
      setErrMsg(msg);
      setStatus("error");
    }
  };

  const result = jobStatus?.result;
  const validation = result?.validation as Record<string, unknown> | null;
  const fields = validation ? (validation.fields as Record<string, { status: string; note: string }>) : null;

  return (
    <div className="space-y-6 max-w-2xl">
      <GlassCard className="rounded-2xl p-6 space-y-5">
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 block">Company Name</label>
          <input
            type="text"
            value={companyName}
            onChange={e => setCompanyName(e.target.value)}
            placeholder="e.g. BankServ Global"
            className="w-full h-10 px-4 rounded-xl glass-input text-sm"
            disabled={status === "polling" || !platformScope}
          />
          {!platformScope && (
            <p className="mt-1 text-xs text-muted-foreground">
              Updates apply to your company's context.
            </p>
          )}
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2 block">Policy Document (.txt)</label>
          <div
            className={cn(
              "border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-colors",
              status === "polling" ? "opacity-50 pointer-events-none" : dragOver ? "border-accent bg-accent/5" : "border-border/50 hover:border-accent/50",
            )}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input ref={fileRef} type="file" accept=".txt,text/plain" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileText className="w-5 h-5 text-accent" />
                <span className="text-sm font-medium text-foreground">{file.name}</span>
                <button onClick={e => { e.stopPropagation(); setFile(null); }} className="p-1 rounded-lg hover:bg-foreground/[0.08]">
                  <X className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>
            ) : (
              <>
                <Upload className="w-8 h-8 text-muted-foreground/50 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">Drop your policy .txt file here or click to browse</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Plain text — scripts, products, policies, tone guidelines</p>
              </>
            )}
          </div>
        </div>

        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSubmit}
          disabled={status === "polling" || !file || !companyName.trim()}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg disabled:opacity-50 transition-all"
        >
          {status === "polling" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {status === "polling" ? "Ingest Policy" : "Ingest Policy"}
        </motion.button>

        {/* Live progress bar while polling */}
        {status === "polling" && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
              <span>{jobStatus?.progress ?? "Starting LLM passes…"}</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-foreground/[0.06] overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                animate={{ x: ["-100%", "100%"] }}
                transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground/60">
              LLM is processing the document in 5 passes. This takes a few minutes — you can leave this page and come back.
            </p>
          </div>
        )}

        {status === "error" && (
          <div className="flex items-center gap-2 text-destructive text-sm p-3 rounded-xl bg-destructive/10">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {errMsg}
          </div>
        )}
      </GlassCard>

      {status === "success" && result && fields && (
        <GlassCard className="rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-foreground mb-4">Validation Report — {result.company}</h3>
          <p className="text-xs text-muted-foreground mb-4">
            {(validation?.overall_completeness as string) ?? ""} complete ·{" "}
            {result.atomicNodesCount} knowledge nodes built
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {Object.entries(fields).map(([name, info]) => (
              <div key={name} className="flex items-start gap-2 p-2 rounded-xl bg-foreground/[0.03]">
                {info.status === "ok"
                  ? <CheckCircle className="w-3.5 h-3.5 text-success mt-0.5 flex-shrink-0" />
                  : info.status === "missing"
                  ? <XCircle className="w-3.5 h-3.5 text-destructive mt-0.5 flex-shrink-0" />
                  : <AlertCircle className="w-3.5 h-3.5 text-warning mt-0.5 flex-shrink-0" />
                }
                <div>
                  <p className="text-xs font-medium text-foreground capitalize">{name.replace(/_/g, " ")}</p>
                  {info.note && info.status !== "ok" && (
                    <p className="text-[10px] text-muted-foreground mt-0.5">{info.note}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
};

// ─── Tickets Tab ──────────────────────────────────────────────────────────────
const TicketsTab = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ companyName: user?.roleScope === "tenant" ? user?.clientName ?? "" : "", fieldName: "", oldText: "", newText: "", reason: "" });
  const [creating, setCreating] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<{
    ticketId: string;
    status: "approved" | "rejected";
  } | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const platformScope = user?.roleScope === "platform";
  const canSubmitTickets = Boolean(user?.capabilities?.canSubmitContextTickets);
  const canReviewTickets =
    user?.role === "owner" || user?.role === "admin" || user?.role === "super_admin";

  useEffect(() => {
    if (!platformScope) {
      setForm((current) => ({ ...current, companyName: user?.clientName ?? "" }));
    }
  }, [platformScope, user?.clientName]);

  const { data, isLoading } = useQuery({
    queryKey: ["context-tickets"],
    queryFn: () => contextApi.listTickets().then(r => r.data.tickets),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ ticketId, status, note }: { ticketId: string; status: "approved" | "rejected"; note?: string }) =>
      contextApi.updateTicket(ticketId, status, note),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["context-tickets"] });
      toast({ title: `Ticket ${variables.status}`, description: "Change request status updated." });
    },
    onError: (error: unknown) => {
      toast({
        title: "Ticket update failed",
        description: apiErrorMessage(error, "Could not update this change request."),
        variant: "destructive",
      });
    },
  });

  const handleCreate = async () => {
    if (!form.companyName || !form.fieldName || !form.newText || !form.reason) {
      toast({ title: "Fill all required fields", variant: "destructive" });
      return;
    }
    setCreating(true);
    try {
      await contextApi.createTicket(form);
      queryClient.invalidateQueries({ queryKey: ["context-tickets"] });
      setShowCreate(false);
      setForm({ companyName: "", fieldName: "", oldText: "", newText: "", reason: "" });
      toast({ title: "Ticket created", description: "Your change request has been submitted." });
    } catch {
      toast({ title: "Failed to create ticket", variant: "destructive" });
    } finally {
      setCreating(false);
    }
  };

  const reviewTicket = (ticketId: string, status: "approved" | "rejected") => {
    setReviewTarget({ ticketId, status });
    setReviewNote("");
  };

  const submitReview = () => {
    if (!reviewTarget) return;
    reviewMutation.mutate(
      {
        ticketId: reviewTarget.ticketId,
        status: reviewTarget.status,
        note: reviewNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          setReviewTarget(null);
          setReviewNote("");
        },
      },
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{data?.length ?? 0} ticket{data?.length !== 1 ? "s" : ""}</p>
        {canSubmitTickets && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-xs font-semibold"
          >
            <Plus className="w-3.5 h-3.5" /> New Change Request
          </motion.button>
        )}
      </div>

      {/* Create form */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <GlassCard className="rounded-2xl p-6 space-y-4 border border-accent/20">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">New Change Request</h3>
                <button onClick={() => setShowCreate(false)} className="p-1 rounded-lg hover:bg-foreground/[0.08]">
                  <X className="w-4 h-4 text-muted-foreground" />
                </button>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">Company *</label>
                  <input value={form.companyName} onChange={e => setForm(f => ({ ...f, companyName: e.target.value }))}
                    placeholder="BankServ Global" disabled={!platformScope} className="w-full h-9 px-3 rounded-xl glass-input text-sm disabled:opacity-70" />
                  {!platformScope && (
                    <p className="mt-1 text-[10px] text-muted-foreground">Locked to your company.</p>
                  )}
                </div>
                <div>
                  <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">Field Name *</label>
                  <input value={form.fieldName} onChange={e => setForm(f => ({ ...f, fieldName: e.target.value }))}
                    placeholder="e.g. greeting_script" className="w-full h-9 px-3 rounded-xl glass-input text-sm" />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">Current Text (optional)</label>
                <textarea value={form.oldText} onChange={e => setForm(f => ({ ...f, oldText: e.target.value }))}
                  rows={2} className="w-full px-3 py-2 rounded-xl glass-input text-sm resize-none" placeholder="What the policy currently says…" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">Proposed New Text *</label>
                <textarea value={form.newText} onChange={e => setForm(f => ({ ...f, newText: e.target.value }))}
                  rows={3} className="w-full px-3 py-2 rounded-xl glass-input text-sm resize-none" placeholder="What it should say instead…" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground uppercase tracking-wider mb-1 block">Reason for Change *</label>
                <textarea value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
                  rows={2} className="w-full px-3 py-2 rounded-xl glass-input text-sm resize-none" placeholder="Why this change is needed…" />
              </div>
              <motion.button
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={handleCreate} disabled={creating}
                className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold disabled:opacity-60"
              >
                {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ticket className="w-4 h-4" />}
                Submit Ticket
              </motion.button>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

      {isLoading ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading tickets…
        </div>
      ) : (data ?? []).length === 0 ? (
        <GlassCard className="rounded-2xl p-8 text-center">
          <Ticket className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No change tickets yet.</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {(data ?? []).map((t: ContextTicket) => (
            <GlassCard key={t.ticket_id} className="rounded-2xl p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-xs font-mono text-muted-foreground">{t.ticket_id}</span>
                    <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-medium capitalize", STATUS_COLORS[t.status] ?? "bg-muted/30 text-muted-foreground")}>
                      {t.status}
                    </span>
                    <span className="text-xs text-muted-foreground">{t.company_name}</span>
                  </div>
                  <p className="text-sm font-medium text-foreground capitalize">{t.field_name.replace(/_/g, " ")}</p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{t.reason}</p>
                  {t.new_text && (
                    <div className="mt-2 p-2 rounded-lg bg-foreground/[0.04] text-xs text-muted-foreground line-clamp-3">
                      <span className="font-medium text-foreground">Proposed: </span>{t.new_text}
                    </div>
                  )}
                  {t.review_note && (
                    <p className="text-xs text-muted-foreground mt-2 italic">Note: {t.review_note}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {t.status === "pending" ? (
                    <Clock className="w-4 h-4 text-warning" />
                  ) : t.status === "approved" ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : (
                    <XCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
              </div>
              {canReviewTickets && t.status === "pending" && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-border/40 pt-3">
                  <button
                    onClick={() => reviewTicket(t.ticket_id, "approved")}
                    disabled={reviewMutation.isPending}
                    className="rounded-xl bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition-colors hover:bg-success/20 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => reviewTicket(t.ticket_id, "rejected")}
                    disabled={reviewMutation.isPending}
                    className="rounded-xl bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition-colors hover:bg-destructive/20 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground/60 mt-3">
                By {t.submitted_by} · {new Date(t.submitted_at).toLocaleDateString()}
                {t.reviewed_by && ` · Reviewed by ${t.reviewed_by}`}
              </p>
            </GlassCard>
          ))}
        </div>
      )}

      <AnimatePresence>
        {reviewTarget && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
            onClick={() => {
              if (!reviewMutation.isPending) setReviewTarget(null);
            }}
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }}
              className="glass-strong w-full max-w-md rounded-2xl border border-border/60 p-6 shadow-2xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">
                    {reviewTarget.status === "approved" ? "Approve change request" : "Reject change request"}
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Add an optional review note. This is stored with the ticket audit trail.
                  </p>
                </div>
                <button
                  onClick={() => setReviewTarget(null)}
                  disabled={reviewMutation.isPending}
                  className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground disabled:opacity-50"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <textarea
                value={reviewNote}
                onChange={(event) => setReviewNote(event.target.value)}
                rows={4}
                className="mt-5 w-full resize-none rounded-xl glass-input px-3 py-2 text-sm"
                placeholder="Optional note for the requester..."
              />

              <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  onClick={() => setReviewTarget(null)}
                  disabled={reviewMutation.isPending}
                  className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/40 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={submitReview}
                  disabled={reviewMutation.isPending}
                  className={cn(
                    "rounded-xl px-4 py-2 text-sm font-semibold transition-colors disabled:opacity-50",
                    reviewTarget.status === "approved"
                      ? "bg-success text-white hover:brightness-110"
                      : "bg-destructive text-destructive-foreground hover:brightness-110",
                  )}
                >
                  {reviewMutation.isPending
                    ? "Saving..."
                    : reviewTarget.status === "approved"
                    ? "Approve"
                    : "Reject"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─── Main Page ────────────────────────────────────────────────────────────────
const CompanyContext = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("companies");
  const userRole = user?.role === "qa" ? "qa" : "admin";
  const canManageContext = Boolean(user?.capabilities?.canManageContext);
  const platformScope = user?.roleScope === "platform";
  const contextScopeLabel = platformScope ? "Platform context workspace" : `${user?.clientName ?? "Your company"} context workspace`;

  const { data: companiesData, isLoading: companiesLoading } = useQuery({
    queryKey: ["context-companies"],
    queryFn: () => contextApi.listCompanies().then(r => r.data.companies),
  });

  const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: "companies", label: platformScope ? "Companies" : "Context",  icon: Building2 },
    ...(canManageContext ? [{ id: "upload" as const, label: platformScope ? "Upload Context" : "Replace Context", icon: Upload }] : []),
    { id: "tickets",   label: "Change Tickets", icon: Ticket },
  ];

  useEffect(() => {
    if (tab === "upload" && !canManageContext) {
      setTab("tickets");
    }
  }, [tab, canManageContext]);

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole={userRole} />

        <main className="max-w-5xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8">
          <header>
            <h1 className="text-3xl sm:text-4xl font-light text-foreground tracking-tight">
              Company{" "}
              <span className="font-bold gradient-text">Context</span>
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Manage company policies the AI uses when scoring calls.
            </p>
          </header>

          <GlassCard className="rounded-2xl p-5">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
                <Building2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{contextScopeLabel}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {platformScope
                    ? "View and manage the scoring context for any company."
                    : canManageContext
                    ? "Review your company's scoring context and replace it by uploading an updated policy document. Change requests from your QA team appear under Change Tickets for you to approve."
                    : "Review your company's scoring context and send a change request when something needs updating. Your admins handle the approval."}
                </p>
              </div>
            </div>
          </GlassCard>

          {/* Tabs */}
          <div className="flex gap-1 p-1 rounded-2xl bg-foreground/[0.04] w-fit">
            {tabs.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium transition-all",
                  tab === t.id
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <t.icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              {tab === "companies" && (
                <div className="space-y-4">
                  {companiesLoading ? (
                    <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
                      <Loader2 className="w-4 h-4 animate-spin" /> Loading companies…
                    </div>
                  ) : (companiesData ?? []).length === 0 ? (
                    <GlassCard className="rounded-2xl p-10 text-center">
                      <Building2 className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
                      <p className="text-sm text-muted-foreground">No company contexts yet.</p>
                      <p className="text-xs text-muted-foreground/60 mt-1">Upload a policy document in the Upload tab to get started.</p>
                    </GlassCard>
                  ) : platformScope ? (
                    (companiesData ?? []).map(c => <CompanyCard key={c.name} company={c} />)
                  ) : (
                    <CompanyCard company={(companiesData ?? [])[0]} defaultExpanded />
                  )}
                </div>
              )}
              {tab === "upload"  && canManageContext && <UploadTab />}
              {tab === "tickets" && <TicketsTab />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </PageTransition>
  );
};

export default CompanyContext;
