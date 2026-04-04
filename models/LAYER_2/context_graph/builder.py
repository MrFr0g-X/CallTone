"""
Graph Builder - constructs a ContextGraph from company context data.

Two build paths:

1. Zettelkasten path (new, preferred):
   Called when the context JSON contains an "atomic_nodes" key produced by
   text_ingestion Pass 5. Each atomic node already has LLM-generated semantic_tags
   and declared cross_refs — no keyword-overlap guessing needed.

   Structure mirrors a Zettelkasten:
   - Atomic nodes  → one fact/rule per node, with semantic_tags
   - Hub nodes     → one per category (MOC-style), link to all nodes in that category
   - part_of edges → atomic node → its category hub
   - related_to edges → declared cross-category references via hub nodes only

2. Fallback path (legacy):
   Called for old context JSONs without "atomic_nodes". Splits field text into
   items and extracts keywords by stop-word removal. Auto-generates relationship
   edges from keyword overlap (less reliable).
"""

import re
from typing import List
from .graph import ContextGraph, Node, Edge


# ---------------------------------------------------------------------------
# Field metadata lookup: field_name -> (topic, category, node_type)
# Used by the Zettelkasten builder to resolve field names from atomic_nodes.
# ---------------------------------------------------------------------------

FIELD_META = {
    "greeting_script":                ("greeting",        "script_compliance",  "protocol"),
    "closing_script":                 ("closing",         "script_compliance",  "protocol"),
    "required_verification_steps":    ("verification",    "script_compliance",  "protocol"),
    "hold_procedure":                 ("hold",            "script_compliance",  "protocol"),
    "transfer_procedure":             ("transfer",        "script_compliance",  "protocol"),
    "escalation_procedure":           ("escalation",      "script_compliance",  "protocol"),
    "mandatory_disclosures":          ("disclosure",      "script_compliance",  "protocol"),
    "prohibited_phrases":             ("prohibited",      "script_compliance",  "rule"),
    "products_and_services":          ("products",        "factual_accuracy",   "fact"),
    "current_promotions":             ("promotions",      "factual_accuracy",   "offer"),
    "policies":                       ("policies",        "factual_accuracy",   "rule"),
    "common_troubleshooting":         ("troubleshooting", "factual_accuracy",   "procedure"),
    "contact_information":            ("contacts",        "factual_accuracy",   "fact"),
    "frequently_asked_questions":     ("faq",             "factual_accuracy",   "fact"),
    "tone_guidelines":                ("tone",            "politeness_tone",    "rule"),
    "empathy_guidelines":             ("empathy",         "empathy",            "rule"),
    "conflict_resolution_guidelines": ("conflict",        "conflict_detection", "rule"),
    "resolution_expectations":        ("resolution",      "issue_resolution",   "rule"),
}


