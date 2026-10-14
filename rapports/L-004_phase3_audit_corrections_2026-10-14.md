# L-004 — Phase 3 : Corrections de l'audit P0/P1

**Projet :** LuCY (Language Unit for Cognitive Yield)  
**Date :** 2026-10-14  
**Session :** Phase 3 — Corrections audit Phase 2  
**SHA avant :** `2e38e52` | **SHA après :** à déterminer après commit  
**Tests :** 92/92 PASS (76 Phase 1+2 + 16 Phase 3)  
**Forensic log :** 2285 entrées (append-only)  
**CERTIFIED_100=false** | **unique_human_proven=false** | Mode DEBUG actif  

---

## 1. Résumé des corrections

L'audit Phase 2 avait identifié 4 failles prioritaires. Ce rapport documente
les corrections appliquées avec les lignes exactes AVANT / APRÈS.

| ID | Priorité | Faille | Statut |
|----|----------|--------|--------|
| P0-A | P0 | HardLimit non bloquante — résultat retourné même si limite violée | ✅ CORRIGÉ |
| P0-B | P0 | `v:no_wipe` contournable par synonymes lexicaux | ✅ CORRIGÉ |
| P1-A | P1 | Clés `traceability` non vérifiées dans `intermediate_steps` | ✅ CORRIGÉ |
| P1-B | P1 | Scores `SuccessCriterion` non bornés strictement dans [0,1] | ✅ CORRIGÉ |

---

## 2. Correction P0-A — HardLimit bloquante

### Faille

AVANT (fichier : `src/lucy/functions/types.py`, méthode `HardLimit.check()`) :

```python
# AVANT — ligne 48-52 (Phase 2)
def check(self, result: Any) -> bool:
    """Retourne True si la limite est respectée."""
    ok = self.check_fn(result)
    self.violated = not ok
    return ok  # ← retournait False silencieusement, l'opérateur continuait
```

```python
# AVANT — OperatorContract.check_all_limits() — ligne 90-96
def check_all_limits(self, result: Any) -> tuple[bool, list[str]]:
    violated: list[str] = []
    for lim in self.hard_limits:
        if not lim.check(result):
            violated.append(lim.name)
    return (len(violated) == 0, violated)
    # ← retournait (False, ['nom_limite']) mais le résultat était quand même retourné
```

```python
# AVANT — pattern dans les 8 opérateurs (ex: sensation_ex.py ligne 251-255)
all_ok, violated = self.contract.check_all_limits(result)
trace.limits_checked = True
trace.limits_violated = violated  # ← violated ignoré, result retourné quand même
trace.criteria_scores = self.contract.evaluate_all_criteria(result)
trace.duration_ns = time.time_ns() - t_start
return result  # ← résultat invalide retourné sans blocage
```

### Correction

APRÈS (fichier : `src/lucy/functions/types.py`) :

```python
# APRÈS — HardLimit.check() lève LimitViolationError (P0-A)
class LimitViolationError(RuntimeError):
    def __init__(self, limit_name: str, operator_id: str, description: str = "") -> None:
        self.limit_name = limit_name
        self.operator_id = operator_id
        ...

def check(self, result: Any, operator_id: str = "UNKNOWN") -> bool:
    ok = self.check_fn(result)
    self.violated = not ok
    if not ok:
        raise LimitViolationError(limit_name=self.name, operator_id=operator_id, ...)
    return True
```

```python
# APRÈS — OperatorContract.finalize_trace() — méthode centrale P0-A
def finalize_trace(self, result, trace, t_start, fallback_result=None):
    trace.limits_checked = True
    try:
        self.check_all_limits(result, operator_id=self.operator_id)
        trace.limits_violated = []
    except LimitViolationError as exc:
        trace.limits_violated = [exc.limit_name]
        trace.intermediate_steps.append(f"LIMIT_VIOLATED:{exc.limit_name}:...")
        if fallback_result is not None:
            return fallback_result, trace
        raise  # ← re-levée si pas de fallback
    ...
```

```python
# APRÈS — pattern dans les 8 opérateurs (ex: sensation_ex.py)
result, trace = self.contract.finalize_trace(result, trace, t_start)
return result  # ← uniquement retourné si toutes les limites sont respectées
```

**Fichiers modifiés :**
- `src/lucy/functions/types.py` — ajout `LimitViolationError`, refactoring `HardLimit.check()`, `OperatorContract.check_all_limits()`, nouvelle méthode `finalize_trace()`
- `src/lucy/functions/sensation_ex.py` — 2 sites remplacés
- `src/lucy/functions/sensation_in.py` — 1 site remplacé
- `src/lucy/functions/intuition_ex.py` — 3 sites remplacés
- `src/lucy/functions/intuition_in.py` — 1 site remplacé
- `src/lucy/functions/thinking_ex.py` — 2 sites remplacés
- `src/lucy/functions/thinking_in.py` — 2 sites remplacés
- `src/lucy/functions/feeling_ex.py` — 1 site remplacé
- `src/lucy/functions/feeling_in.py` — 2 sites remplacés
- `src/lucy/functions/__init__.py` — export `LimitViolationError` ajouté

---

## 3. Correction P0-B — v:no_wipe étendu aux synonymes

### Faille

AVANT (fichier : `src/lucy/functions/feeling_in.py`, méthode `_evaluate_against_value()`) :

