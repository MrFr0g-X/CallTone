"""
Demo data for the CallTone API.

Serves realistic mock data for dashboards and REAL data from LAYER 1
JSON for call detail views. Used by main.py endpoints.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
L1_JSON_DIR = REPO_ROOT / "Test_audio" / "bad_cs_results"

# ---------------------------------------------------------------------------
# Agents (ported from calltone-UI/src/data/mockData.ts)
# ---------------------------------------------------------------------------
AGENTS = [
    {"id": "agent-1", "name": "Sarah Mitchell", "overallScore": 87, "callCount": 142, "trend": [82, 84, 83, 86, 88, 87, 89, 87]},
    {"id": "agent-2", "name": "David Chen", "overallScore": 92, "callCount": 158, "trend": [88, 89, 90, 91, 93, 92, 91, 92]},
    {"id": "agent-3", "name": "Emily Watson", "overallScore": 74, "callCount": 123, "trend": [78, 76, 75, 72, 73, 74, 75, 74]},
    {"id": "agent-4", "name": "Michael Torres", "overallScore": 81, "callCount": 136, "trend": [79, 80, 78, 82, 83, 81, 80, 81]},
    {"id": "agent-5", "name": "Jessica Kim", "overallScore": 95, "callCount": 167, "trend": [91, 92, 93, 94, 95, 96, 95, 95]},
    {"id": "agent-6", "name": "Robert Brown", "overallScore": 68, "callCount": 98, "trend": [72, 70, 69, 67, 66, 68, 69, 68]},
    {"id": "agent-7", "name": "Amanda Garcia", "overallScore": 91, "callCount": 151, "trend": [87, 88, 89, 90, 91, 92, 91, 91]},
    {"id": "agent-8", "name": "Kevin Patel", "overallScore": 63, "callCount": 87, "trend": [68, 66, 65, 63, 62, 61, 63, 63]},
    {"id": "agent-9", "name": "Lisa Nakamura", "overallScore": 89, "callCount": 144, "trend": [85, 86, 87, 88, 89, 90, 89, 89]},
    {"id": "agent-10", "name": "Carlos Rivera", "overallScore": 77, "callCount": 112, "trend": [74, 75, 76, 78, 77, 76, 77, 77]},
    {"id": "agent-11", "name": "Hannah Osei", "overallScore": 94, "callCount": 163, "trend": [90, 91, 92, 93, 94, 95, 94, 94]},
    {"id": "agent-12", "name": "Tyler Jackson", "overallScore": 72, "callCount": 105, "trend": [75, 74, 73, 71, 70, 72, 73, 72]},
    {"id": "agent-13", "name": "Priya Sharma", "overallScore": 88, "callCount": 139, "trend": [84, 85, 86, 87, 88, 89, 88, 88]},
    {"id": "agent-14", "name": "Nathan Wright", "overallScore": 56, "callCount": 76, "trend": [62, 60, 58, 57, 55, 54, 56, 56]},
    {"id": "agent-15", "name": "Olivia Dubois", "overallScore": 83, "callCount": 128, "trend": [80, 81, 82, 83, 84, 83, 82, 83]},
]

# ---------------------------------------------------------------------------
# Trend data for agent dashboard chart
# ---------------------------------------------------------------------------
TREND_DATA = [
    {"name": "Week 1", "overall": 82, "politeness": 4.1, "empathy": 3.8},
    {"name": "Week 2", "overall": 84, "politeness": 4.2, "empathy": 3.9},
    {"name": "Week 3", "overall": 79, "politeness": 3.8, "empathy": 3.6},
    {"name": "Week 4", "overall": 86, "politeness": 4.3, "empathy": 4.1},
    {"name": "Week 5", "overall": 88, "politeness": 4.5, "empathy": 4.2},
    {"name": "Week 6", "overall": 85, "politeness": 4.2, "empathy": 4.0},
    {"name": "Week 7", "overall": 90, "politeness": 4.6, "empathy": 4.3},
    {"name": "Week 8", "overall": 87, "politeness": 4.4, "empathy": 4.1},
]

# ---------------------------------------------------------------------------
# Real call from L1 JSON — the "call-bad-cs" entry
# ---------------------------------------------------------------------------
REAL_CALL_ENTRY = {
    "id": "call-bad-cs", "date": "2026-02-28", "duration": "1:31",
    "overallScore": 38, "politeness": 2, "empathy": 1,
    "conflict": True, "resolution": True,
    "scriptCompliance": False, "factualAccuracy": 3, "severity": "major",
    "status": "flagged",
    "agentId": "agent-1",
}

# ---------------------------------------------------------------------------
# Calls per agent (agent-1 includes the real call)
# ---------------------------------------------------------------------------
AGENT_CALLS = [
    REAL_CALL_ENTRY,
    {"id": "call-001", "date": "2026-02-28", "duration": "4:32", "overallScore": 92, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    {"id": "call-002", "date": "2026-02-27", "duration": "6:15", "overallScore": 78, "politeness": 3, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    {"id": "call-003", "date": "2026-02-27", "duration": "8:47", "overallScore": 45, "politeness": 2, "empathy": 2, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 3, "severity": "major", "status": "flagged"},
    {"id": "call-004", "date": "2026-02-26", "duration": "3:21", "overallScore": 88, "politeness": 4, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    {"id": "call-005", "date": "2026-02-26", "duration": "5:58", "overallScore": 95, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    {"id": "call-006", "date": "2026-02-25", "duration": "7:12", "overallScore": 62, "politeness": 3, "empathy": 2, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "flagged"},
    {"id": "call-007", "date": "2026-02-25", "duration": "2:45", "overallScore": 85, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    {"id": "call-008", "date": "2026-02-24", "duration": "9:03", "overallScore": 38, "politeness": 1, "empathy": 2, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 2, "severity": "critical", "status": "flagged"},
    {"id": "call-009", "date": "2026-02-24", "duration": "4:18", "overallScore": 91, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    {"id": "call-010", "date": "2026-02-23", "duration": "5:30", "overallScore": 82, "politeness": 4, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "pending"},
]

AGENT_CALLS_MAP = {
    "agent-1": AGENT_CALLS,
    "agent-2": [
        {"id": "call-201", "date": "2026-02-28", "duration": "3:45", "overallScore": 96, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-202", "date": "2026-02-27", "duration": "5:12", "overallScore": 89, "politeness": 4, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
        {"id": "call-203", "date": "2026-02-26", "duration": "7:30", "overallScore": 91, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    ],
    "agent-3": [
        {"id": "call-301", "date": "2026-02-28", "duration": "6:22", "overallScore": 65, "politeness": 3, "empathy": 2, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "flagged"},
        {"id": "call-302", "date": "2026-02-27", "duration": "8:45", "overallScore": 72, "politeness": 3, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
        {"id": "call-303", "date": "2026-02-26", "duration": "4:10", "overallScore": 80, "politeness": 4, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-6": [
        {"id": "call-601", "date": "2026-02-28", "duration": "9:30", "overallScore": 42, "politeness": 2, "empathy": 1, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 2, "severity": "critical", "status": "flagged"},
        {"id": "call-602", "date": "2026-02-27", "duration": "6:15", "overallScore": 71, "politeness": 3, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "minor", "status": "reviewed"},
        {"id": "call-603", "date": "2026-02-26", "duration": "7:45", "overallScore": 58, "politeness": 2, "empathy": 2, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "flagged"},
    ],
    "agent-8": [
        {"id": "call-801", "date": "2026-02-28", "duration": "10:15", "overallScore": 48, "politeness": 2, "empathy": 2, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 2, "severity": "major", "status": "flagged"},
        {"id": "call-802", "date": "2026-02-27", "duration": "7:20", "overallScore": 67, "politeness": 3, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "minor", "status": "reviewed"},
        {"id": "call-803", "date": "2026-02-26", "duration": "5:50", "overallScore": 55, "politeness": 2, "empathy": 2, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "flagged"},
    ],
    "agent-4": [
        {"id": "call-401", "date": "2026-02-28", "duration": "5:55", "overallScore": 83, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
        {"id": "call-402", "date": "2026-02-27", "duration": "4:30", "overallScore": 79, "politeness": 3, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-5": [
        {"id": "call-501", "date": "2026-02-28", "duration": "3:15", "overallScore": 98, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-502", "date": "2026-02-27", "duration": "4:48", "overallScore": 94, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    ],
    "agent-7": [
        {"id": "call-701", "date": "2026-02-28", "duration": "4:10", "overallScore": 93, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-702", "date": "2026-02-27", "duration": "6:40", "overallScore": 88, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-9": [
        {"id": "call-901", "date": "2026-02-28", "duration": "3:55", "overallScore": 91, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-902", "date": "2026-02-27", "duration": "5:25", "overallScore": 87, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-10": [
        {"id": "call-1001", "date": "2026-02-28", "duration": "6:05", "overallScore": 78, "politeness": 3, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
        {"id": "call-1002", "date": "2026-02-27", "duration": "8:10", "overallScore": 73, "politeness": 3, "empathy": 3, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "pending"},
    ],
    "agent-11": [
        {"id": "call-1101", "date": "2026-02-28", "duration": "3:30", "overallScore": 97, "politeness": 5, "empathy": 5, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-1102", "date": "2026-02-27", "duration": "4:15", "overallScore": 92, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
    ],
    "agent-12": [
        {"id": "call-1201", "date": "2026-02-28", "duration": "7:50", "overallScore": 66, "politeness": 3, "empathy": 2, "conflict": True, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "flagged"},
        {"id": "call-1202", "date": "2026-02-27", "duration": "5:35", "overallScore": 75, "politeness": 3, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-13": [
        {"id": "call-1301", "date": "2026-02-28", "duration": "4:45", "overallScore": 90, "politeness": 5, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 5, "severity": "minor", "status": "reviewed"},
        {"id": "call-1302", "date": "2026-02-27", "duration": "6:00", "overallScore": 85, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
    "agent-14": [
        {"id": "call-1401", "date": "2026-02-28", "duration": "11:20", "overallScore": 38, "politeness": 1, "empathy": 1, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 2, "severity": "critical", "status": "flagged"},
        {"id": "call-1402", "date": "2026-02-27", "duration": "8:30", "overallScore": 52, "politeness": 2, "empathy": 2, "conflict": True, "resolution": False, "scriptCompliance": False, "factualAccuracy": 3, "severity": "major", "status": "flagged"},
        {"id": "call-1403", "date": "2026-02-26", "duration": "6:45", "overallScore": 64, "politeness": 3, "empathy": 2, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 3, "severity": "moderate", "status": "reviewed"},
    ],
    "agent-15": [
        {"id": "call-1501", "date": "2026-02-28", "duration": "4:20", "overallScore": 85, "politeness": 4, "empathy": 4, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
        {"id": "call-1502", "date": "2026-02-27", "duration": "5:50", "overallScore": 82, "politeness": 4, "empathy": 3, "conflict": False, "resolution": True, "scriptCompliance": True, "factualAccuracy": 4, "severity": "minor", "status": "reviewed"},
    ],
}


# ---------------------------------------------------------------------------
# L1 JSON → CallDetail transformer
# ---------------------------------------------------------------------------
EMOTION_MAP = {
    "anger": "anger",
    "joy": "joy",
    "neutral": "neutral",
    "sadness": "frustration",
    "fear": "frustration",
    "disgust": "frustration",
}


def _load_real_call_detail() -> dict:
    """Load the real vacuum-cleaner call from L1 JSON and map to UI format."""
    l1_path = L1_JSON_DIR / "bad_cs_denoised_diarized_with_emotions.json"
    if not l1_path.exists():
        return None

    with open(l1_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    role_map = {"SPEAKER_A": "agent", "SPEAKER_B": "customer"}

    transcript = []
    for seg in data.get("transcript", []):
        start = seg.get("start", 0)
        minutes = int(start // 60)
        seconds = int(start % 60)

        raw_emotion = seg.get("audio_emotion", "neutral")
        emotion = EMOTION_MAP.get(raw_emotion, "neutral")
        if "SATISFIED" in seg.get("signals", []):
            emotion = "satisfaction"

        text = seg.get("text", "").strip()
        if not text:
            continue

        transcript.append({
            "speaker": role_map.get(seg.get("speaker", ""), "agent"),
            "timestamp": f"{minutes}:{seconds:02d}",
            "text": text,
            "emotion": emotion,
        })

    dur = data.get("call_metadata", {}).get("duration_seconds", 0)
    dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}"

    return {
        "id": "call-bad-cs",
        "date": "2026-02-28",
        "duration": dur_str,
        "agentName": "Tanya Williams",
        "customerName": "John Carter",
        "overallScore": 38,
        "scores": {
            "scriptCompliance": {
                "compliant": False,
                "confidence": 85,
                "evidence": (
                    "Agent skipped empathetic greeting and customer verification. "
                    "Jumped directly into troubleshooting checklist without following standard protocol"
                ),
            },
            "factualAccuracy": {
                "score": 3,
                "confidence": 78,
                "evidence": (
                    "Agent provided correct troubleshooting steps (check bag, check underneath). "
                    "No factual errors detected, but information was delivered without context"
                ),
            },
            "politeness": {
                "score": 2,
                "confidence": 87,
                "evidence": (
                    '"Did you check underneath..." — Agent jumped straight to '
                    "troubleshooting without empathy or greeting warmth"
                ),
            },
            "empathy": {
                "score": 1,
                "confidence": 91,
                "evidence": (
                    "Customer showed sustained anger (>90% confidence). "
                    'Agent never acknowledged frustration: "I just said that" went unaddressed'
                ),
            },
            "conflict": {
                "detected": True,
                "confidence": 94,
                "evidence": (
                    "Customer anger detected at 0.88-0.95 confidence across 20+ utterances. "
                    "Progressive escalation throughout the call"
                ),
            },
            "resolution": {
                "resolved": True,
                "confidence": 83,
                "evidence": (
                    '"Completely full." — Vacuum bag was the root cause. '
                    "Agent correctly identified the fix via bag question"
                ),
            },
            "severity": {
                "level": "major",
                "confidence": 88,
                "evidence": (
                    "Significant empathy deficit (1/5) combined with sustained conflict and "
                    "script non-compliance. Customer experience severely impacted despite resolution"
                ),
            },
        },
        "flagForReview": True,
        "transcript": transcript,
        "aiReport": """## Call Quality Assessment Report

