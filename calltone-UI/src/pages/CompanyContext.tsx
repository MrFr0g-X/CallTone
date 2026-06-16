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
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";

type Tab = "companies" | "upload" | "tickets";

const STATUS_COLORS: Record<string, string> = {
  applied:  "bg-success/10 text-success",
  declined: "bg-destructive/10 text-destructive",
  // legacy human-reviewed tickets
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
  // The most recent AI decision, shown inline right after submitting.
  const [lastOutcome, setLastOutcome] = useState<ContextTicket | null>(null);
  const platformScope = user?.roleScope === "platform";
  const canSubmitTickets = Boolean(user?.capabilities?.canSubmitContextTickets);

  useEffect(() => {
    if (!platformScope) {
      setForm((current) => ({ ...current, companyName: user?.clientName ?? "" }));
    }
  }, [platformScope, user?.clientName]);

  const { data, isLoading } = useQuery({
    queryKey: ["context-tickets"],
    queryFn: () => contextApi.listTickets().then(r => r.data.tickets),
  });

  const handleCreate = async () => {
    if (!form.companyName || !form.fieldName || !form.newText || !form.reason) {
      toast({ title: "Fill all required fields", variant: "destructive" });
      return;
    }
    setCreating(true);
    try {
      const { data: ticket } = await contextApi.createTicket(form);
      queryClient.invalidateQueries({ queryKey: ["context-tickets"] });
      queryClient.invalidateQueries({ queryKey: ["context-companies"] });
      queryClient.invalidateQueries({ queryKey: ["context-detail", form.companyName] });
      setLastOutcome(ticket);
      if (ticket.status === "applied") {
        setShowCreate(false);
        setForm({ companyName: platformScope ? "" : user?.clientName ?? "", fieldName: "", oldText: "", newText: "", reason: "" });
        toast({ title: "Change applied", description: "The AI applied your change to the company context." });
      } else {
        // Declined: keep the form open so the user can rephrase and resubmit.
        toast({ title: "Change declined", description: ticket.ai_reasoning || "The AI declined this change. Please rephrase and resubmit.", variant: "destructive" });
      }
    } catch (error) {
      toast({ title: "Failed to submit change", description: apiErrorMessage(error, "Could not submit this change request."), variant: "destructive" });
    } finally {
      setCreating(false);
    }
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

      {/* Inline AI outcome from the last submission */}
      <AnimatePresence>
        {lastOutcome && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            <GlassCard
              className={cn(
                "rounded-2xl p-4 border",
                lastOutcome.status === "applied" ? "border-success/30" : "border-destructive/30",
              )}
            >
              <div className="flex items-start gap-3">
                {lastOutcome.status === "applied"
                  ? <CheckCircle className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                  : <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground">
                    {lastOutcome.status === "applied"
                      ? "AI applied your change"
                      : "AI declined your change"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {lastOutcome.ai_reasoning ||
                      (lastOutcome.status === "applied"
                        ? "The change was applied to the company context."
                        : "Please rephrase and resubmit.")}
                  </p>
                </div>
                <button
                  onClick={() => setLastOutcome(null)}
                  className="p-1 rounded-lg hover:bg-foreground/[0.08]"
                >
                  <X className="w-4 h-4 text-muted-foreground" />
                </button>
              </div>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

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
                  {(t.ai_reasoning || t.review_note) && (
                    <p
                      className={cn(
                        "text-xs mt-2 italic",
                        t.status === "declined" ? "text-destructive" : "text-muted-foreground",
                      )}
                    >
                      {t.ai_reasoning || t.review_note}
                    </p>
                  )}
                  {t.status === "applied" && t.diff ? (
                    <div className="mt-2 space-y-1">
                      {t.diff.before && (
                        <div className="p-2 rounded-lg bg-destructive/[0.06] text-xs text-muted-foreground line-clamp-2">
                          <span className="font-medium text-foreground">Before: </span>{t.diff.before}
                        </div>
                      )}
                      <div className="p-2 rounded-lg bg-success/[0.08] text-xs text-muted-foreground line-clamp-3">
                        <span className="font-medium text-foreground">After: </span>{t.diff.after}
                      </div>
                    </div>
                  ) : t.new_text ? (
                    <div className="mt-2 p-2 rounded-lg bg-foreground/[0.04] text-xs text-muted-foreground line-clamp-3">
                      <span className="font-medium text-foreground">Proposed: </span>{t.new_text}
                    </div>
                  ) : null}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {t.status === "applied" || t.status === "approved" ? (
                    <CheckCircle className="w-4 h-4 text-success" />
                  ) : t.status === "declined" || t.status === "rejected" ? (
                    <XCircle className="w-4 h-4 text-destructive" />
                  ) : (
                    <Clock className="w-4 h-4 text-warning" />
                  )}
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground/60 mt-3">
                By {t.submitted_by} · {new Date(t.submitted_at).toLocaleDateString()}
                {t.context_version && ` · v${t.context_version}`}
              </p>
            </GlassCard>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Main Page ────────────────────────────────────────────────────────────────
const CompanyContext = ({ chromeless = false }: { chromeless?: boolean }) => {
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

  const Body = (
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
                    ? "Review your company's scoring context and replace it by uploading an updated policy document. QA change requests are scanned and applied automatically; see the outcome under Change Tickets."
                    : "Review your company's scoring context and submit a change when something needs updating. Each change is scanned for safety and applied or declined automatically."}
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
  );

  if (chromeless) return Body;  // rendered inside AdminLayout (sidebar provides chrome)

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole={userRole} />
        {Body}
      </div>
    </PageTransition>
  );
};

export default CompanyContext;
