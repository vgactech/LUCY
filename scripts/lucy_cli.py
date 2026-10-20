"""
lucy_cli.py — Interface en ligne de commande LuCY

Projet : LuCY (Language Unit for Cognitive Yield)
Module : scripts / lucy_cli
Auteur : LuCY Project

Commandes disponibles :
  lucy run   <texte>          — Exécuter un cycle cognitif complet
  lucy state                  — Afficher l'état interne actuel
  lucy learn <op> <feedback>  — Appliquer un feedback à un opérateur
  lucy history [N]            — Afficher les N derniers cycles
  lucy weights                — Afficher les poids actuels des opérateurs
  lucy forensic [N]           — Afficher les N dernières entrées forensic

Mode DEBUG actif (toujours) — CERTIFIED_100=false | unique_human_proven=false
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Résoudre src/ depuis scripts/
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPTS_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from lucy.kernel.lucy_kernel import LuCYKernel  # noqa: E402

# Répertoire de données par défaut
_DEFAULT_DATA = _SCRIPTS_DIR.parent / "data" / "lucy_cli"

# ─────────────────────────────────────────────────────────────────────────────
# Kernel singleton (paresseux)
# ─────────────────────────────────────────────────────────────────────────────

_kernel: LuCYKernel | None = None


def _get_kernel(data_dir: Path | None = None) -> LuCYKernel:
    global _kernel
    if _kernel is None:
        d = data_dir or _DEFAULT_DATA
        d.mkdir(parents=True, exist_ok=True)
        _kernel = LuCYKernel(data_dir=d, debug=True)
    return _kernel


# ─────────────────────────────────────────────────────────────────────────────
# Commandes
# ─────────────────────────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> None:
    """lucy run <texte> — Exécuter un cycle cognitif complet."""
    text = " ".join(args.text) if args.text else ""
    if not text.strip():
        print("[LuCY] ERREUR : texte vide — fournir un stimulus.", file=sys.stderr)
        sys.exit(1)

    k = _get_kernel()
    decision = k.run_cycle(text)

    print("=" * 60)
    print("LuCY — Résultat du cycle cognitif")
    print("=" * 60)
    print(f"  Action       : {decision.action}")
    print(f"  Confidence   : {decision.confidence:.3f}")
    print(f"  Consensus    : {decision.consensus_score:.3f}")
    print(f"  Conflit      : {decision.conflict_detected}")
    if decision.conflict_detected:
        print(f"  Détail       : {decision.conflict_description}")
    print(f"  Dominant     : {decision.dominant_function or 'N/A'}")
    print(f"  Cycle #      : {k.state.cycle_count}")
    print("=" * 60)

    if args.json:
        print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))


def cmd_state(args: argparse.Namespace) -> None:
    """lucy state — Afficher l'état interne."""
    k = _get_kernel()
    s = k.state
    print("=" * 60)
    print("LuCY — État interne")
    print("=" * 60)
    print(f"  Cycles exécutés     : {s.cycle_count}")
    print(f"  Phase courante      : {s.active_phase}")
    print(f"  Dernière action     : {s.last_action or 'aucune'}")
    print(f"  Faits perceptuels   : {len(s.perceptual_buffer)}")
    print(f"  Impressions SI      : {len(s.subjective_impressions)}")
    print(f"  Patterns NI         : {len(s.abstract_patterns)}")
    print(f"  CERTIFIED_100       : {s.certified_100}")
    print(f"  unique_human_proven : {s.unique_human_proven}")
    print(f"  Mémoire travail     : {k.working.size()} entrées")
    print("=" * 60)

    if args.json:
        print(json.dumps({
            "cycle_count": s.cycle_count,
            "current_phase": s.active_phase,
            "last_action": s.last_action,
            "perceptual_buffer_size": len(s.perceptual_buffer),
            "certified_100": s.certified_100,
            "unique_human_proven": s.unique_human_proven,
            "working_memory_size": k.working.size(),
        }, indent=2))


def cmd_learn(args: argparse.Namespace) -> None:
    """lucy learn <op> <feedback> — Appliquer un feedback."""
    op = args.operator.upper()
    valid_ops = ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]
    if op not in valid_ops:
        print(f"[LuCY] ERREUR : opérateur invalide '{op}'. Valides : {valid_ops}", file=sys.stderr)
        sys.exit(1)

    try:
        fb = float(args.feedback)
    except ValueError:
        print(f"[LuCY] ERREUR : feedback doit être un nombre (ex : +1.0 ou -0.5).", file=sys.stderr)
        sys.exit(1)

    if not (-1.0 <= fb <= 1.0):
        print(f"[LuCY] AVERTISSEMENT : feedback {fb} hors [-1.0, +1.0] — il sera borné.")

    k = _get_kernel()
    old_w = k.procedural.get_weight(op)
    new_w = k.learn(op, fb)
    delta = new_w - old_w

    print(f"[LuCY] learn {op} feedback={fb:+.3f}")
    print(f"  Poids avant : {old_w:.4f}")
    print(f"  Poids après : {new_w:.4f}  (Δ={delta:+.4f})")

    if args.json:
        print(json.dumps({
            "operator": op,
            "feedback": fb,
            "weight_before": old_w,
            "weight_after": new_w,
            "delta": delta,
        }, indent=2))


