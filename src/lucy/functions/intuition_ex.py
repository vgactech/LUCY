"""
intuition_ex.py — NE : Intuition Extravertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / intuition_ex
Auteur : LuCY Project

Phase 2 — Contrat opérationnel formel :
  Opération  : Générer de nouvelles associations et plusieurs prolongements possibles.
  Mécanisme  : Expansion BFS bornée (max_depth=3, top_k=5) dans le graphe de connaissances.
               Scoring de plausibilité par co-occurrence apprise. Sans LLM externe.
  Sortie     : HypothesisSet (candidates, plausibility_scores, expansion_depth, trace)
  Limites    : max 5 hypothèses (NE_TOP_K), plausibilités dans [0.0, 1.0].
  Traçabilité: seed_concepts, bfs_depth, candidates_before_filter, top_k_selected.
  Critères   : expansion_attempted (voir CONTRACT_NE).

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from .contracts import CONTRACT_NE
from .types import Hypothesis, HypothesisSet, OperatorTrace, PerceptualFact

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NE_MAX_DEPTH: int = 3       # profondeur BFS maximale
NE_TOP_K: int = 5           # nombre d'hypothèses retenues
NE_MIN_PLAUSIBILITY: float = 0.1  # seuil minimal de plausibilité


# ---------------------------------------------------------------------------
# Graphe de connaissances en mémoire (structure légère)
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """Graphe de connaissances simple pour NE.

    Nœuds = concepts (str)
    Arêtes = co-occurrences avec poids de plausibilité [0.0 – 1.0]
    """

    def __init__(self) -> None:
        # adjacency list : concept -> {voisin: poids}
        self._graph: dict[str, dict[str, float]] = {}

    def add_node(self, concept: str) -> None:
        if concept not in self._graph:
            self._graph[concept] = {}

    def add_edge(self, src: str, dst: str, weight: float = 0.5) -> None:
        """Ajouter ou renforcer une arête bidirectionnelle."""
        self.add_node(src)
        self.add_node(dst)
        # Renforcement par moyenne pondérée avec l'existant
        existing = self._graph[src].get(dst, 0.0)
        self._graph[src][dst] = round(0.7 * existing + 0.3 * weight, 4)
        existing_rev = self._graph[dst].get(src, 0.0)
        self._graph[dst][src] = round(0.7 * existing_rev + 0.3 * weight, 4)

    def neighbors(self, concept: str) -> dict[str, float]:
        """Voisins directs d'un concept avec leurs poids."""
        return dict(self._graph.get(concept, {}))

    def node_count(self) -> int:
        return len(self._graph)

    def edge_count(self) -> int:
        return sum(len(v) for v in self._graph.values()) // 2

    def to_dict(self) -> dict:
        return dict(self._graph)

    def load_dict(self, data: dict[str, dict[str, float]]) -> None:
        self._graph = data


# ---------------------------------------------------------------------------
# Opérateur NE principal
# ---------------------------------------------------------------------------