### Executive Summary
This call scored **38/100** and has been **flagged for supervisor review**. Agent Tanya handled a vacuum cleaner malfunction complaint from an increasingly frustrated customer. While the issue was ultimately resolved (full vacuum bag), the agent demonstrated critical empathy deficits throughout the 1:31 interaction. Overall severity classified as **Major**.

### Key Findings

**Script Compliance (Non-Compliant)**
Agent skipped the empathetic greeting protocol and customer identity verification. Jumped directly into a rapid-fire troubleshooting checklist without following the standard call opening procedure.

**Factual Accuracy (Score: 3/5)**
The troubleshooting steps provided were technically correct — checking underneath the vacuum and asking about the bag were valid diagnostic questions. No factual errors or contradictions detected, but information lacked context.

**Politeness & Tone (Score: 2/5)**
The agent opened professionally ("All pro vacuums, this is Tanya") but immediately shifted to a rapid-fire troubleshooting checklist without acknowledging the customer's emotional state. Questions were asked in quick succession without pausing for the customer's full responses.

**Empathy Deficit (Score: 1/5)**
Audio emotion analysis detected sustained anger at **0.88–0.95 confidence** across 20+ customer utterances. The agent never used a single acknowledgment phrase ("I understand," "That must be frustrating," "I'm sorry to hear that"). When the customer said "I just said that" at 1:24, indicating they felt unheard, the agent moved on without response.

