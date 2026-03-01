export interface Call {
  id: string;
  date: string;
  duration: string;
  overallScore: number;
  politeness: number;
  empathy: number;
  conflict: boolean;
  resolution: boolean;
  scriptCompliance: boolean;
  factualAccuracy: number;
  severity: string;
  status: "reviewed" | "pending" | "flagged";
  agentId?: string;
}

export interface Agent {
  id: string;
  name: string;
  overallScore: number;
  callCount: number;
  trend: number[];
}

export interface TranscriptLine {
  speaker: "agent" | "customer";
  timestamp: string;
  text: string;
  emotion: "neutral" | "anger" | "joy" | "frustration" | "satisfaction";
}

export interface CallDetail {
  id: string;
  date: string;
  duration: string;
  agentName: string;
  customerName: string;
  overallScore: number;
  scores: {
    scriptCompliance: { compliant: boolean; confidence: number; evidence: string };
    factualAccuracy: { score: number; confidence: number; evidence: string };
    politeness: { score: number; confidence: number; evidence: string };
    empathy: { score: number; confidence: number; evidence: string };
    conflict: { detected: boolean; confidence: number; evidence: string };
    resolution: { resolved: boolean; confidence: number; evidence: string };
    severity: { level: string; confidence: number; evidence: string };
  };
  flagForReview: boolean;
  transcript: TranscriptLine[];
  aiReport: string;
}

export const currentUser = {
  name: "Sarah Mitchell",
  role: "agent" as "agent" | "qa",
  email: "sarah@calltone.ai",
};

export const qaUser = {
  name: "James Rodriguez",
  role: "qa" as "agent" | "qa",
  email: "james@calltone.ai",
};

