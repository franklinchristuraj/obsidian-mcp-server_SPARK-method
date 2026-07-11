"""In-memory typed-edge graph over entity notes (PRD_ziksaka-knowledge-graph, Phase 2).

Built fresh per call from an already-loaded List[ParsedNote] (entities/ only) —
no separate cache layer, matching the vault's own "631 notes, full rebuild is
milliseconds" scale. Edge extraction and resolution rules are documented on
GraphIndex._build; see robust-mapping-spindle.md for the scoping rationale
(read-time derivation only, no frontmatter backfill/mutation here).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .entity_index import EntityIndex
from .parser import CONNECTIONS_HEADING, ParsedNote, WIKILINK_RE, extract_section_links, normalize_link_target, normalize_path_key

# Controlled vocabulary, PRD §4.2 (used as-is, no vocabulary changes in this cut).
REL_ENGAGED_WITH = "engaged_with"
REL_ATTENDED = "attended"
REL_ATTENDEES = "attendees"
REL_RELATED_TO = "related_to"
REL_MENTION = "mention"


@dataclass(frozen=True)
class Edge:
    source: str  # canonical path
    target: str  # canonical path
    type: str
    source_note: str  # note the edge was declared on (== source, except the attendees inverse)
    provenance: str  # "frontmatter" / "connections" / "body"


def as_link_list(value: Any) -> List[str]:
    """Normalize a frontmatter scalar/list value into wikilink target strings.

    Handles both wikilink-wrapped ("[[claroty]]") and bare ("claroty") forms.
    """
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    links: List[str] = []
    for item in items:
        s = str(item).strip()
        if not s:
            continue
        m = WIKILINK_RE.search(s)
        target = normalize_link_target(m.group(1) if m else s)
        if target:
            links.append(target)
    return links


class GraphIndex:
    """Typed-edge graph over a snapshot of entity notes.

    Nodes are canonical note paths. Edges are directed; ``shortest_path``
    traverses an undirected adjacency built alongside the directed one.
    """

    def __init__(self, notes: List[ParsedNote]):
        self.notes = notes
        self.entity_index = EntityIndex(notes)
        self.nodes: Dict[str, ParsedNote] = {
            normalize_path_key(n.path): n for n in notes
        }
        self.edges: List[Edge] = []
        self._out: Dict[str, List[Edge]] = defaultdict(list)
        self._in: Dict[str, List[Edge]] = defaultdict(list)
        self._adj: Dict[str, List[Tuple[str, Edge]]] = defaultdict(list)
        self._build()

    def _resolve(self, link: str) -> Optional[str]:
        return self.entity_index.resolve_bare_or_path(link)

    def _resolve_node(self, name: str) -> Optional[str]:
        return self.entity_index.resolve_bare_or_path(name)

    def _add_resolved_edge(
        self, source_path: str, target_path: str, type_: str, source_note: str, provenance: str
    ) -> None:
        source_key = normalize_path_key(source_path)
        target_key = normalize_path_key(target_path)
        if source_key not in self.nodes or target_key not in self.nodes:
            return
        if source_key == target_key:
            return
        edge = Edge(
            source=self.nodes[source_key].path,
            target=self.nodes[target_key].path,
            type=type_,
            source_note=source_note,
            provenance=provenance,
        )
        self.edges.append(edge)
        self._out[source_key].append(edge)
        self._in[target_key].append(edge)
        self._adj[source_key].append((target_key, edge))
        self._adj[target_key].append((source_key, edge))

    def _add_link_edge(
        self, source_path: str, target_link: str, type_: str, source_note: str, provenance: str
    ) -> None:
        target_path = self._resolve(target_link)
        if target_path is None:
            return
        self._add_resolved_edge(source_path, target_path, type_, source_note, provenance)

    def _build(self) -> None:
        for note in self.notes:
            fm = note.frontmatter

            if note.entity_type == "event":
                engaged_links = as_link_list(fm.get("customer")) + as_link_list(
                    fm.get("organizations")
                )
                seen_targets: set = set()
                for link in engaged_links:
                    target = self._resolve(link)
                    if target is None:
                        continue
                    tkey = normalize_path_key(target)
                    if tkey in seen_targets:
                        continue
                    seen_targets.add(tkey)
                    self._add_resolved_edge(
                        note.path, target, REL_ENGAGED_WITH, note.path, "frontmatter"
                    )

                for link in as_link_list(fm.get("participants")):
                    person_path = self._resolve(link)
                    if person_path is None:
                        continue
                    self._add_resolved_edge(
                        person_path, note.path, REL_ATTENDED, note.path, "frontmatter"
                    )
                    self._add_resolved_edge(
                        note.path, person_path, REL_ATTENDEES, note.path, "frontmatter"
                    )

                for link in as_link_list(fm.get("concepts")):
                    self._add_link_edge(
                        note.path, link, REL_RELATED_TO, note.path, "frontmatter"
                    )

            conn_links = extract_section_links(note, CONNECTIONS_HEADING)
            for link in conn_links:
                self._add_link_edge(
                    note.path, link, REL_RELATED_TO, note.path, "connections"
                )

            excluded = set(note.frontmatter_links) | set(conn_links)
            for link in note.outlinks:
                if link in excluded:
                    continue
                self._add_link_edge(note.path, link, REL_MENTION, note.path, "body")

    # =================== Queries ===================

    def neighbors(
        self,
        name: str,
        depth: int = 1,
        rel_type: Optional[str] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        start = self._resolve_node(name)
        if start is None:
            return {"resolved": False, "query": name, "neighbors": [], "count": 0}

        start_key = normalize_path_key(start)
        depth = max(1, int(depth))
        best_hop: Dict[str, int] = {start_key: 0}
        edge_hits: Dict[str, List[Edge]] = defaultdict(list)
        frontier = {start_key}

        for hop in range(1, depth + 1):
            next_frontier: set = set()
            for key in frontier:
                candidates: List[Tuple[Edge, str]] = []
                if direction in ("out", "both"):
                    candidates += [(e, e.target) for e in self._out.get(key, [])]
                if direction in ("in", "both"):
                    candidates += [(e, e.source) for e in self._in.get(key, [])]
                for edge, other_path in candidates:
                    if rel_type and edge.type != rel_type:
                        continue
                    other_key = normalize_path_key(other_path)
                    if other_key == start_key:
                        continue
                    edge_hits[other_key].append(edge)
                    if other_key not in best_hop:
                        best_hop[other_key] = hop
                        next_frontier.add(other_key)
            frontier = next_frontier
            if not frontier:
                break

        results = []
        for key, edges in edge_hits.items():
            node = self.nodes.get(key)
            if node is None:
                continue
            results.append(
                {
                    "path": node.path,
                    "entity_type": node.entity_type,
                    "agent_context": node.agent_context,
                    "hops": best_hop.get(key, 1),
                    "edge_types": sorted({e.type for e in edges}),
                }
            )
        results.sort(key=lambda r: (r["hops"], r["path"]))
        return {
            "resolved": True,
            "canonical_path": start,
            "neighbors": results,
            "count": len(results),
        }

    def backlinks(self, name: str) -> Dict[str, Any]:
        target = self._resolve_node(name)
        if target is None:
            return {"resolved": False, "query": name, "backlinks": [], "count": 0}
        target_key = normalize_path_key(target)
        entries = []
        for edge in self._in.get(target_key, []):
            node = self.nodes.get(normalize_path_key(edge.source))
            if node is None:
                continue
            entries.append(
                {
                    "path": node.path,
                    "entity_type": node.entity_type,
                    "agent_context": node.agent_context,
                    "edge_type": edge.type,
                    "provenance": edge.provenance,
                }
            )
        entries.sort(key=lambda e: e["path"])
        return {
            "resolved": True,
            "canonical_path": target,
            "backlinks": entries,
            "count": len(entries),
        }

    def shortest_path(self, a: str, b: str) -> Dict[str, Any]:
        start = self._resolve_node(a)
        end = self._resolve_node(b)
        if start is None or end is None:
            return {"resolved": False, "found": False, "path": []}
        start_key, end_key = normalize_path_key(start), normalize_path_key(end)
        if start_key == end_key:
            return {"resolved": True, "found": True, "path": [], "hops": 0}

        visited = {start_key}
        prev: Dict[str, Tuple[str, Edge]] = {}
        queue = deque([start_key])
        found = False
        while queue and not found:
            key = queue.popleft()
            for other_key, edge in self._adj.get(key, []):
                if other_key in visited:
                    continue
                visited.add(other_key)
                prev[other_key] = (key, edge)
                if other_key == end_key:
                    found = True
                    break
                queue.append(other_key)

        if not found:
            return {"resolved": True, "found": False, "path": []}

        chain: List[dict] = []
        cur = end_key
        while cur != start_key:
            prev_key, edge = prev[cur]
            chain.append(
                {
                    "from": self.nodes[prev_key].path,
                    "to": self.nodes[cur].path,
                    "edge_type": edge.type,
                }
            )
            cur = prev_key
        chain.reverse()
        return {"resolved": True, "found": True, "path": chain, "hops": len(chain)}

    def health_summary(self) -> Dict[str, Any]:
        type_counts: Dict[str, int] = {}
        for e in self.edges:
            type_counts[e.type] = type_counts.get(e.type, 0) + 1

        degree: Dict[str, int] = {k: 0 for k in self.nodes}
        for e in self.edges:
            sk, tk = normalize_path_key(e.source), normalize_path_key(e.target)
            degree[sk] = degree.get(sk, 0) + 1
            degree[tk] = degree.get(tk, 0) + 1
        orphans = sorted(self.nodes[k].path for k, d in degree.items() if d == 0)

        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "edge_type_counts": dict(sorted(type_counts.items())),
            "orphan_count": len(orphans),
            "orphans": orphans[:50],
        }
