#!/usr/bin/env python3
"""
lucy_arc3_eval.py — LuCY ARC-AGI Evaluation Script
=====================================================
Évalue le kernel cognitif LuCY sur les puzzles ARC-AGI (Abstract Reasoning Corpus).

Protocole :
  1. Télécharger les puzzles ARC depuis GitHub public (fchollet/ARC-AGI)
  2. Encoder chaque puzzle en stimulus textuel pour LuCYKernel
  3. Exécuter run_cycle() et analyser la décision cognitive
  4. Scorer : confidence + consensus_score + conflict_ratio
  5. Logger forensic JSONL + summary JSON
  6. Produire rapport dans LuCY/logs/arc3_eval/

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

import json
import os
import sys
import time
import math
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
LUCY_ROOT = SCRIPT_DIR.parent
SRC_DIR = LUCY_ROOT / "src"
LOG_DIR = LUCY_ROOT / "logs" / "arc3_eval"
LOG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SRC_DIR))

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ARC_GITHUB_API_BASE = "https://api.github.com/repos/fchollet/ARC-AGI/contents/data"
ARC_RAW_BASE = "https://raw.githubusercontent.com/fchollet/ARC-AGI/master/data"
MAX_TRAINING_PUZZLES = 50   # Limite pour durée raisonnable
MAX_EVAL_PUZZLES = 20       # Puzzles d'évaluation
REQUEST_TIMEOUT = 20
EVAL_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
FORENSIC_LOG = LOG_DIR / f"lucy_arc3_forensic_{EVAL_TIMESTAMP}.jsonl"
SUMMARY_LOG = LOG_DIR / f"lucy_arc3_summary_{EVAL_TIMESTAMP}.json"

# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = REQUEST_TIMEOUT) -> Any:
    """Télécharge et parse JSON depuis une URL publique."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LuCY-ARC3-Eval/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_raw(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """Télécharge du texte brut depuis une URL publique."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LuCY-ARC3-Eval/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Chargement puzzles ARC depuis GitHub
# ---------------------------------------------------------------------------

def list_arc_puzzles(subset: str = "training") -> list[str]:
    """Retourne la liste des noms de fichiers JSON pour un sous-ensemble ARC.

    Args:
        subset: 'training' ou 'evaluation'

    Returns:
        Liste de noms de fichiers (ex: ['00d62c1b.json', ...])
    """
    url = f"{ARC_GITHUB_API_BASE}/{subset}"
    print(f"[DEBUG] Fetching puzzle list: {url}")
    try:
        entries = _fetch_json(url)
        names = [e["name"] for e in entries if e.get("name", "").endswith(".json")]
        print(f"[DEBUG] Found {len(names)} puzzles in {subset}")
        return names
    except Exception as exc:
        print(f"[ERROR] Cannot list puzzles from GitHub: {exc}")
        return []