export const agentCalls: Call[] = [
  { id: "call-001", date: "2026-02-28", duration: "4:32", overallScore: 92, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  { id: "call-002", date: "2026-02-27", duration: "6:15", overallScore: 78, politeness: 3, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  { id: "call-003", date: "2026-02-27", duration: "8:47", overallScore: 45, politeness: 2, empathy: 2, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 3, severity: "major", status: "flagged" },
  { id: "call-004", date: "2026-02-26", duration: "3:21", overallScore: 88, politeness: 4, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  { id: "call-005", date: "2026-02-26", duration: "5:58", overallScore: 95, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  { id: "call-006", date: "2026-02-25", duration: "7:12", overallScore: 62, politeness: 3, empathy: 2, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "flagged" },
  { id: "call-007", date: "2026-02-25", duration: "2:45", overallScore: 85, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  { id: "call-008", date: "2026-02-24", duration: "9:03", overallScore: 38, politeness: 1, empathy: 2, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 2, severity: "critical", status: "flagged" },
  { id: "call-009", date: "2026-02-24", duration: "4:18", overallScore: 91, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  { id: "call-010", date: "2026-02-23", duration: "5:30", overallScore: 82, politeness: 4, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "pending" },
];

export const agents: Agent[] = [
  { id: "agent-1", name: "Sarah Mitchell", overallScore: 87, callCount: 142, trend: [82, 84, 83, 86, 88, 87, 89, 87] },
  { id: "agent-2", name: "David Chen", overallScore: 92, callCount: 158, trend: [88, 89, 90, 91, 93, 92, 91, 92] },
  { id: "agent-3", name: "Emily Watson", overallScore: 74, callCount: 123, trend: [78, 76, 75, 72, 73, 74, 75, 74] },
  { id: "agent-4", name: "Michael Torres", overallScore: 81, callCount: 136, trend: [79, 80, 78, 82, 83, 81, 80, 81] },
  { id: "agent-5", name: "Jessica Kim", overallScore: 95, callCount: 167, trend: [91, 92, 93, 94, 95, 96, 95, 95] },
  { id: "agent-6", name: "Robert Brown", overallScore: 68, callCount: 98, trend: [72, 70, 69, 67, 66, 68, 69, 68] },
  { id: "agent-7", name: "Amanda Garcia", overallScore: 91, callCount: 151, trend: [87, 88, 89, 90, 91, 92, 91, 91] },
  { id: "agent-8", name: "Kevin Patel", overallScore: 63, callCount: 87, trend: [68, 66, 65, 63, 62, 61, 63, 63] },
  { id: "agent-9", name: "Lisa Nakamura", overallScore: 89, callCount: 144, trend: [85, 86, 87, 88, 89, 90, 89, 89] },
  { id: "agent-10", name: "Carlos Rivera", overallScore: 77, callCount: 112, trend: [74, 75, 76, 78, 77, 76, 77, 77] },
  { id: "agent-11", name: "Hannah Osei", overallScore: 94, callCount: 163, trend: [90, 91, 92, 93, 94, 95, 94, 94] },
  { id: "agent-12", name: "Tyler Jackson", overallScore: 72, callCount: 105, trend: [75, 74, 73, 71, 70, 72, 73, 72] },
  { id: "agent-13", name: "Priya Sharma", overallScore: 88, callCount: 139, trend: [84, 85, 86, 87, 88, 89, 88, 88] },
  { id: "agent-14", name: "Nathan Wright", overallScore: 56, callCount: 76, trend: [62, 60, 58, 57, 55, 54, 56, 56] },
  { id: "agent-15", name: "Olivia Dubois", overallScore: 83, callCount: 128, trend: [80, 81, 82, 83, 84, 83, 82, 83] },
];

export const agentCallsMap: Record<string, Call[]> = {
  "agent-1": agentCalls,
  "agent-2": [
    { id: "call-201", date: "2026-02-28", duration: "3:45", overallScore: 96, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-202", date: "2026-02-27", duration: "5:12", overallScore: 89, politeness: 4, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
    { id: "call-203", date: "2026-02-26", duration: "7:30", overallScore: 91, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  ],
  "agent-3": [
    { id: "call-301", date: "2026-02-28", duration: "6:22", overallScore: 65, politeness: 3, empathy: 2, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "flagged" },
    { id: "call-302", date: "2026-02-27", duration: "8:45", overallScore: 72, politeness: 3, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
    { id: "call-303", date: "2026-02-26", duration: "4:10", overallScore: 80, politeness: 4, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-4": [
    { id: "call-401", date: "2026-02-28", duration: "5:55", overallScore: 83, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
    { id: "call-402", date: "2026-02-27", duration: "4:30", overallScore: 79, politeness: 3, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-5": [
    { id: "call-501", date: "2026-02-28", duration: "3:15", overallScore: 98, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-502", date: "2026-02-27", duration: "4:48", overallScore: 94, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  ],
  "agent-6": [
    { id: "call-601", date: "2026-02-28", duration: "9:30", overallScore: 42, politeness: 2, empathy: 1, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 2, severity: "critical", status: "flagged" },
    { id: "call-602", date: "2026-02-27", duration: "6:15", overallScore: 71, politeness: 3, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "minor", status: "reviewed" },
    { id: "call-603", date: "2026-02-26", duration: "7:45", overallScore: 58, politeness: 2, empathy: 2, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "flagged" },
  ],
  "agent-7": [
    { id: "call-701", date: "2026-02-28", duration: "4:10", overallScore: 93, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-702", date: "2026-02-27", duration: "6:40", overallScore: 88, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-8": [
    { id: "call-801", date: "2026-02-28", duration: "10:15", overallScore: 48, politeness: 2, empathy: 2, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 2, severity: "major", status: "flagged" },
    { id: "call-802", date: "2026-02-27", duration: "7:20", overallScore: 67, politeness: 3, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "minor", status: "reviewed" },
    { id: "call-803", date: "2026-02-26", duration: "5:50", overallScore: 55, politeness: 2, empathy: 2, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "flagged" },
  ],
  "agent-9": [
    { id: "call-901", date: "2026-02-28", duration: "3:55", overallScore: 91, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-902", date: "2026-02-27", duration: "5:25", overallScore: 87, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-10": [
    { id: "call-1001", date: "2026-02-28", duration: "6:05", overallScore: 78, politeness: 3, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
    { id: "call-1002", date: "2026-02-27", duration: "8:10", overallScore: 73, politeness: 3, empathy: 3, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "pending" },
  ],
  "agent-11": [
    { id: "call-1101", date: "2026-02-28", duration: "3:30", overallScore: 97, politeness: 5, empathy: 5, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-1102", date: "2026-02-27", duration: "4:15", overallScore: 92, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
  ],
  "agent-12": [
    { id: "call-1201", date: "2026-02-28", duration: "7:50", overallScore: 66, politeness: 3, empathy: 2, conflict: true, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "flagged" },
    { id: "call-1202", date: "2026-02-27", duration: "5:35", overallScore: 75, politeness: 3, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-13": [
    { id: "call-1301", date: "2026-02-28", duration: "4:45", overallScore: 90, politeness: 5, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 5, severity: "minor", status: "reviewed" },
    { id: "call-1302", date: "2026-02-27", duration: "6:00", overallScore: 85, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
  "agent-14": [
    { id: "call-1401", date: "2026-02-28", duration: "11:20", overallScore: 38, politeness: 1, empathy: 1, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 2, severity: "critical", status: "flagged" },
    { id: "call-1402", date: "2026-02-27", duration: "8:30", overallScore: 52, politeness: 2, empathy: 2, conflict: true, resolution: false, scriptCompliance: false, factualAccuracy: 3, severity: "major", status: "flagged" },
    { id: "call-1403", date: "2026-02-26", duration: "6:45", overallScore: 64, politeness: 3, empathy: 2, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 3, severity: "moderate", status: "reviewed" },
  ],
  "agent-15": [
    { id: "call-1501", date: "2026-02-28", duration: "4:20", overallScore: 85, politeness: 4, empathy: 4, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
    { id: "call-1502", date: "2026-02-27", duration: "5:50", overallScore: 82, politeness: 4, empathy: 3, conflict: false, resolution: true, scriptCompliance: true, factualAccuracy: 4, severity: "minor", status: "reviewed" },
  ],
};

export const trendData = [
  { name: "Week 1", overall: 82, politeness: 4.1, empathy: 3.8 },
  { name: "Week 2", overall: 84, politeness: 4.2, empathy: 3.9 },
  { name: "Week 3", overall: 79, politeness: 3.8, empathy: 3.6 },
  { name: "Week 4", overall: 86, politeness: 4.3, empathy: 4.1 },
  { name: "Week 5", overall: 88, politeness: 4.5, empathy: 4.2 },
  { name: "Week 6", overall: 85, politeness: 4.2, empathy: 4.0 },
  { name: "Week 7", overall: 90, politeness: 4.6, empathy: 4.3 },
  { name: "Week 8", overall: 87, politeness: 4.4, empathy: 4.1 },
];

export const callDetail: CallDetail = {
  id: "call-003",
  date: "2026-02-27",
  duration: "8:47",
  agentName: "Sarah Mitchell",
  customerName: "Alex Thompson",
  overallScore: 45,
  scores: {
    scriptCompliance: {
      compliant: false,
      confidence: 82,
      evidence: "Agent failed to verify customer identity before accessing account. Skipped de-escalation protocol when conflict arose",
    },
    factualAccuracy: {
      score: 3,
      confidence: 75,
      evidence: "Agent stated charges were for different billing periods, which may be incorrect. Refund timeline of 5-7 days appears standard",
    },
    politeness: {
      score: 2,
      confidence: 89,
      evidence: "\"Look, I already told you this isn't going to work\" — Agent used dismissive tone at 2:34",
    },
    empathy: {
      score: 2,
      confidence: 91,
      evidence: "\"I understand that's frustrating\" was said once but not followed with supportive action",
    },
    conflict: {
      detected: true,
      confidence: 94,
      evidence: "Raised voices detected at 3:15–4:02. Customer said \"This is unacceptable\" and agent responded defensively",
    },
    resolution: {
      resolved: false,
      confidence: 87,
      evidence: "Call ended without agreed-upon next steps. Customer expressed ongoing dissatisfaction at 8:30",
    },
    severity: {
      level: "major",
      confidence: 90,
      evidence: "Dismissive agent behavior combined with unresolved billing issue and active conflict. Customer threatened cancellation",
    },
  },
  flagForReview: true,
  transcript: [
    { speaker: "agent", timestamp: "0:00", text: "Thank you for calling TechSupport, this is Sarah. How can I help you today?", emotion: "neutral" },
    { speaker: "customer", timestamp: "0:05", text: "Hi, I've been trying to get my account issue resolved for three days now. I keep getting transferred around.", emotion: "frustration" },
    { speaker: "agent", timestamp: "0:15", text: "I'm sorry to hear that. Let me pull up your account. Can I get your account number?", emotion: "neutral" },
    { speaker: "customer", timestamp: "0:22", text: "It's 4482-9917. I've given this number five times already.", emotion: "frustration" },
    { speaker: "agent", timestamp: "0:30", text: "Okay, I see your account. So you're having a billing issue?", emotion: "neutral" },
    { speaker: "customer", timestamp: "0:38", text: "Yes! I was charged twice for my subscription last month, and no one has fixed it. I need a refund.", emotion: "anger" },
    { speaker: "agent", timestamp: "0:48", text: "I understand that's frustrating. Let me look into the charges.", emotion: "neutral" },
    { speaker: "customer", timestamp: "1:20", text: "Well? Can you see the duplicate charge?", emotion: "frustration" },
    { speaker: "agent", timestamp: "1:28", text: "I can see two charges, but they appear to be for different billing periods.", emotion: "neutral" },
    { speaker: "customer", timestamp: "1:35", text: "That's impossible. I only have one subscription. Check again.", emotion: "anger" },
    { speaker: "agent", timestamp: "1:45", text: "Look, I already told you this isn't going to work if you keep interrupting me.", emotion: "frustration" },
    { speaker: "customer", timestamp: "1:52", text: "Excuse me? I'm the customer here. I've been waiting three days for this!", emotion: "anger" },
    { speaker: "agent", timestamp: "2:00", text: "I understand, but I need time to review the system.", emotion: "neutral" },
    { speaker: "customer", timestamp: "2:45", text: "This is unacceptable. I want to speak to a manager.", emotion: "anger" },
    { speaker: "agent", timestamp: "2:52", text: "A manager isn't available right now. I'm trying to help you.", emotion: "frustration" },
    { speaker: "customer", timestamp: "3:00", text: "You're not helping. You're arguing with me.", emotion: "anger" },
    { speaker: "agent", timestamp: "3:10", text: "I'm not arguing. Let me see what I can do about the refund.", emotion: "neutral" },
    { speaker: "customer", timestamp: "5:00", text: "So what's the verdict?", emotion: "frustration" },
    { speaker: "agent", timestamp: "5:08", text: "I've submitted a request, but refunds take 5-7 business days to process.", emotion: "neutral" },
    { speaker: "customer", timestamp: "5:15", text: "Another week? I've already waited three days!", emotion: "anger" },
    { speaker: "agent", timestamp: "5:22", text: "That's our standard processing time. There's nothing I can do to speed it up.", emotion: "neutral" },
    { speaker: "customer", timestamp: "8:30", text: "Fine. But if this isn't resolved by next week, I'm canceling my account entirely.", emotion: "anger" },
    { speaker: "agent", timestamp: "8:38", text: "I understand. Is there anything else I can help with?", emotion: "neutral" },
    { speaker: "customer", timestamp: "8:42", text: "No. Goodbye.", emotion: "frustration" },
  ],
  aiReport: `## Call Quality Assessment Report

### Executive Summary
This call exhibited significant quality concerns requiring immediate supervisory review. The interaction between Agent Sarah Mitchell and customer Alex Thompson regarding a duplicate billing charge escalated into a conflict situation, resulting in an unresolved outcome.

### Key Findings

**Communication Breakdown**
The agent's initial greeting and account lookup were professional. However, at the 1:45 mark, the agent's response ("Look, I already told you this isn't going to work if you keep interrupting me") represented a critical breakdown in professional communication standards. This statement was perceived as confrontational by the customer and escalated the situation.

**Empathy Deficit**
While the agent used the phrase "I understand that's frustrating" early in the call, this was not supported by empathetic behavior throughout the rest of the interaction. The agent failed to acknowledge the customer's three-day wait or validate their frustration about being transferred multiple times.

**Conflict Escalation**
The call escalated from mild frustration to active conflict between 1:45 and 3:10. The agent's defensive posture contributed to the escalation rather than de-escalating the situation. Best practice would have been to acknowledge the customer's feelings and offer concrete next steps.

**Resolution Failure**
While a refund request was submitted, the call ended without clear confirmation of resolution timeline, no follow-up commitment was made, and the customer explicitly threatened account cancellation. This represents a retention risk.

### Recommendations
1. **Immediate**: Schedule a coaching session with Agent Mitchell focusing on de-escalation techniques
2. **Short-term**: Review the refund request to ensure it is processed within the stated timeline
3. **Follow-up**: Proactive outreach to the customer within 48 hours to confirm refund status
4. **Training**: Enroll agent in advanced conflict resolution and empathy training module`,
};
