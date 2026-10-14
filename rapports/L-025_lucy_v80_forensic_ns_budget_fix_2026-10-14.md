# L-025 — LuCY v8.0 : ForensicLogger nanoseconde inline + corrections BUG-B1/B2/B3

**Horodatage :** 2026-10-14T18:00:04Z  
**Session :** L-025  
**Projet :** LuCY — ARC-AGI-3 (arc-prize-2026)  
**Version :** v7.0 → v8.0  
**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

---

## 1. Objectif de la session

Intégrer un **logger forensic nanoseconde inline** dans `my_agent.py`, visible dans la console Kaggle (stdout → `__results__.html`), et corriger simultanément les bugs critiques BUG-B1, BUG-B2 et BUG-B3 identifiés dans L-023.

---

## 2. Fichiers modifiés

| Fichier | Action | Avant | Après |
|---|---|---|---|
| `LuCY/agent/my_agent_v80.py` | CRÉÉ | — | v8.0 (584 lignes) |
| `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | MIS À JOUR | v7.0 (357 lignes) | v8.0 (584 lignes) |
| `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/notebooks/kernel-metadata.json` | MIS À JOUR | id: `lucy-v7-0-arc-agi-3-cognitive-agent` | id: `lucy-v8-0-arc-agi-3-forensic-ns` |

---

## 3. Corrections appliquées

### BUG-B1 — CRITIQUE : budget MAX_ACTIONS_TOTAL incorrect

**Avant (v7.0, ligne 54) :**
```python
MAX_ACTIONS_TOTAL = 500       # hard cap per game (framework default is 80 but we set higher)
```

**Après (v8.0, ligne 56) :**
```python
MAX_ACTIONS_TOTAL = 80          # hard cap per game (matches framework default)
```

**Impact :** L'agent v7.0 continuait d'appeler `choose_action()` bien après l'épuisement réel du budget (≈80), gaspillant les actions restantes. Le score RHAE était pénalisé par le dénominateur `ai_actions` qui dépassait le budget humain de référence.

---

### BUG-B2 — MAJEUR : `is_done()` ne stoppait pas sur budget épuisé

**Avant (v7.0, ligne 251) :**
```python
def is_done(self, frames, latest_frame):
    return latest_frame.state is GameState.WIN
```

**Après (v8.0, lignes 260-274) :**
```python
def is_done(self, frames, latest_frame):
    if latest_frame.state is GameState.WIN:
        self._forensic.on_done(reason="WIN", ...)
        return True
    if self._action_count >= MAX_ACTIONS_TOTAL:
        self._forensic.on_done(reason="BUDGET_EXHAUSTED", ...)
        return True
    return False
```

**Impact :** Sans ce fix, le framework continuait d'appeler `choose_action()` jusqu'à une condition interne. Maintenant `is_done()` retourne `True` dès `action_count >= 80`, ce qui déclenche proprement `GAME_DONE` + `SUMMARY` dans les logs.

---

### BUG-B3 — MODÉRÉ : `_frame_delta` tronqué à 256 éléments

**Avant (v7.0, ligne 126) :**
```python
fa = _flatten(frame_a)[:256]
fb = _flatten(frame_b)[:256]
```

**Après (v8.0, ligne ~223) :**
```python
fa = _flatten(frame_a)
fb = _flatten(frame_b)
```

**Impact :** Les frames ARC-AGI-3 font typiquement 30×30 = 900 éléments. La troncature à 256 rendait `_frame_delta` aveugle aux changements dans les 2/3 inférieurs du frame.

---

## 4. Nouveauté : `_KaggleForensicLogger` (lignes 64–159)

### Contraintes de conception
- **Pas d'I/O fichier** : le système de fichiers Kaggle est éphémère, un fichier JSONL ne survit pas à la session
- **stdout uniquement** : `print()` est capturé par Kaggle dans `__results__.html` (338 Ko en v7.0)
- **Nanoseconde** : `time.time_ns()` à chaque événement
- **AVANT et PENDANT** : `ACTION_BEFORE` est émis **avant** la sélection d'action, `ACTION_AFTER` **immédiatement après** avec `selection_dur_ns`

### Format des événements stdout

```
[LuCY-NS:{ts_ns}] EVENT_TYPE | {"ts_ns":...,"event":"...","game_id":"...",...}
```

### Événements implémentés

| Événement | Quand | Champs clés |
|---|---|---|
| `GAME_INIT` | `__init__()` | `game_id`, `version`, `max_actions_total`, `certified_100=false` |
| `ACTION_BEFORE` | Avant sélection | `action_count`, `phase`, `fp_prefix`, `stuck_streak`, `n_candidates`, `candidates` |
| `ACTION_AFTER` | Après sélection | `action`, `phase`, `is_complex`, `selection_dur_ns` |
| `LEVEL_UP` | Niveau franchi | `old_level`, `new_level`, `actions_this_level` |
| `STUCK` | `stuck_streak == STUCK_THRESHOLD` | `streak`, `phase` |
| `RESET` | Tout RESET | `reason`, `action_count` |
| `STATE_CHANGE` | NOT_PLAYED / GAME_OVER | `state`, `action_count` |
| `MODEL_UPDATE` | Après enregistrement UCB1 | `action`, `level_up`, `delta`, `n_total` |
| `GAME_DONE` | WIN ou BUDGET_EXHAUSTED | `reason`, `levels_completed`, `total_actions`, `elapsed_ns` |
| `GAME_DONE (SUMMARY)` | Fin de jeu | Résumé JSON compact |

### Invariants dans tous les événements GAME_INIT

```json
"certified_100": false,
"unique_human_proven": false,
"debug": true
```

---

## 5. Vérification AST

```
AST PARSE OK
Classes found: ['_KaggleForensicLogger', '_ActionModel', 'MyAgent']
CERTIFIED_100=false in source: True
unique_human_proven=false in source: True
VERSION = "8.0"
MAX_ACTIONS_TOTAL = 80
```

---

## 6. Différence nommage (rappel décision C — L-024)

La distinction `Noyau cognitif` / `Cognitive Agent` est **conservée** :
- `LuCY/src/lucy/kernel/` → `Noyau cognitif LuCY` (classe de raisonnement interne)
- `LuCY/agent/my_agent_v80.py` → `LuCY Cognitive Agent v8.0` (wrapper Kaggle, code anglais D-004)

---

## 7. Logs générés

| Fichier | Type |
|---|---|
| `LuCY/logs/lucy_L025_20261014T180004Z.json` | Log JSON session L-025 |
| `LuCY/rapports/L-025_lucy_v80_forensic_ns_budget_fix_2026-10-14.md` | Ce rapport |

---

## 8. Prochaines actions

1. **Commit + push** sur `vgactech/LUCY` (main)
2. **`make submit`** dans `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/` pour créer le kernel v8.0 sur Kaggle
3. Vérifier la présence d'événements `[LuCY-NS:` dans `__results__.html` après exécution
4. Relever le score RHAE officiel v8.0 pour comparer avec v7.0 (0.14)
5. Si score amélioré → produire rapport L-026 avec analyse

---

*Rapport généré automatiquement — CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
