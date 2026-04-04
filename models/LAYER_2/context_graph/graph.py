"""
Context Graph - a knowledge graph for company rules and protocols.

Nodes represent individual rules, protocols, statements, or facts.
Edges represent relationships between them (same_concept, related_to, supersedes).

This graph structure allows:
1. Efficient retrieval of relevant context for a specific topic
2. Change-resistant scoring: when wording changes but meaning stays the same,
   the old node gets an edge to the new node with relation "same_concept",
   so the model knows they are equivalent
3. Breaking large documents into searchable chunks the model can handle
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict


@dataclass
class Node:
    """A single piece of company context (rule, protocol, fact, etc.)."""
    node_id: str
    content: str
    topic: str  # e.g., "greeting", "refund_policy", "pricing"
    category: str  # "script_compliance", "factual_accuracy", etc.
    node_type: str  # "rule", "protocol", "statement", "offer", "fact", "procedure", "hub"
    content_hash: str = ""  # SHA-256 of normalized content for change detection
    keywords: List[str] = field(default_factory=list)
    semantic_tags: List[str] = field(default_factory=list)  # LLM-generated specific search tags
    is_hub: bool = False  # True for MOC/hub nodes (one per category, links to all nodes in it)
    version: int = 1
    active: bool = True

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute a hash of the normalized content."""
        normalized = self.content.lower().strip()
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Edge:
    """A relationship between two nodes."""
    source_id: str
    target_id: str
    relation: str  # "same_concept", "related_to", "supersedes", "part_of", "contradicts"
    confidence: float = 1.0
    note: str = ""


class ContextGraph:
    """
    A knowledge graph of company context nodes and their relationships.

    The graph is stored as JSON on disk for persistence and determinism.
    No embeddings are used - retrieval is based on keyword matching and
    graph traversal, which is fully deterministic.
    """

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._adjacency: Dict[str, List[str]] = {}  # node_id -> [neighbor_ids]

    def add_node(self, node: Node) -> str:
        """Add a node to the graph. Returns the node_id."""
        self.nodes[node.node_id] = node
        if node.node_id not in self._adjacency:
            self._adjacency[node.node_id] = []
        return node.node_id

    def add_edge(self, edge: Edge):
        """Add an edge between two nodes."""
        if edge.source_id not in self.nodes:
            raise ValueError(f"Source node not found: {edge.source_id}")
        if edge.target_id not in self.nodes:
            raise ValueError(f"Target node not found: {edge.target_id}")
        self.edges.append(edge)
        self._adjacency.setdefault(edge.source_id, []).append(edge.target_id)
        self._adjacency.setdefault(edge.target_id, []).append(edge.source_id)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str, relation: Optional[str] = None) -> List[Node]:
        """Get all neighbors of a node, optionally filtered by relation type."""
        neighbors = []
        for edge in self.edges:
            if edge.source_id == node_id:
                if relation is None or edge.relation == relation:
                    node = self.nodes.get(edge.target_id)
                    if node:
                        neighbors.append(node)
            elif edge.target_id == node_id:
                if relation is None or edge.relation == relation:
                    node = self.nodes.get(edge.source_id)
                    if node:
                        neighbors.append(node)
        return neighbors

    def get_edges_for_node(self, node_id: str) -> List[Edge]:
        """Get all edges connected to a node."""
        return [
            e for e in self.edges
            if e.source_id == node_id or e.target_id == node_id
        ]

    def find_nodes_by_topic(self, topic: str) -> List[Node]:
        """Find all active nodes with a given topic."""
        return [
            n for n in self.nodes.values()
            if n.topic == topic and n.active
        ]

    def find_nodes_by_category(self, category: str) -> List[Node]:
        """Find all active nodes in a category."""
        return [
            n for n in self.nodes.values()
            if n.category == category and n.active
        ]

    def find_nodes_by_keywords(self, keywords: List[str]) -> List[Node]:
        """
        Find nodes that match any of the given keywords.
        Returns nodes sorted by number of matching keywords (most matches first).
        """
        scored = []
        keywords_lower = [k.lower() for k in keywords]
        for node in self.nodes.values():
            if not node.active:
                continue
            # Check keywords list
            node_kw_lower = [k.lower() for k in node.keywords]
            keyword_matches = sum(1 for k in keywords_lower if k in node_kw_lower)
            # Check content
            content_lower = node.content.lower()
            content_matches = sum(1 for k in keywords_lower if k in content_lower)
            total = keyword_matches * 2 + content_matches  # keywords weighted higher
            if total > 0:
                scored.append((total, node))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored]

    def find_equivalent_nodes(self, node_id: str) -> List[Node]:
        """Find all nodes that are semantically equivalent (via same_concept edges)."""
        return self.get_neighbors(node_id, relation="same_concept")

    def get_canonical_node(self, node_id: str) -> Node:
        """
        Get the canonical (latest active) version of a node.
        Follows 'supersedes' edges to find the most recent version.
        """
        current = self.nodes.get(node_id)
        if current is None:
            raise ValueError(f"Node not found: {node_id}")

        # Follow supersedes chain
        visited = {node_id}
        while True:
            superseded_by = [
                e.target_id for e in self.edges
                if e.source_id == current.node_id and e.relation == "supersedes"
            ]
            if not superseded_by:
                break
            next_id = superseded_by[0]
            if next_id in visited:
                break  # Avoid cycles
            visited.add(next_id)
            next_node = self.nodes.get(next_id)
            if next_node and next_node.active:
                current = next_node
            else:
                break
        return current

    def save(self, filepath: str):
        """Save graph to JSON file."""
        data = {
            "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "ContextGraph":
        """Load graph from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = cls()
        for nid, ndata in data.get("nodes", {}).items():
            node = Node(**ndata)
            graph.nodes[nid] = node
            graph._adjacency.setdefault(nid, [])

        for edata in data.get("edges", []):
            edge = Edge(**edata)
            graph.edges.append(edge)
            graph._adjacency.setdefault(edge.source_id, []).append(edge.target_id)
            graph._adjacency.setdefault(edge.target_id, []).append(edge.source_id)

        return graph

    def stats(self) -> dict:
        """Return graph statistics."""
        active = sum(1 for n in self.nodes.values() if n.active)
        return {
            "total_nodes": len(self.nodes),
            "active_nodes": active,
            "total_edges": len(self.edges),
            "categories": list(set(n.category for n in self.nodes.values())),
            "topics": list(set(n.topic for n in self.nodes.values())),
        }