def load_arc_puzzle(name: str, subset: str = "training") -> Optional[dict]:
    """Charge un puzzle ARC depuis GitHub raw.

    Args:
        name: Nom du fichier (ex: '00d62c1b.json')
        subset: 'training' ou 'evaluation'

    Returns:
        Dict avec 'train' et 'test' keys, ou None si erreur
    """
    url = f"{ARC_RAW_BASE}/{subset}/{name}"
    try:
        raw = _fetch_raw(url)
        puzzle = json.loads(raw)
        return puzzle
    except Exception as exc:
        print(f"[ERROR] Cannot load puzzle {name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Encodage puzzle → stimulus textuel pour LuCY
# ---------------------------------------------------------------------------

def encode_grid(grid: list[list[int]]) -> str:
    """Convertit une grille ARC en représentation textuelle compacte."""
    rows = []
    for row in grid:
        rows.append(" ".join(str(v) for v in row))
    return "\n".join(rows)


def encode_arc_puzzle_as_stimulus(puzzle: dict, puzzle_id: str) -> str:
    """Encode un puzzle ARC en stimulus textuel pour LuCYKernel.run_cycle().

    Format : description structurée des exemples d'entraînement et de la question.
    LuCY doit analyser le pattern et proposer une décision cognitive.
    """
    parts = [f"PUZZLE_ID: {puzzle_id}"]
    parts.append("TASK: Abstract pattern recognition and transformation.")
    parts.append("INSTRUCTION: Analyze the input/output transformations. Identify the rule.")

    # Exemples d'entraînement
    train_examples = puzzle.get("train", [])
    parts.append(f"\nTRAINING_EXAMPLES: {len(train_examples)}")
    for i, ex in enumerate(train_examples[:3]):  # Max 3 exemples pour concision
        inp = encode_grid(ex.get("input", []))
        out = encode_grid(ex.get("output", []))
        rows_in = len(ex.get("input", []))
        cols_in = len(ex["input"][0]) if ex.get("input") else 0
        rows_out = len(ex.get("output", []))
        cols_out = len(ex["output"][0]) if ex.get("output") else 0
        parts.append(f"\nEXAMPLE_{i+1}:")
        parts.append(f"  INPUT ({rows_in}x{cols_in}):\n{inp}")
        parts.append(f"  OUTPUT ({rows_out}x{cols_out}):\n{out}")

    # Question de test
    test_cases = puzzle.get("test", [])
    if test_cases:
        test_input = encode_grid(test_cases[0].get("input", []))
        rows_t = len(test_cases[0].get("input", []))
        cols_t = len(test_cases[0]["input"][0]) if test_cases[0].get("input") else 0
        parts.append(f"\nTEST_INPUT ({rows_t}x{cols_t}):\n{test_input}")
        parts.append("\nQUESTION: What is the expected output transformation?")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Métriques ARC spécifiques
# ---------------------------------------------------------------------------

def compute_arc_metrics(decision, puzzle: dict, puzzle_id: str) -> dict:
    """Calcule les métriques d'évaluation pour un puzzle ARC.

    Note : LuCY ne génère pas de grilles de sortie — il produit des décisions
    cognitives. On mesure donc la qualité du raisonnement, pas la réponse exacte.

    Métriques :
      - cognitive_confidence : confiance de la décision [0,1]
      - consensus_score : accord inter-fonctions [0,1]
      - conflict_penalty : pénalité si conflit détecté
      - composite_score : score agrégé
      - reasoning_quality : évaluation qualitative
    """
    confidence = float(decision.confidence) if math.isfinite(decision.confidence) else 0.0
    consensus = float(decision.consensus_score) if math.isfinite(decision.consensus_score) else 0.0
    conflict_penalty = 0.3 if decision.conflict_detected else 0.0

    # Score composite : confiance × consensus - pénalité conflit
    composite = max(0.0, confidence * consensus - conflict_penalty)
    composite = min(1.0, composite)

    # Complexité du puzzle (heuristique)
    train_examples = puzzle.get("train", [])
    grid_sizes = []
    for ex in train_examples:
        inp = ex.get("input", [[]])
        rows = len(inp)
        cols = len(inp[0]) if inp else 0
        grid_sizes.append(rows * cols)
    avg_grid_size = sum(grid_sizes) / len(grid_sizes) if grid_sizes else 0
    complexity_class = "small" if avg_grid_size < 25 else ("medium" if avg_grid_size < 100 else "large")

    # Qualité du raisonnement (classification heuristique)
    if composite >= 0.5:
        reasoning_quality = "ADEQUATE"
    elif composite >= 0.3:
        reasoning_quality = "PARTIAL"
    else:
        reasoning_quality = "INSUFFICIENT"

    return {
        "puzzle_id": puzzle_id,
        "cognitive_confidence": round(confidence, 6),
        "consensus_score": round(consensus, 6),
        "conflict_detected": decision.conflict_detected,
        "conflict_description": decision.conflict_description or "",
        "dominant_function": decision.dominant_function or "",
        "action": decision.action or "",
        "conflict_penalty": round(conflict_penalty, 6),
        "composite_score": round(composite, 6),
        "reasoning_quality": reasoning_quality,
        "complexity_class": complexity_class,
        "avg_grid_size": round(avg_grid_size, 1),
        "num_train_examples": len(train_examples),
    }


# ---------------------------------------------------------------------------
# Logger forensic
# ---------------------------------------------------------------------------

def log_forensic(event: dict) -> None:
    """Append une entrée dans le journal forensic JSONL."""
    event["ts_utc"] = datetime.now(timezone.utc).isoformat()
    event["ts_ns"] = time.time_ns()
    with open(FORENSIC_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Évaluation principale
# ---------------------------------------------------------------------------

def evaluate_subset(
    kernel,
    subset: str,
    max_puzzles: int,
    puzzle_names: list[str],
) -> list[dict]:
    """Évalue LuCY sur un sous-ensemble de puzzles ARC.

    Args:
        kernel: Instance LuCYKernel
        subset: 'training' ou 'evaluation'
        max_puzzles: Nombre maximum de puzzles à traiter
        puzzle_names: Liste des noms de fichiers disponibles

    Returns:
        Liste de résultats par puzzle
    """
    results = []
    names_to_process = puzzle_names[:max_puzzles]
    total = len(names_to_process)
    print(f"\n[INFO] Evaluating {total} {subset} puzzles...")

    for idx, name in enumerate(names_to_process):
        puzzle_id = name.replace(".json", "")
        pct = int((idx / total) * 100)
        print(f"  [{pct:3d}%] {subset}/{puzzle_id} ({idx+1}/{total})", end=" ", flush=True)

        # Chargement puzzle
        puzzle = load_arc_puzzle(name, subset)
        if puzzle is None:
            log_forensic({
                "event": "PUZZLE_LOAD_ERROR",
                "subset": subset,
                "puzzle_id": puzzle_id,
            })
            print("→ LOAD_ERROR")
            continue

        # Encodage en stimulus
        stimulus = encode_arc_puzzle_as_stimulus(puzzle, puzzle_id)
        stimulus_hash = hashlib.sha256(stimulus.encode()).hexdigest()[:16]

        # Exécution kernel cognitif
        t_start = time.time_ns()
        try:
            decision = kernel.run_cycle(stimulus=stimulus)
        except Exception as exc:
            log_forensic({
                "event": "KERNEL_ERROR",
                "subset": subset,
                "puzzle_id": puzzle_id,
                "error": str(exc),
            })
            print(f"→ KERNEL_ERROR: {exc}")
            continue
        t_end = time.time_ns()
        duration_ms = (t_end - t_start) / 1_000_000

        # Calcul métriques
        metrics = compute_arc_metrics(decision, puzzle, puzzle_id)
        metrics["subset"] = subset
        metrics["duration_ms"] = round(duration_ms, 2)
        metrics["stimulus_hash"] = stimulus_hash
        metrics["stimulus_len"] = len(stimulus)

        # Log forensic
        log_forensic({
            "event": "PUZZLE_EVALUATED",
            **metrics,
        })

        results.append(metrics)
        q = metrics["reasoning_quality"]
        score = metrics["composite_score"]
        print(f"→ {q} (score={score:.3f}, conf={metrics['cognitive_confidence']:.3f})")

        # Petite pause pour éviter rate-limit GitHub
        time.sleep(0.05)

    return results


def compute_summary(results: list[dict], subset: str) -> dict:
    """Calcule les statistiques agrégées pour un sous-ensemble."""
    if not results:
        return {"subset": subset, "count": 0, "error": "NO_RESULTS"}

    scores = [r["composite_score"] for r in results]
    confidences = [r["cognitive_confidence"] for r in results]
    consensus_scores = [r["consensus_score"] for r in results]

    quality_counts = {"ADEQUATE": 0, "PARTIAL": 0, "INSUFFICIENT": 0}
    conflict_count = 0
    for r in results:
        quality_counts[r.get("reasoning_quality", "INSUFFICIENT")] = \
            quality_counts.get(r.get("reasoning_quality", "INSUFFICIENT"), 0) + 1
        if r.get("conflict_detected"):
            conflict_count += 1

    n = len(scores)
    mean_score = sum(scores) / n
    mean_confidence = sum(confidences) / n
    mean_consensus = sum(consensus_scores) / n

    # Variance
    var_score = sum((s - mean_score) ** 2 for s in scores) / n
    std_score = math.sqrt(var_score)

    return {
        "subset": subset,
        "count": n,
        "mean_composite_score": round(mean_score, 6),
        "std_composite_score": round(std_score, 6),
        "min_composite_score": round(min(scores), 6),
        "max_composite_score": round(max(scores), 6),
        "mean_cognitive_confidence": round(mean_confidence, 6),
        "mean_consensus_score": round(mean_consensus, 6),
        "quality_distribution": quality_counts,
        "conflict_rate": round(conflict_count / n, 4),
        "adequate_rate": round(quality_counts["ADEQUATE"] / n, 4),
        "partial_rate": round(quality_counts["PARTIAL"] / n, 4),
        "insufficient_rate": round(quality_counts["INSUFFICIENT"] / n, 4),
    }


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def main() -> None:
    """Exécute l'évaluation LuCY sur ARC-AGI et produit le rapport."""
    print("=" * 70)
    print("LuCY ARC-AGI Evaluation")
    print(f"Timestamp : {EVAL_TIMESTAMP}")
    print(f"CERTIFIED_100=false | unique_human_proven=false | DEBUG=true")
    print("=" * 70)

    log_forensic({"event": "EVAL_START", "timestamp": EVAL_TIMESTAMP,
                  "max_training": MAX_TRAINING_PUZZLES,
                  "max_eval": MAX_EVAL_PUZZLES,
                  "certified_100": False,
                  "unique_human_proven": False})

    # Initialisation kernel
    print("\n[INFO] Initializing LuCYKernel...")
    from lucy.kernel.lucy_kernel import LuCYKernel
    kernel = LuCYKernel()
    print("[INFO] LuCYKernel initialized OK")
    log_forensic({"event": "KERNEL_INIT", "status": "OK"})

    all_results = []
    summaries = {}

    # --- Sous-ensemble TRAINING ---
    training_names = list_arc_puzzles("training")
    if not training_names:
        print("[ERROR] Cannot fetch training puzzle list — aborting")
        log_forensic({"event": "ABORT", "reason": "NO_TRAINING_PUZZLES"})
        sys.exit(1)

    training_results = evaluate_subset(
        kernel, "training", MAX_TRAINING_PUZZLES, training_names
    )
    all_results.extend(training_results)
    summaries["training"] = compute_summary(training_results, "training")

    # --- Sous-ensemble EVALUATION ---
    eval_names = list_arc_puzzles("evaluation")
    if eval_names:
        eval_results = evaluate_subset(
            kernel, "evaluation", MAX_EVAL_PUZZLES, eval_names
        )
        all_results.extend(eval_results)
        summaries["evaluation"] = compute_summary(eval_results, "evaluation")
    else:
        print("[WARNING] Cannot fetch evaluation puzzle list — skipping")
        log_forensic({"event": "EVAL_SUBSET_SKIP", "subset": "evaluation"})

    # --- Résumé global ---
    global_scores = [r["composite_score"] for r in all_results]
    global_summary = {
        "eval_timestamp": EVAL_TIMESTAMP,
        "certified_100": False,
        "unique_human_proven": False,
        "debug_mode": True,
        "total_puzzles_evaluated": len(all_results),
        "max_training_puzzles": MAX_TRAINING_PUZZLES,
        "max_eval_puzzles": MAX_EVAL_PUZZLES,
        "global_mean_composite_score": round(sum(global_scores) / len(global_scores), 6) if global_scores else 0.0,
        "arc_exact_match_rate": 0.0,  # LuCY ne génère pas de grilles exactes — N/A
        "arc_exact_match_note": "LuCY produces cognitive decisions, not grid outputs. Exact match rate = N/A for this evaluation.",
        "subsets": summaries,
        "forensic_log": str(FORENSIC_LOG),
        "summary_log": str(SUMMARY_LOG),
        "interpretation": {
            "composite_score_meaning": "Weighted cognitive quality: confidence × consensus - conflict_penalty",
            "adequate_threshold": "composite_score >= 0.5",
            "partial_threshold": "0.3 <= composite_score < 0.5",
            "insufficient_threshold": "composite_score < 0.3",
        }
    }

    # Écriture summary JSON
    with open(SUMMARY_LOG, "w", encoding="utf-8") as f:
        json.dump(global_summary, f, indent=2, ensure_ascii=False)

    log_forensic({"event": "EVAL_END", "total_evaluated": len(all_results),
                  "global_mean_score": global_summary["global_mean_composite_score"]})

    # --- Affichage résultats ---
    print("\n" + "=" * 70)
    print("RÉSULTATS FINAUX")
    print("=" * 70)
    for subset_name, s in summaries.items():
        print(f"\n[{subset_name.upper()}]")
        print(f"  Puzzles évalués : {s['count']}")
        print(f"  Score moyen composite : {s['mean_composite_score']:.4f} (±{s['std_composite_score']:.4f})")
        print(f"  Confiance cognitive moy : {s['mean_cognitive_confidence']:.4f}")
        print(f"  Consensus moyen : {s['mean_consensus_score']:.4f}")
        print(f"  Taux conflits : {s['conflict_rate']:.1%}")
        print(f"  Distribution qualité :")
        print(f"    ADEQUATE      : {s['quality_distribution']['ADEQUATE']:3d} ({s['adequate_rate']:.1%})")
        print(f"    PARTIAL       : {s['quality_distribution']['PARTIAL']:3d} ({s['partial_rate']:.1%})")
        print(f"    INSUFFICIENT  : {s['quality_distribution']['INSUFFICIENT']:3d} ({s['insufficient_rate']:.1%})")

    print(f"\n[GLOBAL]")
    print(f"  Total puzzles évalués : {global_summary['total_puzzles_evaluated']}")
    print(f"  Score composite global : {global_summary['global_mean_composite_score']:.4f}")
    print(f"\n[LOGS]")
    print(f"  Forensic : {FORENSIC_LOG}")
    print(f"  Summary  : {SUMMARY_LOG}")
    print("\nCERTIFIED_100=false | unique_human_proven=false")
    print("=" * 70)


if __name__ == "__main__":
    main()
