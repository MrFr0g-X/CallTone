"""
Context Graph Visualizer — generates an Obsidian-style interactive HTML
visualization of a ContextGraph JSON file.

Usage:
    python visualize_graph.py
    python visualize_graph.py --graph path/to/graph.json --output viz.html
    python visualize_graph.py --company metroboost   (builds graph fresh from context)
"""

import json
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Convert ContextGraph JSON → D3-compatible dict
# ---------------------------------------------------------------------------

def convert_to_d3(graph_data: dict) -> dict:
    nodes, links = [], []
    for node_id, n in graph_data.get("nodes", {}).items():
        nodes.append({
            "id":            node_id,
            "label":         n.get("content", "")[:60] + ("…" if len(n.get("content","")) > 60 else ""),
            "content":       n.get("content", ""),
            "category":      n.get("category", "unknown"),
            "topic":         n.get("topic", ""),
            "node_type":     n.get("node_type", ""),
            "is_hub":        n.get("is_hub", False),
            "semantic_tags": n.get("semantic_tags", []),
            "active":        n.get("active", True),
            "version":       n.get("version", 1),
        })
    for e in graph_data.get("edges", []):
        src, tgt = e.get("source_id"), e.get("target_id")
        if src and tgt:
            links.append({
                "source":   src,
                "target":   tgt,
                "relation": e.get("relation", "related_to"),
                "note":     e.get("note", ""),
            })
    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Context Graph — {title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    overflow: hidden;
  }}

  #graph {{ width: 100vw; height: 100vh; }}

  /* ── Tooltip ── */
  #tooltip {{
    position: fixed;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 14px;
    max-width: 320px;
    pointer-events: none;
    opacity: 0;
    transition: opacity .15s;
    z-index: 100;
    font-size: 12px;
    line-height: 1.6;
    box-shadow: 0 8px 24px rgba(0,0,0,.5);
  }}
  #tooltip.visible {{ opacity: 1; }}
  #tooltip .tt-type   {{ color: #8b949e; font-size: 10px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px; }}
  #tooltip .tt-content{{ color: #e6edf3; font-weight: 500; margin-bottom: 8px; }}
  #tooltip .tt-tags   {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  #tooltip .tt-tag    {{ background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; font-size: 10px; color: #58a6ff; }}
  #tooltip .tt-refs   {{ margin-top: 6px; color: #8b949e; font-size: 11px; }}

  /* ── Legend ── */
  #legend {{
    position: fixed;
    bottom: 20px;
    left: 20px;
    background: rgba(22,27,34,.9);
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 12px;
    backdrop-filter: blur(8px);
    z-index: 50;
  }}
  #legend h4 {{ color: #8b949e; font-size: 10px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
  .legend-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 5px; cursor: pointer; user-select: none; }}
  .legend-row:last-child {{ margin-bottom: 0; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .legend-row.dimmed {{ opacity: .35; }}
  .legend-row.dimmed .legend-dot {{ filter: grayscale(1); }}

  /* ── Edge legend ── */
  #edge-legend {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: rgba(22,27,34,.9);
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 12px;
    backdrop-filter: blur(8px);
    z-index: 50;
  }}
  #edge-legend h4 {{ color: #8b949e; font-size: 10px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }}
  .edge-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }}
  .edge-swatch {{ width: 28px; height: 2px; flex-shrink: 0; }}

  /* ── Controls ── */
  #controls {{
    position: fixed;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 8px;
    z-index: 50;
  }}
  #search {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    padding: 6px 12px;
    font-size: 13px;
    width: 260px;
    outline: none;
  }}
  #search:focus {{ border-color: #58a6ff; }}
  #search::placeholder {{ color: #484f58; }}
  button.ctrl {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #8b949e;
    padding: 6px 12px;
    font-size: 12px;
    cursor: pointer;
  }}
  button.ctrl:hover {{ border-color: #58a6ff; color: #58a6ff; }}

  /* ── Stats ── */
  #stats {{
    position: fixed;
    top: 16px;
    right: 20px;
    color: #484f58;
    font-size: 11px;
    text-align: right;
    z-index: 50;
    line-height: 1.8;
  }}

  /* ── Links ── */
  .link {{ fill: none; }}
  .link.part_of    {{ stroke: #21262d; stroke-width: 1; }}
  .link.related_to {{ stroke-width: 1.5; opacity: .7; }}
  .link.supersedes {{ stroke: #f85149; stroke-width: 2; stroke-dasharray: 5,3; }}
  .link.same_concept{{ stroke: #e3b341; stroke-width: 1.5; stroke-dasharray: 2,3; }}

  /* ── Nodes ── */
  .node {{ cursor: pointer; }}
  .node circle {{ transition: r .1s; }}
  .node.hub circle {{ filter: drop-shadow(0 0 6px currentColor); }}
  .node.faded {{ opacity: .12; }}
  .node.faded.hub {{ opacity: .2; }}
  .node-label {{
    font-size: 9px;
    fill: #8b949e;
    pointer-events: none;
    text-anchor: middle;
    dominant-baseline: hanging;
  }}
  .node.hub .node-label {{
    font-size: 11px;
    fill: #e6edf3;
    font-weight: 600;
  }}
</style>
</head>
<body>

<div id="graph"></div>
<div id="tooltip"></div>

<div id="controls">
  <input id="search" type="text" placeholder="Search nodes…"/>
  <button class="ctrl" onclick="resetView()">⊙ Reset</button>
  <button class="ctrl" onclick="toggleLabels()">Aa Labels</button>
</div>

<div id="stats"></div>
<div id="legend"><h4>Categories</h4></div>
<div id="edge-legend">
  <h4>Edges</h4>
  <div class="edge-row"><div class="edge-swatch" style="background:#30363d"></div><span>part of</span></div>
  <div class="edge-row"><div class="edge-swatch" style="background:#58a6ff;opacity:.7"></div><span>related to</span></div>
  <div class="edge-row"><div class="edge-swatch" style="background:#f85149;border-top:2px dashed #f85149;height:0"></div><span>supersedes</span></div>
  <div class="edge-row"><div class="edge-swatch" style="border-top:2px dotted #e3b341;height:0"></div><span>same concept</span></div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const GRAPH = {graph_json};

const CATEGORY_COLORS = {{
  "script_compliance":  "#4a9af4",
  "factual_accuracy":   "#e8a838",
  "politeness_tone":    "#9b59b6",
  "empathy":            "#2ecc71",
  "conflict_detection": "#e74c3c",
  "issue_resolution":   "#f39c12",
  "unknown":            "#555",
}};

const CATEGORY_LABELS = {{
  "script_compliance":  "Script Compliance",
  "factual_accuracy":   "Factual Accuracy",
  "politeness_tone":    "Politeness & Tone",
  "empathy":            "Empathy",
  "conflict_detection": "Conflict Detection",
  "issue_resolution":   "Issue Resolution",
}};

const LINK_COLORS = {{
  "part_of":      "#21262d",
  "related_to":   "#58a6ff",
  "supersedes":   "#f85149",
  "same_concept": "#e3b341",
}};

let showLabels = true;
let activeCategories = new Set(Object.keys(CATEGORY_COLORS));

// ── Build index ────────────────────────────────────────────────────────────
const nodeById = {{}};
GRAPH.nodes.forEach(n => nodeById[n.id] = n);

// ── SVG setup ──────────────────────────────────────────────────────────────
const W = window.innerWidth, H = window.innerHeight;
const svg = d3.select("#graph").append("svg")
    .attr("width", W).attr("height", H);

const defs = svg.append("defs");

// Glow filter for hub nodes
const glow = defs.append("filter").attr("id","glow").attr("x","-50%").attr("y","-50%").attr("width","200%").attr("height","200%");
glow.append("feGaussianBlur").attr("stdDeviation","4").attr("result","blur");
const feMerge = glow.append("feMerge");
feMerge.append("feMergeNode").attr("in","blur");
feMerge.append("feMergeNode").attr("in","SourceGraphic");

const g = svg.append("g");

const zoom = d3.zoom().scaleExtent([0.05, 6])
    .on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);

// ── Simulation ─────────────────────────────────────────────────────────────
const simulation = d3.forceSimulation(GRAPH.nodes)
  .force("link", d3.forceLink(GRAPH.links)
      .id(d => d.id)
      .distance(d => d.relation === "part_of" ? 80 : d.relation === "related_to" ? 160 : 120)
      .strength(d => d.relation === "part_of" ? 0.6 : 0.3))
  .force("charge", d3.forceManyBody().strength(d => d.is_hub ? -800 : -120))
  .force("center", d3.forceCenter(W / 2, H / 2).strength(0.05))
  .force("collision", d3.forceCollide(d => d.is_hub ? 40 : 18))
  .alphaDecay(0.02);

// ── Draw links ─────────────────────────────────────────────────────────────
const linkGroup = g.append("g").attr("class","links");
const link = linkGroup.selectAll("line")
  .data(GRAPH.links)
  .join("line")
  .attr("class", d => `link ${{d.relation}}`)
  .style("stroke", d => LINK_COLORS[d.relation] || "#444");

// ── Draw nodes ─────────────────────────────────────────────────────────────
const nodeGroup = g.append("g").attr("class","nodes");
const node = nodeGroup.selectAll("g.node")
  .data(GRAPH.nodes)
  .join("g")
  .attr("class", d => `node${{d.is_hub ? " hub" : ""}}`)
  .call(d3.drag()
    .on("start", dragStart)
    .on("drag",  dragged)
    .on("end",   dragEnd))
  .on("mouseover", showTooltip)
  .on("mousemove", moveTooltip)
  .on("mouseout",  hideTooltip)
  .on("click",     highlightNode);

node.append("circle")
  .attr("r", d => d.is_hub ? 18 : 7)
  .style("fill", d => CATEGORY_COLORS[d.category] || "#555")
  .style("fill-opacity", d => d.active ? (d.is_hub ? 0.95 : 0.75) : 0.3)
  .style("stroke", d => CATEGORY_COLORS[d.category] || "#555")
  .style("stroke-width", d => d.is_hub ? 2 : 1)
  .style("stroke-opacity", 0.8)
  .style("filter", d => d.is_hub ? "url(#glow)" : "none");

const labels = node.append("text")
  .attr("class","node-label")
  .attr("dy", d => d.is_hub ? 24 : 12)
  .text(d => {{
    if (d.is_hub) return d.label.replace(/^Hub: /, "").split(" —")[0];
    return d.label.length > 35 ? d.label.slice(0,34)+"…" : d.label;
  }});

// ── Simulation tick ────────────────────────────────────────────────────────
simulation.on("tick", () => {{
  link
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

// ── Tooltip ────────────────────────────────────────────────────────────────
const tooltip = d3.select("#tooltip");

function showTooltip(event, d) {{
  const cat  = CATEGORY_LABELS[d.category] || d.category;
  const tags = d.semantic_tags.slice(0,10).map(t => `<span class="tt-tag">${{t}}</span>`).join("");
  tooltip.html(`
    <div class="tt-type">${{cat}} · ${{d.node_type}}</div>
    <div class="tt-content">${{d.content}}</div>
    ${{tags ? `<div class="tt-tags">${{tags}}</div>` : ""}}
    ${{d.is_hub ? `<div class="tt-refs">Hub node · click to focus category</div>` : ""}}
  `).classed("visible", true);
  moveTooltip(event);
}}

function moveTooltip(event) {{
  const x = event.clientX + 14, y = event.clientY - 10;
  const tw = 320, th = tooltip.node().offsetHeight;
  tooltip
    .style("left",  (x + tw > W ? x - tw - 20 : x) + "px")
    .style("top",   (y + th > H ? y - th       : y) + "px");
}}

function hideTooltip() {{
  tooltip.classed("visible", false);
}}

// ── Click highlight ────────────────────────────────────────────────────────
let highlighted = null;

function highlightNode(event, d) {{
  event.stopPropagation();
  if (highlighted === d.id) {{
    // Deselect
    node.classed("faded", false);
    link.style("opacity", null);
    highlighted = null;
    return;
  }}
  highlighted = d.id;

  const connectedIds = new Set([d.id]);
  GRAPH.links.forEach(l => {{
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    if (sid === d.id) connectedIds.add(tid);
    if (tid === d.id) connectedIds.add(sid);
  }});

  node.classed("faded", n => !connectedIds.has(n.id));
  link.style("opacity", l => {{
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    return (sid === d.id || tid === d.id) ? 1 : 0.05;
  }});
}}

svg.on("click", () => {{
  highlighted = null;
  node.classed("faded", false);
  link.style("opacity", null);
}});

// ── Drag ───────────────────────────────────────────────────────────────────
function dragStart(event, d) {{
  if (!event.active) simulation.alphaTarget(0.2).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragged(event, d) {{ d.fx = event.x; d.fy = event.y; }}
function dragEnd(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}}

// ── Search ─────────────────────────────────────────────────────────────────
d3.select("#search").on("input", function() {{
  const q = this.value.trim().toLowerCase();
  if (!q) {{
    node.classed("faded", false);
    link.style("opacity", null);
    return;
  }}
  const matched = new Set();
  GRAPH.nodes.forEach(n => {{
    if (n.content.toLowerCase().includes(q) ||
        n.semantic_tags.some(t => t.toLowerCase().includes(q)) ||
        n.category.includes(q) || n.topic.includes(q)) {{
      matched.add(n.id);
    }}
  }});
  node.classed("faded", n => !matched.has(n.id));
  link.style("opacity", l => {{
    const sid = typeof l.source==="object" ? l.source.id : l.source;
    const tid = typeof l.target==="object" ? l.target.id : l.target;
    return (matched.has(sid) && matched.has(tid)) ? 0.6 : 0.04;
  }});
}});

// ── Controls ───────────────────────────────────────────────────────────────
function resetView() {{
  svg.transition().duration(600)
     .call(zoom.transform, d3.zoomIdentity.translate(W/2, H/2).scale(0.9).translate(-W/2, -H/2));
  d3.select("#search").property("value","");
  node.classed("faded", false);
  link.style("opacity", null);
  highlighted = null;
}}

function toggleLabels() {{
  showLabels = !showLabels;
  labels.style("display", showLabels ? null : "none");
}}

// ── Legend ─────────────────────────────────────────────────────────────────
const categories = [...new Set(GRAPH.nodes.map(n => n.category))].filter(c => c !== "unknown");
const legendEl = d3.select("#legend");

categories.forEach(cat => {{
  const row = legendEl.append("div").attr("class","legend-row")
    .datum(cat)
    .on("click", function(event, c) {{
      if (activeCategories.has(c)) activeCategories.delete(c);
      else activeCategories.add(c);
      d3.select(this).classed("dimmed", !activeCategories.has(c));
      node.style("display", n => activeCategories.has(n.category) ? null : "none");
      link.style("display", l => {{
        const sc = typeof l.source==="object" ? l.source.category : "";
        const tc = typeof l.target==="object" ? l.target.category : "";
        return (activeCategories.has(sc) || activeCategories.has(tc)) ? null : "none";
      }});
    }});
  row.append("div").attr("class","legend-dot")
     .style("background", CATEGORY_COLORS[cat] || "#555");
  row.append("span").text(CATEGORY_LABELS[cat] || cat);
}});

// ── Stats ──────────────────────────────────────────────────────────────────
const hubs = GRAPH.nodes.filter(n => n.is_hub).length;
const atoms = GRAPH.nodes.length - hubs;
d3.select("#stats").html(`
  ${{GRAPH.nodes.length}} nodes (${{hubs}} hubs · ${{atoms}} atomic)<br>
  ${{GRAPH.links.length}} edges
`);

// ── Initial fit ────────────────────────────────────────────────────────────
simulation.on("end", () => {{
  const bbox = g.node().getBBox();
  const scale = Math.min(0.9 * W / bbox.width, 0.9 * H / bbox.height, 1);
  const tx = W/2 - scale*(bbox.x + bbox.width/2);
  const ty = H/2 - scale*(bbox.y + bbox.height/2);
  svg.transition().duration(800)
     .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_visualization(graph_json_path: str, output_path: str, title: str):
    with open(graph_json_path) as f:
        raw = json.load(f)

    d3_data = convert_to_d3(raw)
    graph_json_str = json.dumps(d3_data, ensure_ascii=False)

    html = HTML_TEMPLATE.format(
        title=title,
        graph_json=graph_json_str,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Visualization saved to: {output_path}")
    print(f"  Nodes: {len(d3_data['nodes'])}  ({sum(1 for n in d3_data['nodes'] if n['is_hub'])} hubs)")
    print(f"  Edges: {len(d3_data['links'])}")
    print(f"\nOpen in browser:")
    print(f"  Windows: \\\\wsl$\\Ubuntu{output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize a ContextGraph as an Obsidian-style HTML graph")
    parser.add_argument("--graph",   default=str(Path(__file__).parent / "company_context" / "contexts" / "metroboost_graph.json"), help="Path to graph JSON")
    parser.add_argument("--output",  default=str(Path(__file__).parent / "context_graph_viz.html"), help="Output HTML file")
    parser.add_argument("--company", default="MetroBoost", help="Company name (used as title)")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild graph from context JSON before visualizing")
    args = parser.parse_args()

    if args.rebuild:
        from LAYER_2.company_context.context_store import ContextStore
        from LAYER_2.context_graph.builder import GraphBuilder
        store = ContextStore()
        context_dict = store.load_raw(args.company.lower())
        builder = GraphBuilder()
        graph = GraphBuilder().build_from_context(context_dict)
        graph.save(args.graph)
        print(f"Graph rebuilt: {graph.stats()}")

    build_visualization(args.graph, args.output, args.company)