def cmd_history(args: argparse.Namespace) -> None:
    """lucy history [N] — Afficher les N derniers cycles en mémoire de travail."""
    n = args.count if hasattr(args, "count") and args.count else 5
    k = _get_kernel()
    entries = k.working.last(n)
    print(f"[LuCY] Historique — {len(entries)} dernières entrées (sur {k.working.size()} total)")
    for i, e in enumerate(entries):
        ts = e.get("ts_ns", "?")
        etype = e.get("entry_type", "?")
        cycle = e.get("cycle_id", "?")
        print(f"  [{i+1:02d}] type={etype} cycle={cycle} ts_ns={ts}")

    if args.json:
        print(json.dumps(entries, indent=2, default=str, ensure_ascii=False))


def cmd_weights(args: argparse.Namespace) -> None:
    """lucy weights — Afficher les poids des 8 opérateurs."""
    k = _get_kernel()
    weights = k.procedural.all_weights()
    updates = k.procedural.recent_updates(5)
    print("=" * 50)
    print("LuCY — Poids des opérateurs")
    print("=" * 50)
    for op in ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]:
        w = weights.get(op, 0.0)
        bar = "█" * int(w * 10)
        print(f"  {op}  {w:.4f}  {bar}")
    print("=" * 50)
    print(f"  Dernières mises à jour : {len(updates)}")
    for u in updates[-3:]:
        print(f"    {u['function']} feedback={u['feedback']:+.3f}  {u['old_weight']:.4f}→{u['new_weight']:.4f}")

    if args.json:
        print(json.dumps(weights, indent=2))


def cmd_forensic(args: argparse.Namespace) -> None:
    """lucy forensic [N] — Afficher les N dernières entrées forensic."""
    n = args.count if hasattr(args, "count") and args.count else 10
    log_path = Path("LuCY/logs/forensic/lucy_forensic.jsonl")
    if not log_path.exists():
        # Tenter un chemin relatif
        log_path = _SCRIPTS_DIR.parent / "logs" / "forensic" / "lucy_forensic.jsonl"

    if not log_path.exists():
        print(f"[LuCY] Log forensic introuvable : {log_path}", file=sys.stderr)
        print("  Exécuter d'abord `lucy run` pour générer des logs.")
        return

    lines: list[str] = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    recent = lines[-n:]
    print(f"[LuCY] Forensic — {len(recent)} dernières entrées (sur {len(lines)} total)")
    print(f"  Fichier : {log_path}")
    print("-" * 60)
    for raw in recent:
        try:
            entry = json.loads(raw)
            etype = entry.get("event_type", entry.get("type", "?"))
            ts = entry.get("ts_ns", "?")
            phase = entry.get("phase", "")
            print(f"  [{etype}] phase={phase} ts_ns={ts}")
        except json.JSONDecodeError:
            print(f"  [PARSE_ERROR] {raw[:80]}")

    if args.json and recent:
        entries = []
        for raw in recent:
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                entries.append({"raw": raw})
        print(json.dumps(entries, indent=2, default=str, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────────────
# Parser principal
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lucy",
        description="LuCY — Language Unit for Cognitive Yield (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python scripts/lucy_cli.py run "The sky is blue today"
  python scripts/lucy_cli.py state
  python scripts/lucy_cli.py learn NE +0.5
  python scripts/lucy_cli.py weights
  python scripts/lucy_cli.py forensic 20
  python scripts/lucy_cli.py history 5
""",
    )
    parser.add_argument("--json", action="store_true", help="Sortie JSON machine-lisible")
    parser.add_argument(
        "--data-dir", type=Path, default=None,
        help="Répertoire des données LuCY (défaut : LuCY/data/lucy_cli/)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Exécuter un cycle cognitif complet")
    p_run.add_argument("text", nargs="+", help="Texte stimulus")
    p_run.set_defaults(func=cmd_run)

    # state
    p_state = sub.add_parser("state", help="Afficher l'état interne LuCY")
    p_state.set_defaults(func=cmd_state)

    # learn
    p_learn = sub.add_parser("learn", help="Appliquer un feedback à un opérateur")
    p_learn.add_argument("operator", help="Opérateur cible : SE SI NE NI TE TI FE FI")
    p_learn.add_argument("feedback", help="Feedback [-1.0 … +1.0]")
    p_learn.set_defaults(func=cmd_learn)

    # history
    p_hist = sub.add_parser("history", help="Afficher l'historique des cycles")
    p_hist.add_argument("count", nargs="?", type=int, default=5, help="Nombre d'entrées (défaut 5)")
    p_hist.set_defaults(func=cmd_history)

    # weights
    p_w = sub.add_parser("weights", help="Afficher les poids des opérateurs")
    p_w.set_defaults(func=cmd_weights)

    # forensic
    p_f = sub.add_parser("forensic", help="Afficher le log forensic")
    p_f.add_argument("count", nargs="?", type=int, default=10, help="Nombre d'entrées (défaut 10)")
    p_f.set_defaults(func=cmd_forensic)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.data_dir:
        # Injecter le data_dir dans le kernel lazy
        global _kernel
        _kernel = None
        _DEFAULT_DATA_OVERRIDE = args.data_dir
        # Monkey-patch pour passer le data_dir
        original_get = _get_kernel
        def patched_get(data_dir=None):
            return original_get(data_dir=args.data_dir)
        import lucy_cli as _self_mod
        _self_mod._get_kernel = patched_get

    args.func(args)


if __name__ == "__main__":
    main()