class IntuitionExtravertie:
    """NE — Perception des possibilités ouvertes par l'environnement.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_NE).
    Transformations :
    1. Expansion BFS bornée dans le graphe de connaissances
    2. Scoring de plausibilité par co-occurrence apprise
    3. Sélection top-K hypothèses candidates
    4. Vérification des limites du contrat + génération OperatorTrace
    """

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        max_depth: int = NE_MAX_DEPTH,
        top_k: int = NE_TOP_K,
    ) -> None:
        self.graph = graph or KnowledgeGraph()
        self.max_depth = max_depth
        self.top_k = top_k
        self.contract = CONTRACT_NE

    def process(self, fact: PerceptualFact, cycle_ref: str = "") -> HypothesisSet:
        """Explorer les possibilités ouvertes par un PerceptualFact.

        Args:
            fact      : sortie de SE
            cycle_ref : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            HypothesisSet — ensemble d'hypothèses classées par plausibilité.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        input_hash = fact.raw_input_hash or ""

        trace = OperatorTrace(
            operator_id="NE",
            cycle_ref=cycle_ref,
            input_hash=input_hash,
        )

        # Pas de perception → pas d'hypothèse
        if not fact.exists or fact.confidence < 0.3:
            trace.intermediate_steps.append("expansion:skipped_no_perception")
            result = HypothesisSet(
                candidates=[],
                plausibility_scores={},
                expansion_depth=0,
                ts_ns=t_start,
                trace=trace,
            )
            result, trace = self.contract.finalize_trace(result, trace, t_start)
            return result

        # --- Étape 1 : extraire les concepts d'ancrage depuis SE ---
        seed_concepts = self._extract_seeds(fact)
        trace.intermediate_steps.append(f"seed_concepts:{seed_concepts}")

        if not seed_concepts:
            trace.intermediate_steps.append("expansion:no_seed_concepts")
            result = HypothesisSet(
                candidates=[],
                plausibility_scores={"reason": "no_seed_concepts"},
                expansion_depth=0,
                ts_ns=t_start,
                trace=trace,
            )
            result, trace = self.contract.finalize_trace(result, trace, t_start)
            return result

        # --- Étape 2 : expansion BFS dans le graphe ---
        candidates_raw: dict[str, tuple[float, list[str], int]] = {}
        # {concept: (plausibility, supporting_facts, depth)}

        for seed in seed_concepts:
            self._bfs_expand(seed, candidates_raw, fact)

        trace.intermediate_steps.append(f"candidates_before_filter:{len(candidates_raw)}")
        trace.intermediate_steps.append(f"bfs_depth:{self.max_depth}")

        # --- Étape 3 : filtrage et classement top-K ---
        filtered = {
            c: v for c, v in candidates_raw.items()
            if v[0] >= NE_MIN_PLAUSIBILITY and c not in seed_concepts
        }
        sorted_candidates = sorted(
            filtered.items(), key=lambda x: x[1][0], reverse=True
        )[:self.top_k]

        hypotheses = [
            Hypothesis(
                concept=concept,
                plausibility=round(pla, 4),
                supporting_facts=supporting,
                depth=depth,
            )
            for concept, (pla, supporting, depth) in sorted_candidates
        ]

        plausibility_scores = {h.concept: h.plausibility for h in hypotheses}
        trace.intermediate_steps.append(f"top_k_selected:{len(hypotheses)}")

        result = HypothesisSet(
            candidates=hypotheses,
            plausibility_scores=plausibility_scores,
            expansion_depth=self.max_depth,
            ts_ns=t_start,
            trace=trace,
        )

        # --- Phase 3 (P0-A) : vérification du contrat via finalize_trace ---
        result, trace = self.contract.finalize_trace(result, trace, t_start)

        return result

    # ------------------------------------------------------------------
    # Méthodes internes
    # ------------------------------------------------------------------

    def _extract_seeds(self, fact: PerceptualFact) -> list[str]:
        """Extraire les concepts d'ancrage depuis les propriétés du PerceptualFact."""
        seeds: list[str] = []
        p = fact.properties

        if p.get("type") == "text":
            # On utilise le premier token et la langue comme amorces
            first = p.get("first_token", "")
            lang = p.get("language_hint", "")
            if first:
                seeds.append(first)
            if lang and lang != "unknown":
                seeds.append(f"lang:{lang}")
            # Présence de question ou négation comme concepts
            if p.get("has_question"):
                seeds.append("query")
            if p.get("has_negation"):
                seeds.append("negation")

        elif p.get("type") == "json":
            seeds.extend(p.get("keys", [])[:3])

        elif p.get("type") == "event":
            seeds.append("event")

        # Garder uniquement les seeds présentes dans le graphe
        known = [s for s in seeds if s in self.graph._graph]
        return known if known else seeds[:2]  # même inconnus si graphe vide

    def _bfs_expand(
        self,
        seed: str,
        candidates: dict[str, tuple[float, list[str], int]],
        fact: PerceptualFact,
    ) -> None:
        """BFS borné depuis un nœud seed."""
        if seed not in self.graph._graph:
            return

        queue: deque[tuple[str, float, list[str], int]] = deque()
        queue.append((seed, 1.0, [seed], 0))
        visited: set[str] = {seed}

        while queue:
            node, plausibility, path, depth = queue.popleft()
            if depth >= self.max_depth:
                continue

            for neighbor, weight in self.graph.neighbors(node).items():
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_plausibility = plausibility * weight * fact.confidence
                new_path = path + [neighbor]

                # Accumulation : garder la meilleure voie vers ce concept
                existing = candidates.get(neighbor)
                if existing is None or new_plausibility > existing[0]:
                    candidates[neighbor] = (new_plausibility, new_path, depth + 1)

                queue.append((neighbor, new_plausibility, new_path, depth + 1))
