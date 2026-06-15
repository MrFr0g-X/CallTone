"""Read a QA call-detail JSON from stdin and print a pipeline-completeness summary."""
import sys, json

d = json.load(sys.stdin)
r = d.get("report") or {}
print("=== REPORT ===")
print("overall:", r.get("overallScore"), "grade:", r.get("grade"), "severity:", r.get("severity"))
dims = r.get("dimensions") or []
for dim in dims:
    ev = dim.get("evidence") or dim.get("evidenceQuotes") or []
    name = dim.get("name")
    print("  - {0}: score={1} conf={2} evidence={3}".format(
        name, dim.get("score"), dim.get("confidence"), len(ev)))
ds = r.get("dimensionScores") or {}
dr = r.get("dimensionReports") or {}
print("dimensionScores keys:", list(ds.keys()))
for k in ("script_compliance", "factual_accuracy"):
    print("  [{0}] score={1} report={2}".format(k, ds.get(k), str(dr.get(k))[:140]))
print("flagForReview:", r.get("flagForReview"), "reason:", str(r.get("flagReason"))[:80])
print("summary:", str((r.get("reportJson") or r.get("report_json") or {}).get("summary") or r.get("summary"))[:160])

t = d.get("transcript") or {}
turns = t.get("speakerTurns") or t.get("turns") or []
roles = sorted({str(x.get("role") or x.get("speaker")) for x in turns})
emos = sorted({str(x.get("audioEmotion") or x.get("audio_emotion")) for x in turns})
sigs = sorted({s for x in turns for s in (x.get("signals") or [])})
print("=== LAYER1 ===")
print("turns:", len(turns), "roles:", roles)
print("emotions:", emos)
print("signals:", sigs)
print("asr:", t.get("asrEngine") or t.get("asr_engine"), "der:", t.get("der"), "wer:", t.get("wer"))