```python
# AVANT — ligne 236-239
if val.value_id == "v:no_wipe":
    if any(w in action_lower for w in ("wipe", "truncate", "delete_log", "clear_forensic")):
        return 0.0
    return 1.0
# ← actions "remove_forensic", "destroy_log", "purge_log", etc. retournaient 1.0 (non détectées)
```

### Correction

APRÈS :

```python
# APRÈS — 12 synonymes couverts
if val.value_id == "v:no_wipe":
    _no_wipe_keywords = (
        "wipe", "truncate", "delete_log", "clear_forensic",
        "remove_forensic", "destroy_log", "erase_log", "purge_log",
        "reset_forensic", "drop_forensic", "flush_forensic", "overwrite_log",
    )
    if any(w in action_lower for w in _no_wipe_keywords):
        return 0.0
    return 1.0
```

**Fichier modifié :** `src/lucy/functions/feeling_in.py` — ligne 227 (ajout 8 synonymes)

---

## 4. Correction P1-A — Vérification clés traceability

### Faille

AVANT : La liste `OperatorContract.traceability` déclarait les clés obligatoires mais
aucune méthode ne vérifiait qu'elles étaient présentes dans `OperatorTrace.intermediate_steps`.

### Correction

APRÈS (fichier : `src/lucy/functions/types.py`) :

```python
# APRÈS — nouvelle méthode OperatorContract.check_traceability_keys()
def check_traceability_keys(self, trace: OperatorTrace) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key in self.traceability:
        found = any(key in step for step in trace.intermediate_steps)
        if not found:
            missing.append(key)
    return (len(missing) == 0, missing)
```

```python
# APRÈS — finalize_trace() appelle check_traceability_keys() (non bloquant, log)
all_present, missing = self.check_traceability_keys(trace)
if not all_present:
    trace.intermediate_steps.append(f"TRACEABILITY_MISSING_KEYS:{missing}")
```

**Fichier modifié :** `src/lucy/functions/types.py` — méthode ajoutée + appelée dans `finalize_trace()`

---

## 5. Correction P1-B — Bornage scores [0,1]

### Faille

AVANT (fichier : `src/lucy/functions/types.py`, méthode `SuccessCriterion.evaluate()`) :

```python
# AVANT — ligne 64-66
def evaluate(self, result: Any) -> float:
    """Évalue et mémorise le score [0.0 – 1.0]."""
    self.last_score = float(self.evaluate_fn(result))
    return self.last_score  # ← pouvait retourner -0.5 ou 1.5 si evaluate_fn mal écrite
```

### Correction

APRÈS :

```python
# APRÈS — clamp + attribut clamped
def evaluate(self, result: Any) -> float:
    raw = float(self.evaluate_fn(result))
    clamped_score = max(0.0, min(1.0, raw))
    self.clamped = (raw != clamped_score)  # audit trace
    self.last_score = clamped_score
    return self.last_score
```

**Fichier modifié :** `src/lucy/functions/types.py` — attribut `clamped: bool = False` + logique `evaluate()`

---

## 6. Nouveaux tests P3-T01 → P3-T16

Fichier créé : `tests/test_lucy_phase3_audit.py`

| Test | Description |
|------|-------------|
| P3-T01 | `HardLimit.check()` lève `LimitViolationError` si `check_fn` retourne `False` |
| P3-T02 | `HardLimit.check()` retourne `True` sans lever si limite respectée |
| P3-T03 | `check_all_limits()` lève dès la première limite violée (court-circuit) |
| P3-T04 | `finalize_trace()` retourne le fallback et logge la violation si fourni |
| P3-T05 | Mot original `wipe` toujours détecté (régression P0-B) |
| P3-T06 | Synonyme `remove_forensic` désormais détecté |
| P3-T07 | Synonyme `destroy_log` désormais détecté |
| P3-T08 | Synonymes `purge_log`, `erase_log`, `overwrite_log` détectés |
| P3-T09 | `check_traceability_keys()` retourne `(True, [])` si toutes les clés présentes |
| P3-T10 | `check_traceability_keys()` retourne `(False, ['confidence_computation'])` si manquante |
| P3-T11 | L'opérateur SE réel produit une trace avec toutes ses clés déclarées |
| P3-T12 | `finalize_trace()` logge `TRACEABILITY_MISSING_KEYS` si clé absente |
| P3-T13 | Score de `1.5` clamped à `1.0`, `clamped=True` |
| P3-T14 | Score de `-0.5` clamped à `0.0`, `clamped=True` |
| P3-T15 | Score de `0.75` non modifié, `clamped=False` |
| P3-T16 | Tous les critères des 8 opérateurs en pipeline retournent des scores dans [0,1] |

---

## 7. Résultats d'exécution

```
92 passed in 0.75s
```

- Phase 1 (T01–T32) : 32/32 ✅
- Phase 1 integration (A01–A04 + I01–I08) : 12/12 ✅
- Phase 2 (P2-T01–T32) : 32/32 ✅
- Phase 3 (P3-T01–T16) : 16/16 ✅

---

## 8. Forensic log

- **Entrées avant :** 2280
- **Entrées après :** 2285 (+ 5 entrées P3 ajoutées)
- **Fichier :** `logs/forensic/lucy_forensic.jsonl` — append-only perpétuel ✅

---

*Rapport généré automatiquement — jamais écraser les anciens rapports*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