**Conflict Detection (Detected)**
Active conflict signals were present throughout the call. The customer's tone was angry from utterance 2 onward, with anger confidence exceeding 0.90 in 15 of 20 customer segments. No de-escalation was attempted.

**Resolution (Resolved)**
Despite poor delivery, the agent correctly diagnosed the problem. The vacuum bag was completely full. The customer confirmed this finding. This prevented what could have escalated to a formal complaint or return.

**Overall Severity: Major**
The combination of script non-compliance, critical empathy deficit (1/5), and sustained unaddressed conflict constitutes a major service failure. The issue was resolved, which prevented escalation to critical severity.

### Recommendations
1. **Immediate**: Empathy scripting — require agents to verbally acknowledge customer emotion before troubleshooting
2. **Coaching**: Tanya should review call recordings where agents demonstrate active listening
3. **Script compliance**: Reinforce standard call opening protocol (greeting, verification, empathy)
4. **Process**: "Is the bag full?" should be question #1, not #4, in the vacuum troubleshooting script
5. **Follow-up**: Customer satisfaction survey recommended within 48 hours""",
    }


# Pre-load real call detail at module init
_REAL_CALL_DETAIL = _load_real_call_detail()

# Mock call detail for call-003 (matching UI mockData)
_MOCK_CALL_DETAIL = {
    "id": "call-003",
    "date": "2026-02-27",
    "duration": "8:47",
    "agentName": "Sarah Mitchell",
    "customerName": "Alex Thompson",
    "overallScore": 45,
    "scores": {
        "scriptCompliance": {"compliant": False, "confidence": 82, "evidence": "Agent failed to verify customer identity before accessing account. Skipped de-escalation protocol when conflict arose"},
        "factualAccuracy": {"score": 3, "confidence": 75, "evidence": "Agent stated charges were for different billing periods, which may be incorrect. Refund timeline of 5-7 days appears standard"},
        "politeness": {"score": 2, "confidence": 89, "evidence": '"Look, I already told you this isn\'t going to work" — Agent used dismissive tone at 2:34'},
        "empathy": {"score": 2, "confidence": 91, "evidence": '"I understand that\'s frustrating" was said once but not followed with supportive action'},
        "conflict": {"detected": True, "confidence": 94, "evidence": 'Raised voices detected at 3:15-4:02. Customer said "This is unacceptable" and agent responded defensively'},
        "resolution": {"resolved": False, "confidence": 87, "evidence": "Call ended without agreed-upon next steps. Customer expressed ongoing dissatisfaction at 8:30"},
        "severity": {"level": "major", "confidence": 90, "evidence": "Dismissive agent behavior combined with unresolved billing issue and active conflict. Customer threatened cancellation"},
    },
    "flagForReview": True,
    "transcript": [
        {"speaker": "agent", "timestamp": "0:00", "text": "Thank you for calling TechSupport, this is Sarah. How can I help you today?", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "0:05", "text": "Hi, I've been trying to get my account issue resolved for three days now.", "emotion": "frustration"},
        {"speaker": "agent", "timestamp": "0:15", "text": "I'm sorry to hear that. Let me pull up your account.", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "0:22", "text": "It's 4482-9917. I've given this number five times already.", "emotion": "frustration"},
        {"speaker": "agent", "timestamp": "0:30", "text": "Okay, I see your account. So you're having a billing issue?", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "0:38", "text": "Yes! I was charged twice for my subscription last month. I need a refund.", "emotion": "anger"},
        {"speaker": "agent", "timestamp": "0:48", "text": "I understand that's frustrating. Let me look into the charges.", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "1:20", "text": "Well? Can you see the duplicate charge?", "emotion": "frustration"},
        {"speaker": "agent", "timestamp": "1:28", "text": "I can see two charges, but they appear to be for different billing periods.", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "1:35", "text": "That's impossible. I only have one subscription. Check again.", "emotion": "anger"},
        {"speaker": "agent", "timestamp": "1:45", "text": "Look, I already told you this isn't going to work if you keep interrupting me.", "emotion": "frustration"},
        {"speaker": "customer", "timestamp": "1:52", "text": "Excuse me? I'm the customer here. I've been waiting three days!", "emotion": "anger"},
        {"speaker": "customer", "timestamp": "2:45", "text": "This is unacceptable. I want to speak to a manager.", "emotion": "anger"},
        {"speaker": "agent", "timestamp": "5:08", "text": "I've submitted a request, but refunds take 5-7 business days.", "emotion": "neutral"},
        {"speaker": "customer", "timestamp": "8:30", "text": "Fine. But if this isn't resolved by next week, I'm canceling entirely.", "emotion": "anger"},
        {"speaker": "agent", "timestamp": "8:38", "text": "I understand. Is there anything else I can help with?", "emotion": "neutral"},
    ],
    "aiReport": "## Call Quality Assessment\n\nThis call scored 45/100 and has been flagged for review. Agent exhibited dismissive behavior at 1:45 mark. Conflict escalated without de-escalation attempts. Resolution pending (refund submitted but not confirmed).\n\n### Recommendations\n1. Schedule coaching session on de-escalation\n2. Follow up on refund processing\n3. Proactive customer outreach within 48 hours",
}


def get_call_detail(call_id: str) -> dict | None:
    """Return call detail by ID. Real data for call-bad-cs, mock for call-003."""
    if call_id == "call-bad-cs" and _REAL_CALL_DETAIL:
        return _REAL_CALL_DETAIL
    if call_id == "call-003":
        return _MOCK_CALL_DETAIL
    return None