class GraphBuilder:
    """Builds a ContextGraph from company context data."""

    def __init__(self):
        self._node_counter = 0

    def _next_id(self, prefix: str) -> str:
        """Generate a unique node ID."""
        self._node_counter += 1
        return f"{prefix}_{self._node_counter:04d}"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text (used by legacy path)."""
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "and",
            "but", "or", "not", "no", "if", "then", "than", "that",
            "this", "these", "those", "it", "its", "they", "them",
            "their", "we", "our", "you", "your", "he", "she", "his",
            "her", "must", "also", "when", "how", "what", "which",
        }
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = []
        seen = set()
        for w in words:
            if w not in stop_words and w not in seen:
                seen.add(w)
                keywords.append(w)
        return keywords[:20]

    def _split_into_items(self, text: str) -> List[str]:
        """Split numbered or bulleted list text into individual items (legacy path)."""
        items = re.split(r'\n\s*\d+[\.\)]\s*', text)
        if len(items) > 1:
            return [item.strip() for item in items if item.strip()]
        items = re.split(r'\n\s*[-\*]\s*', text)
        if len(items) > 1:
            return [item.strip() for item in items if item.strip()]
        items = [line.strip() for line in text.strip().split('\n') if line.strip()]
        if len(items) > 1:
            return items
        return [text.strip()] if text.strip() else []

    # -----------------------------------------------------------------------
    # Main entry point — branches on whether atomic_nodes key is present
    # -----------------------------------------------------------------------

    def build_from_context(self, context_dict: dict) -> ContextGraph:
        """
        Build a ContextGraph from a company context dictionary.

        If the dict has an "atomic_nodes" key (produced by text_ingestion Pass 5),
        uses the Zettelkasten path with LLM-generated semantic tags.

        Otherwise falls back to the legacy keyword-based path.
        """
        atomic_nodes = context_dict.get("atomic_nodes")
        if atomic_nodes:
            return self.build_from_atomic_nodes(
                atomic_nodes,
                context_dict.get("company_name", "Unknown"),
            )
        # Legacy fallback for old context JSONs without atomic_nodes
        return self._build_from_context_legacy(context_dict)

    # -----------------------------------------------------------------------
    # Zettelkasten path
    # -----------------------------------------------------------------------

    def build_from_atomic_nodes(self, atomic_nodes: list, company: str) -> ContextGraph:
        """
        Build a Zettelkasten-style graph from LLM-generated atomic nodes.

        Structure:
        - One Node per atomic fact, carrying LLM-generated semantic_tags
        - One hub Node per category (MOC-style entry point)
        - part_of edges: each atomic node → its category hub
        - related_to edges: declared cross-refs → hub of referenced field's category
        """
        graph = ContextGraph()

        # Pass 1: create all atomic nodes, group by category
        nodes_by_category = {}   # category -> [Node]
        created_pairs = []       # [(Node, raw_item_dict)]

        for item in atomic_nodes:
            field = item.get("field", "")
            content = item.get("content", "")
            semantic_tags = item.get("semantic_tags", [])

            if not field or not content:
                continue

            meta = FIELD_META.get(field)
            if meta is None:
                # Unknown field from LLM — skip gracefully
                continue

            topic, category, node_type = meta
            node = Node(
                node_id=self._next_id(field[:3]),
                content=content,
                topic=topic,
                category=category,
                node_type=node_type,
                keywords=self._extract_keywords(content),  # kept for legacy compat
                semantic_tags=semantic_tags,
            )
            graph.add_node(node)
            nodes_by_category.setdefault(category, []).append(node)
            created_pairs.append((node, item))

        # Pass 2: create one hub node per category
        hub_by_category = {}   # category -> hub_node_id
        hub_by_field = {}      # field_name -> hub_node_id of that field's category

        for category, nodes in nodes_by_category.items():
            topics = sorted(set(n.topic for n in nodes))
            hub_content = (
                f"Hub: {category.replace('_', ' ').title()} — "
                f"{len(nodes)} rules covering: {', '.join(topics)}"
            )
            hub_node = Node(
                node_id=self._next_id("hub"),
                content=hub_content,
                topic=f"{category}_hub",
                category=category,
                node_type="hub",
                keywords=[],
                semantic_tags=[category, category.replace("_", "-")] + topics,
                is_hub=True,
            )
            graph.add_node(hub_node)
            hub_by_category[category] = hub_node.node_id

            # part_of edges: every atomic node in this category → hub
            for node in nodes:
                graph.add_edge(Edge(
                    source_id=node.node_id,
                    target_id=hub_node.node_id,
                    relation="part_of",
                    confidence=1.0,
                    note=f"Part of {category}",
                ))

        # Build field -> hub_node_id lookup for cross-ref edges
        for field_name, (_, field_category, _) in FIELD_META.items():
            if field_category in hub_by_category:
                hub_by_field[field_name] = hub_by_category[field_category]

        # Pass 3: build declared cross-reference edges (atomic → foreign hub only)
        for node, item in created_pairs:
            node_category = node.category
            for ref_field in item.get("cross_refs", []):
                target_hub_id = hub_by_field.get(ref_field)
                if target_hub_id is None:
                    continue
                # Only add cross-CATEGORY references (same-category is already in hub)
                ref_category = FIELD_META.get(ref_field, (None, None, None))[1]
                if ref_category == node_category:
                    continue
                graph.add_edge(Edge(
                    source_id=node.node_id,
                    target_id=target_hub_id,
                    relation="related_to",
                    confidence=0.9,
                    note=f"Declared cross-reference to {ref_field}",
                ))

        return graph

    # -----------------------------------------------------------------------
    # Legacy path (unchanged from original, kept for backward compatibility)
    # -----------------------------------------------------------------------

    def _build_from_context_legacy(self, context_dict: dict) -> ContextGraph:
        """Original keyword-based builder. Used when atomic_nodes is absent."""
        graph = ContextGraph()
        company = context_dict.get("company_name", "Unknown")

        sc = context_dict.get("script_compliance", {})
        self._add_script_compliance_nodes(graph, sc, company)

        fa = context_dict.get("factual_accuracy", {})
        self._add_factual_accuracy_nodes(graph, fa, company)

        bh = context_dict.get("behavioral", {})
        self._add_behavioral_nodes(graph, bh, company)

        self._build_relationship_edges(graph)
        return graph

    def _add_script_compliance_nodes(self, graph: ContextGraph, sc: dict, company: str):
        field_to_topic = {
            "greeting_script": "greeting",
            "closing_script": "closing",
            "required_verification_steps": "verification",
            "hold_procedure": "hold",
            "transfer_procedure": "transfer",
            "escalation_procedure": "escalation",
            "mandatory_disclosures": "disclosure",
            "prohibited_phrases": "prohibited",
        }
        for field_name, topic in field_to_topic.items():
            content = sc.get(field_name, "")
            if not content:
                continue
            if field_name in ("required_verification_steps", "mandatory_disclosures", "prohibited_phrases"):
                items = self._split_into_items(content)
                for item in items:
                    node = Node(
                        node_id=self._next_id("sc"),
                        content=item,
                        topic=topic,
                        category="script_compliance",
                        node_type="rule" if field_name == "prohibited_phrases" else "protocol",
                        keywords=self._extract_keywords(item),
                    )
                    graph.add_node(node)
            else:
                node = Node(
                    node_id=self._next_id("sc"),
                    content=content,
                    topic=topic,
                    category="script_compliance",
                    node_type="protocol",
                    keywords=self._extract_keywords(content),
                )
                graph.add_node(node)

    def _add_factual_accuracy_nodes(self, graph: ContextGraph, fa: dict, company: str):
        field_to_topic = {
            "products_and_services": "products",
            "current_promotions": "promotions",
            "policies": "policies",
            "common_troubleshooting": "troubleshooting",
            "contact_information": "contacts",
            "frequently_asked_questions": "faq",
        }
        for field_name, topic in field_to_topic.items():
            content = fa.get(field_name, "")
            if not content:
                continue
            items = self._split_into_items(content)
            for item in items:
                node_type = "fact"
                if field_name == "policies":
                    node_type = "rule"
                elif field_name == "current_promotions":
                    node_type = "offer"
                elif field_name == "common_troubleshooting":
                    node_type = "procedure"
                node = Node(
                    node_id=self._next_id("fa"),
                    content=item,
                    topic=topic,
                    category="factual_accuracy",
                    node_type=node_type,
                    keywords=self._extract_keywords(item),
                )
                graph.add_node(node)

    def _add_behavioral_nodes(self, graph: ContextGraph, bh: dict, company: str):
        field_map = {
            "tone_guidelines":                ("tone",       "politeness_tone"),
            "empathy_guidelines":             ("empathy",    "empathy"),
            "conflict_resolution_guidelines": ("conflict",   "conflict_detection"),
            "resolution_expectations":        ("resolution", "issue_resolution"),
        }
        for field_name, (topic, category) in field_map.items():
            content = bh.get(field_name, "")
            if not content:
                continue
            items = self._split_into_items(content)
            for item in items:
                node = Node(
                    node_id=self._next_id("bh"),
                    content=item,
                    topic=topic,
                    category=category,
                    node_type="rule",
                    keywords=self._extract_keywords(item),
                )
                graph.add_node(node)

    def _build_relationship_edges(self, graph: ContextGraph):
        """Auto-generate related_to edges from keyword overlap (legacy path only)."""
        node_list = list(graph.nodes.values())
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                n1 = node_list[i]
                n2 = node_list[j]
                if n1.category == n2.category and n1.topic == n2.topic:
                    continue
                kw1 = set(k.lower() for k in n1.keywords)
                kw2 = set(k.lower() for k in n2.keywords)
                overlap = kw1 & kw2
                if len(overlap) >= 3:
                    edge = Edge(
                        source_id=n1.node_id,
                        target_id=n2.node_id,
                        relation="related_to",
                        confidence=len(overlap) / max(len(kw1), len(kw2)),
                        note=f"Shared keywords: {', '.join(sorted(overlap)[:5])}",
                    )
                    graph.add_edge(edge)
