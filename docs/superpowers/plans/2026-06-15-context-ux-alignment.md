# Context UX Alignment Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three visible Company-Context UX defects: (B) every field renders ✗ because the UI reads a flat schema while the real context is grouped; (C) QA (single-company) sees a plural "Companies" list; (E) admins land on the QA URL `/qa/context` with a QA "Upload" affordance instead of an admin-shell context page.

**Architecture:** All changes live in the existing React SPA (`calltone-UI`). `CompanyContext.tsx` becomes schema-aware (renders the grouped context: `script_compliance` / `factual_accuracy` / `behavioral` + `atomic_nodes`, with a flat-schema fallback) and scope-aware (platform → multi-company list; tenant → that one company's context directly). A new `chromeless` prop lets the same page render inside `AdminLayout` at a new `/admin/context` route (admin sidebar, no QA `Navbar`/Upload).

**Tech Stack:** React + TypeScript + Vite, TailwindCSS, framer-motion, react-router-dom, @tanstack/react-query, vitest. Verify with `npx tsc -p tsconfig.app.json --noEmit`, `npx vitest run`, `npm run build`, and Playwright per-role on staging.

**Pre-req:** branch `feature/product-overhaul-2026-06-12` (current). No backend or GPU needed.

---

### Task 1: Schema-aware context field model + unit test

**Files:**
- Create: `calltone-UI/src/lib/contextSchema.ts`
- Test: `calltone-UI/src/test/contextSchema.test.ts`

Real context JSON top-level keys (verified live): `company_name`, `context_version`,
`last_updated`, `script_compliance` (obj), `factual_accuracy` (obj), `behavioral`
(obj), `atomic_nodes` (array). The legacy flat schema used top-level string fields
(`greeting_script`, …). This module normalizes either shape into display groups.

- [ ] **Step 1: Write the failing test**

```ts
// calltone-UI/src/test/contextSchema.test.ts
import { describe, it, expect } from "vitest";
import { toContextGroups } from "@/lib/contextSchema";

describe("toContextGroups", () => {
  it("reads the grouped schema and marks filled vs empty", () => {
    const g = toContextGroups({
      company_name: "metro boost",
      script_compliance: { greeting_script: "Hi, thanks for calling", closing_script: "" },
      factual_accuracy: { products_and_services: "fibre, mobile" },
      behavioral: { tone_guidelines: "" },
      atomic_nodes: [{ id: 1 }, { id: 2 }],
    });
    const sc = g.groups.find((x) => x.key === "script_compliance")!;
    expect(sc.fields.find((f) => f.key === "greeting_script")!.filled).toBe(true);
    expect(sc.fields.find((f) => f.key === "closing_script")!.filled).toBe(false);
    expect(g.atomicNodeCount).toBe(2);
    expect(g.filledCount).toBe(2); // greeting_script + products_and_services
  });

  it("falls back to flat legacy schema", () => {
    const g = toContextGroups({ company_name: "X", greeting_script: "Hello" });
    expect(g.filledCount).toBe(1);
    expect(g.groups.some((grp) => grp.fields.some((f) => f.key === "greeting_script" && f.filled))).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd calltone-UI && npx vitest run src/test/contextSchema.test.ts`
Expected: FAIL — `toContextGroups` not found.

- [ ] **Step 3: Write minimal implementation**

```ts
// calltone-UI/src/lib/contextSchema.ts
export type ContextField = { key: string; label: string; filled: boolean; value: string };
export type ContextGroup = { key: string; label: string; fields: ContextField[] };
export type ContextGroups = { groups: ContextGroup[]; filledCount: number; atomicNodeCount: number };

const GROUPS: Record<string, { label: string; fields: string[] }> = {
  script_compliance: {
    label: "Script Compliance",
    fields: ["greeting_script", "closing_script", "required_verification_steps",
      "hold_procedure", "transfer_procedure", "escalation_procedure", "mandatory_disclosures", "prohibited_phrases"],
  },
  factual_accuracy: {
    label: "Factual Accuracy",
    fields: ["products_and_services", "current_promotions", "policies",
      "common_troubleshooting", "contact_information", "frequently_asked_questions"],
  },
  behavioral: {
    label: "Behavioral",
    fields: ["tone_guidelines", "empathy_guidelines", "conflict_resolution_guidelines", "resolution_expectations"],
  },
};

const titleize = (k: string) => k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function toContextGroups(detail: Record<string, unknown> | null | undefined): ContextGroups {
  const d = detail ?? {};
  let filledCount = 0;
  const groups: ContextGroup[] = Object.entries(GROUPS).map(([gkey, g]) => ({
    key: gkey,
    label: g.label,
    fields: g.fields.map((fkey) => {
      // grouped schema: d[gkey][fkey]; flat fallback: d[fkey]
      const group = d[gkey];
      const raw = group && typeof group === "object"
        ? (group as Record<string, unknown>)[fkey]
        : (d as Record<string, unknown>)[fkey];
      const value = typeof raw === "string" ? raw.trim() : "";
      const filled = value.length > 0;
      if (filled) filledCount += 1;
      return { key: fkey, label: titleize(fkey), filled, value };
    }),
  }));
  const atomicNodeCount = Array.isArray((d as Record<string, unknown>).atomic_nodes)
    ? ((d as Record<string, unknown>).atomic_nodes as unknown[]).length : 0;
  return { groups, filledCount, atomicNodeCount };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd calltone-UI && npx vitest run src/test/contextSchema.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add calltone-UI/src/lib/contextSchema.ts calltone-UI/src/test/contextSchema.test.ts
git commit -m "feat(context): schema-aware context grouping helper (B)"
```

---

### Task 2: Render grouped fields in CompanyCard (fixes all-✗)

**Files:**
- Modify: `calltone-UI/src/pages/CompanyContext.tsx` (the `CompanyCard` component + remove the flat `CONTEXT_FIELDS` constant)

- [ ] **Step 1: Replace the flat `CONTEXT_FIELDS` constant** (top of file) — delete the `CONTEXT_FIELDS` array and import the helper:

```ts
import { toContextGroups } from "@/lib/contextSchema";
```

- [ ] **Step 2: Rewrite the expanded body of `CompanyCard`** — replace the `CONTEXT_FIELDS.map(...)` grid block with grouped rendering:

```tsx
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
```

- [ ] **Step 3: Verify types + build**

Run: `cd calltone-UI && npx tsc -p tsconfig.app.json --noEmit && npx vitest run`
Expected: tsc 0 errors, all vitest pass.

- [ ] **Step 4: Commit**

```bash
git add calltone-UI/src/pages/CompanyContext.tsx
git commit -m "fix(context): render grouped context schema so fields show filled (B)"
```

---

### Task 3: Tenant scope shows one company, not a "Companies" list (C)

**Files:**
- Modify: `calltone-UI/src/pages/CompanyContext.tsx` (tab labels + tab content + header copy)

- [ ] **Step 1: Compute tenant vs platform + relabel tabs.** In the `CompanyContext` component, after `const platformScope = ...`, change the `tabs` array's first entry label and gate it:

```ts
const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "companies", label: platformScope ? "Companies" : "Context", icon: Building2 },
  ...(canManageContext ? [{ id: "upload" as const, label: platformScope ? "Upload Context" : "Replace Context", icon: Upload }] : []),
  { id: "tickets", label: "Change Tickets", icon: Ticket },
];
```

- [ ] **Step 2: For tenant scope, auto-expand the single company and drop list chrome.** In the `companies` tab body, when `!platformScope`, render the one company's card expanded by default (pass an `defaultExpanded` prop to `CompanyCard`); when `platformScope`, keep the list. Add the prop:

```tsx
// CompanyCard signature:
const CompanyCard = ({ company, defaultExpanded = false }: { company: CompanyContextSummary; defaultExpanded?: boolean }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
```

```tsx
// companies tab body:
{tab === "companies" && (
  <div className="space-y-4">
    {companiesLoading ? (
      <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    ) : (companiesData ?? []).length === 0 ? (
      <GlassCard className="rounded-2xl p-10 text-center">
        <Building2 className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-sm text-muted-foreground">No company context yet.</p>
      </GlassCard>
    ) : platformScope ? (
      (companiesData ?? []).map((c) => <CompanyCard key={c.name} company={c} />)
    ) : (
      <CompanyCard company={(companiesData ?? [])[0]} defaultExpanded />
    )}
  </div>
)}
```

- [ ] **Step 3: Verify**

Run: `cd calltone-UI && npx tsc -p tsconfig.app.json --noEmit && npx vitest run`
Expected: tsc 0, vitest pass.

- [ ] **Step 4: Commit**

```bash
git add calltone-UI/src/pages/CompanyContext.tsx
git commit -m "fix(context): tenant scope shows single company context, not a Companies list (C)"
```

---

### Task 4: `chromeless` prop so the page can render inside AdminLayout (E, part 1)

**Files:**
- Modify: `calltone-UI/src/pages/CompanyContext.tsx`

- [ ] **Step 1: Accept a `chromeless` prop and skip the QA `Navbar` + `AnimatedBackground` when set.** Change the component signature and the outer JSX:

```tsx
const CompanyContext = ({ chromeless = false }: { chromeless?: boolean }) => {
  // ...existing hooks...
  const Body = (
    <main className="max-w-5xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8">
      {/* ...existing header + cards + tabs... */}
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
```

- [ ] **Step 2: Verify**

Run: `cd calltone-UI && npx tsc -p tsconfig.app.json --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add calltone-UI/src/pages/CompanyContext.tsx
git commit -m "feat(context): chromeless render mode for admin shell (E)"
```

---

### Task 5: `/admin/context` route + sidebar points there (E, part 2)

**Files:**
- Modify: `calltone-UI/src/App.tsx` (add child route under the `/admin` AdminLayout block)
- Modify: `calltone-UI/src/components/AdminSidebar.tsx` (Company Context link → `/admin/context`)
- Modify: `calltone-UI/src/components/AdminMobileNav.tsx` (same)

- [ ] **Step 1: Add the admin child route.** In `App.tsx`, inside the `<Route path="/admin" element={<AdminLayout/>}>` children, add:

```tsx
<Route path="context" element={
  <ProtectedRoute allowedRoles={["owner", "admin", "super_admin"]}>
    <CompanyContext chromeless />
  </ProtectedRoute>
} />
```

(Keep the existing `/qa/context` route for QA. `CompanyContext` is already imported.)

- [ ] **Step 2: Point the admin nav links to `/admin/context`.** In `AdminSidebar.tsx` and `AdminMobileNav.tsx`, change the nav item:

```ts
{ to: "/admin/context", label: "Company Context", icon: FileText },
```

and the `visibleNavItems` filter rule:

```ts
if (item.to === "/admin/context") return Boolean(user?.capabilities?.canManageContext);
```

- [ ] **Step 3: Verify build + types**

Run: `cd calltone-UI && npx tsc -p tsconfig.app.json --noEmit && npm run build`
Expected: tsc 0, build OK.

- [ ] **Step 4: Commit**

```bash
git add calltone-UI/src/App.tsx calltone-UI/src/components/AdminSidebar.tsx calltone-UI/src/components/AdminMobileNav.tsx
git commit -m "feat(context): dedicated /admin/context route in admin shell, no QA Upload (E)"
```

---

### Task 6: Deploy to staging + per-role browser verification (B + C + E)

**Files:** none (deploy + verify)

- [ ] **Step 1: Build with staging API + deploy** (same pattern as prior staging deploys):

```bash
cd calltone-UI && VITE_API_BASE_URL="https://api-staging.calltone.tech/api" npm run build
# tar dist, pscp to webspace, extract into /usr/www/users/gsx8iy/staging with backup (existing deploy pattern)
```

- [ ] **Step 2: Playwright — QA (`staging_calltone_qa@spamok.com`)**: `/qa/context` → tab reads **"Context"** (not "Companies"); the single company auto-expands; grouped fields show ✓ for filled (not all ✗); Change Tickets present; 0 console errors.

- [ ] **Step 3: Playwright — Admin (`staging_calltone_admin@spamok.com`)**: sidebar **Company Context** → URL is **`/admin/context`** (not `/qa/context`); admin sidebar visible; **no "Upload"** top-nav item; tabs Context + Replace Context + Change Tickets; 0 console errors.

- [ ] **Step 4: Confirm no regression for platform scope** (if a platform/owner test user exists): `/admin/context` still shows the multi-company list.

- [ ] **Step 5: Commit** any fixes found, else note verification complete in the vault (`Context-Tickets-Appeals-2026-06-15.md`).

---

## Self-Review
- **Spec coverage:** B (Task 1–2), C (Task 3), E (Task 4–5), verification (Task 6). A/D/F are separate plans. ✓
- **Type consistency:** `toContextGroups`, `ContextGroups.filledCount`, `atomicNodeCount`, `CompanyCard defaultExpanded`, `CompanyContext chromeless` used consistently across tasks. ✓
- **Placeholders:** none — all steps carry real code/commands. ✓
- **Note:** `fieldCount` shown in the card subtitle ("21 fields filled") comes from the backend `list_companies`; if it disagrees with the grouped `filledCount`, prefer the UI `filledCount` in the subtitle (Task 3 optional tweak) — backend count is cosmetic, not in scope to change here.
