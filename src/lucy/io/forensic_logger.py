#!/usr/bin/env python3
"""
# **************************************************************************
# lucy_forensic_logger.py — Log forensic perpétuel LuCY
#
# Projet : LuCY (Language Unit for Cognitive Yield)
# Module : io / forensic
# Auteur : LuCY Project
#
# RÈGLE ABSOLUE : ce fichier est APPEND-ONLY. Ne jamais tronquer,
# ne jamais supprimer lucy_forensic.jsonl.
# Toute entrée écrite est permanente.
#
# CERTIFIED_100=false | unique_human_proven=false
# Mode DEBUG actif
# ************************************************************************
"""

import json
import os
import time
import hashlib
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FORENSIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs" / "forensic"
FORENSIC_FILE = FORENSIC_DIR / "lucy_forensic.jsonl"

DEBUG = os.environ.get("LUCY_DEBUG", "true").lower() != "false"

CERTIFIED_100 = False           # INVARIANT — ne jamais mettre à True sans preuve
UNIQUE_HUMAN_PROVEN = False     # INVARIANT — ne jamais mettre à True sans preuve


# ---------------------------------------------------------------------------
# Classe ForensicLogger
# ---------------------------------------------------------------------------

class ForensicLogger:
    """Logger forensic append-only pour LuCY.

    Chaque entrée est un objet JSON sur une seule ligne (JSON Lines).
    Le fichier lucy_forensic.jsonl ne doit jamais être tronqué ni supprimé.
    """

    def __init__(self, component: str = "lucy") -> None:
        self.component = component
        FORENSIC_DIR.mkdir(parents=True, exist_ok=True)

    def _ts_ns(self) -> int:
        """Horodatage nanoseconde."""
        return time.time_ns()

    def _ts_iso(self, ts_ns: int) -> str:
        """ISO 8601 depuis ns."""
        ts_s = ts_ns / 1e9
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts_s, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f000Z"
        )

    def _state_hash(self, data: Any) -> str:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]

    def log(
        self,
        event_type: str,
        phase: str = "",
        function: str = "",
        cycle_id: str = "",
        input_data: Any = None,
        output_summary: Any = None,
        duration_ns: int = 0,
        extra: dict | None = None,
    ) -> dict:
        """Écrire une entrée dans le log forensic.

        Args:
            event_type: INIT | CYCLE_START | PERCEIVE | JUDGE | ARBITRATE | LEARN | ERROR
            phase: phase du cycle courant
            function: code de la fonction (SE, SI, NE, NI, TE, TI, FE, FI)
            cycle_id: identifiant unique du cycle
            input_data: résumé des entrées (jamais les données brutes sensibles)
            output_summary: résumé des sorties
            duration_ns: durée de l'opération en nanosecondes
            extra: champs additionnels

        Returns:
            L'entrée JSON écrite.
        """
        ts = self._ts_ns()
        entry = {
            "ts_ns": ts,
            "ts_iso": self._ts_iso(ts),
            "event_type": event_type,
            "component": self.component,
            "phase": phase,
            "function": function,
            "cycle_id": cycle_id or ("lucy_c" + uuid.uuid4().hex[:8]),
            "input_hash": self._state_hash(input_data) if input_data else None,
            "output_summary": output_summary or {},
            "duration_ns": duration_ns,
            "debug": DEBUG,
            "certified_100": CERTIFIED_100,
            "unique_human_proven": UNIQUE_HUMAN_PROVEN,
        }
        if extra:
            entry.update(extra)

        # Écriture append-only — la seule opération autorisée sur ce fichier
        with open(FORENSIC_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        if DEBUG:
            print(f"[FORENSIC] {event_type} | {phase}/{function} | {self._ts_iso(ts)}")

        return entry

    def log_init(self, project_version: str = "0.0.1") -> dict:
        """Entrée d'initialisation du système."""
        return self.log(
            event_type="INIT",
            phase="BOOT",
            output_summary={
                "message": "LuCY forensic logger initialized",
                "project": "LuCY",
                "version": project_version,
                "forensic_file": str(FORENSIC_FILE),
                "append_only": True,
            },
            extra={"project_version": project_version},
        )

    def log_cycle_start(self, cycle_id: str, stimulus_type: str) -> dict:
        """Début d'un cycle cognitif."""
        return self.log(
            event_type="CYCLE_START",
            phase="INIT",
            cycle_id=cycle_id,
            output_summary={"stimulus_type": stimulus_type},
        )

    def log_perceive(
        self,
        function: str,
        cycle_id: str,
        input_data: Any,
        output: Any,
        duration_ns: int,
    ) -> dict:
        """Enregistrement d'une phase PERCEIVE."""
        return self.log(
            event_type="PERCEIVE",
            phase="PERCEIVE",
            function=function,
            cycle_id=cycle_id,
            input_data=input_data,
            output_summary=output,
            duration_ns=duration_ns,
        )

    def log_judge(
        self,
        function: str,
        cycle_id: str,
        input_data: Any,
        output: Any,
        duration_ns: int,
    ) -> dict:
        """Enregistrement d'une phase JUDGE."""
        return self.log(
            event_type="JUDGE",
            phase="JUDGE",
            function=function,
            cycle_id=cycle_id,
            input_data=input_data,
            output_summary=output,
            duration_ns=duration_ns,
        )

    def log_arbitrate(
        self,
        cycle_id: str,
        decision: str,
        conflict_resolved: bool,
        duration_ns: int,
    ) -> dict:
        """Enregistrement d'une phase ARBITRATE."""
        return self.log(
            event_type="ARBITRATE",
            phase="ARBITRATE",
            cycle_id=cycle_id,
            output_summary={
                "decision": decision,
                "conflict_resolved": conflict_resolved,
            },
            duration_ns=duration_ns,
        )

    def log_learn(
        self,
        cycle_id: str,
        function_updated: str,
        feedback: float,
        delta: float,
        duration_ns: int,
    ) -> dict:
        """Enregistrement d'une phase LEARN."""
        return self.log(
            event_type="LEARN",
            phase="LEARN",
            function=function_updated,
            cycle_id=cycle_id,
            output_summary={
                "feedback": feedback,
                "delta": delta,
                "function_updated": function_updated,
            },
            duration_ns=duration_ns,
        )

    def log_error(
        self,
        cycle_id: str,
        phase: str,
        function: str,
        error_type: str,
        message: str,
    ) -> dict:
        """Enregistrement d'une erreur — toujours dans le forensic."""
        return self.log(
            event_type="ERROR",
            phase=phase,
            function=function,
            cycle_id=cycle_id,
            output_summary={
                "error_type": error_type,
                "message": message,
            },
        )

    def count_entries(self) -> int:
        """Nombre d'entrées dans le log forensic."""
        if not FORENSIC_FILE.exists():
            return 0
        with open(FORENSIC_FILE, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def last_entries(self, n: int = 10) -> list[dict]:
        """Lire les N dernières entrées du log."""
        if not FORENSIC_FILE.exists():
            return []
        entries = []
        with open(FORENSIC_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries[-n:]


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_logger: ForensicLogger | None = None


def get_logger(component: str = "lucy") -> ForensicLogger:
    """Obtenir l'instance singleton du logger forensic."""
    global _logger
    if _logger is None:
        _logger = ForensicLogger(component=component)
    return _logger


# ---------------------------------------------------------------------------
# Initialisation au démarrage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger = get_logger("lucy-init")
    entry = logger.log_init(project_version="0.0.1")
    print(f"✅ Log forensic initialisé : {FORENSIC_FILE}")
    print(f"   Entrées totales : {logger.count_entries()}")
    print(f"   Première entrée : {entry['ts_iso']}")
