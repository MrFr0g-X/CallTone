"""
Change Tracker - manages changes to company protocols with semantic equivalence checking.

When the QA head wants to change a rule/protocol/statement, they submit a
ChangeTicket describing what they want to change. The system:

1. Compares old text vs new text using the process-context-change skill
2. If semantically equivalent → updates wording, adds same_concept edge, NO score impact
3. If semantically different → creates new node, marks old as superseded, may affect scores
4. Logs all changes for audit trail

This prevents the "context change effect" where rewording the same rule
causes agent scores to change even though the meaning didn't change.
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from LAYER_2.context_graph.graph import ContextGraph, Node, Edge


@dataclass
class ChangeTicket:
    """A request to change a piece of company context."""
    ticket_id: str
    submitted_by: str
    submitted_at: str
    old_text: str
    new_text: str
    reason: str
    field_name: str  # Which context field this belongs to
    topic: str  # The topic in the graph
    category: str  # The category (script_compliance, factual_accuracy, etc.)

    # Filled after processing
    status: str = "pending"  # "pending", "approved_equivalent", "approved_different", "rejected"
    is_semantically_equivalent: Optional[bool] = None
    equivalence_confidence: Optional[float] = None
    equivalence_explanation: Optional[str] = None
    processed_at: Optional[str] = None


class ChangeTracker:
    """Tracks and processes changes to company context."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            self.storage_dir = Path(__file__).parent / "change_logs"
        else:
            self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_ticket(
        self,
        old_text: str,
        new_text: str,
        reason: str,
        field_name: str,
        topic: str,
        category: str,
        submitted_by: str = "QA_Head",
    ) -> ChangeTicket:
        """Create a new change ticket."""
        ticket_id = hashlib.sha256(
            f"{old_text}{new_text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        ticket = ChangeTicket(
            ticket_id=ticket_id,
            submitted_by=submitted_by,
            submitted_at=datetime.now().isoformat(),
            old_text=old_text,
            new_text=new_text,
            reason=reason,
            field_name=field_name,
            topic=topic,
            category=category,
        )

        self._save_ticket(ticket)
        return ticket

    def process_ticket(
        self,
        ticket: ChangeTicket,
        graph: ContextGraph,
        equivalence_result: dict,
    ) -> ChangeTicket:
        """
        Process a change ticket using the result from the process-context-change skill.

        Args:
            ticket: The change ticket to process
            graph: The context graph to update
            equivalence_result: Output from the process-context-change skill
                Expected keys: is_equivalent (bool), confidence (float),
                               explanation (str), recommended_action (str)

        Returns:
            Updated ticket
        """
        is_equivalent = equivalence_result.get("is_equivalent", False)
        confidence = equivalence_result.get("confidence", 0.0)
        explanation = equivalence_result.get("explanation", "")

        ticket.is_semantically_equivalent = is_equivalent
        ticket.equivalence_confidence = confidence
        ticket.equivalence_explanation = explanation
        ticket.processed_at = datetime.now().isoformat()

        if is_equivalent:
            ticket.status = "approved_equivalent"
            self._apply_equivalent_change(ticket, graph)
        else:
            ticket.status = "approved_different"
            self._apply_different_change(ticket, graph)

        self._save_ticket(ticket)
        return ticket

    def _apply_equivalent_change(self, ticket: ChangeTicket, graph: ContextGraph):
        """
        Apply a semantically equivalent change.
        Updates the node content but adds a same_concept edge to preserve history.
        This ensures scores don't change due to rewording.
        """
        # Find the node with the old text
        old_node = None
        for node in graph.nodes.values():
            if node.content.strip() == ticket.old_text.strip() and node.active:
                old_node = node
                break

        if old_node is None:
            return

        # Create a new node with the updated text
        new_node = Node(
            node_id=f"{old_node.node_id}_v{old_node.version + 1}",
            content=ticket.new_text,
            topic=old_node.topic,
            category=old_node.category,
            node_type=old_node.node_type,
            keywords=old_node.keywords,      # Keep same keywords since meaning is same
            semantic_tags=old_node.semantic_tags,  # Keep same tags since meaning is same
            version=old_node.version + 1,
            active=True,
        )
        graph.add_node(new_node)

        # Add same_concept edge
        graph.add_edge(Edge(
            source_id=old_node.node_id,
            target_id=new_node.node_id,
            relation="same_concept",
            confidence=ticket.equivalence_confidence or 1.0,
            note=f"Reworded by {ticket.submitted_by}: {ticket.reason}",
        ))

        # Deactivate old node
        old_node.active = False

    def _apply_different_change(self, ticket: ChangeTicket, graph: ContextGraph):
        """
        Apply a semantically different change.
        Creates new node and marks old as superseded.
        """
        old_node = None
        for node in graph.nodes.values():
            if node.content.strip() == ticket.old_text.strip() and node.active:
                old_node = node
                break

        if old_node is None:
            # No existing node found, create fresh
            new_node = Node(
                node_id=f"new_{ticket.ticket_id}",
                content=ticket.new_text,
                topic=ticket.topic,
                category=ticket.category,
                node_type="rule",
                keywords=[],
                version=1,
                active=True,
            )
            graph.add_node(new_node)
            return

        # Create new node
        new_node = Node(
            node_id=f"{old_node.node_id}_v{old_node.version + 1}",
            content=ticket.new_text,
            topic=old_node.topic,
            category=old_node.category,
            node_type=old_node.node_type,
            keywords=[],  # Will be re-extracted by builder
            version=old_node.version + 1,
            active=True,
        )
        graph.add_node(new_node)

        # Add supersedes edge (old → new means new supersedes old)
        graph.add_edge(Edge(
            source_id=old_node.node_id,
            target_id=new_node.node_id,
            relation="supersedes",
            confidence=1.0,
            note=f"Changed by {ticket.submitted_by}: {ticket.reason}",
        ))

        # Deactivate old
        old_node.active = False

    def _save_ticket(self, ticket: ChangeTicket):
        """Save ticket to disk."""
        filepath = self.storage_dir / f"{ticket.ticket_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(ticket), f, indent=2, ensure_ascii=False)

    def load_ticket(self, ticket_id: str) -> ChangeTicket:
        """Load a ticket from disk."""
        filepath = self.storage_dir / f"{ticket_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Ticket not found: {ticket_id}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ChangeTicket(**data)

    def list_tickets(self, status: Optional[str] = None) -> List[ChangeTicket]:
        """List all tickets, optionally filtered by status."""
        tickets = []
        for filepath in self.storage_dir.glob("*.json"):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            ticket = ChangeTicket(**data)
            if status is None or ticket.status == status:
                tickets.append(ticket)
        return sorted(tickets, key=lambda t: t.submitted_at, reverse=True)
