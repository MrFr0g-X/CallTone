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
