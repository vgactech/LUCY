#!/usr/bin/env python3
"""
Script de lecture et d'analyse du log forensic perpétuel LuCY.

Usage :
    python scripts/lucy_forensic_reader.py [--last N] [--event EVENT_TYPE] [--stats]
"""

import json
import sys
import argparse
from pathlib import Path

FORENSIC_FILE = Path(__file__).resolve().parent.parent / "logs" / "forensic" / "lucy_forensic.jsonl"


def load_entries(filepath: Path) -> list[dict]:
    if not filepath.exists():
        print(f"[WARN] Fichier forensic introuvable : {filepath}")
        return []
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] Ligne {i} non parseable : {e}")
    return entries


def print_entry(entry: dict) -> None:
    ts = entry.get("ts_iso", "?")
    etype = entry.get("event_type", "?")
    phase = entry.get("phase", "")
    func = entry.get("function", "")
    cycle = entry.get("cycle_id", "")
    summary = entry.get("output_summary", {})
    print(f"  [{ts}] {etype:12s} | {phase:10s} | {func:4s} | {cycle:20s} | {summary}")


def print_stats(entries: list[dict]) -> None:
    from collections import Counter
    total = len(entries)
    by_type = Counter(e.get("event_type", "?") for e in entries)
    by_func = Counter(e.get("function", "") for e in entries if e.get("function"))
    by_phase = Counter(e.get("phase", "") for e in entries if e.get("phase"))

    print(f"\n=== STATISTIQUES LOG FORENSIC LuCY ===")
    print(f"  Fichier    : {FORENSIC_FILE}")
    print(f"  Total      : {total} entrées")
    print(f"\n  Par type d'événement :")
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {k:20s} : {v}")
    print(f"\n  Par fonction :")
    for k, v in sorted(by_func.items(), key=lambda x: -x[1]):
        print(f"    {k:6s} : {v}")
    print(f"\n  Par phase :")
    for k, v in sorted(by_phase.items(), key=lambda x: -x[1]):
        print(f"    {k:12s} : {v}")

    errors = [e for e in entries if e.get("event_type") == "ERROR"]
    print(f"\n  Erreurs    : {len(errors)}")
    if errors:
        for e in errors[-5:]:
            print(f"    {e.get('ts_iso')} | {e.get('output_summary', {}).get('message', '?')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lecteur log forensic LuCY")
    parser.add_argument("--last", type=int, default=20, help="Afficher les N dernières entrées")
    parser.add_argument("--event", type=str, default="", help="Filtrer par event_type")
    parser.add_argument("--stats", action="store_true", help="Afficher les statistiques")
    parser.add_argument("--all", action="store_true", help="Afficher toutes les entrées")
    args = parser.parse_args()

    entries = load_entries(FORENSIC_FILE)
    if not entries:
        print("Aucune entrée dans le log forensic.")
        return

    if args.stats:
        print_stats(entries)
        return

    filtered = entries
    if args.event:
        filtered = [e for e in entries if e.get("event_type") == args.event.upper()]

    if not args.all:
        filtered = filtered[-args.last:]

    print(f"\n=== LOG FORENSIC LuCY — {len(filtered)} entrée(s) affichée(s) / {len(entries)} total ===\n")
    for entry in filtered:
        print_entry(entry)


if __name__ == "__main__":
    main()
