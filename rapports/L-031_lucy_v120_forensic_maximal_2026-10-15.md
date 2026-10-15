# L-031 — LuCY v12.0 : Forensic Max + Goal-Delta + Action-ID Audit

**Date :** 2026-10-15T12:00:00Z  
**Version agent :** v12.0  
**Source :** `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
**Archive :** `LuCY/agent/my_agent_v120.py`  
**Log JSON :** `LuCY/logs/lucy_L031_20261015T120000Z.json`  
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**  
**Espace rapports :** LuCY (L-001→L-031) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Contexte et problème précis résolu

Le rapport L-030 a identifié **trois causes profondes** pour `levels_completed=0/25` :

| ID | Cause | Impact |
|----|-------|--------|
| **P0-win** | `win_levels` (compteur officiel du moteur) non suivi | Victoires non comptées si `levels_completed` diverge |
| **P0-actions** | `available_actions` = `list[int]`, IDs > 7 invalides pour `GameAction.from_id()` | Silently ignorés → LuCY joue avec les 7 actions de repli |
| **P0-perception** | `IDENTITY` déclenché sur agrégats (active_count, dom_color, CoM) | Changements pixel-level invisibles → PS ne confirme jamais GROWING |
| **P1-goal** | Aucun accès à l'état objectif du puzzle | Optimise « changement » au lieu de « rapprochement du but » |

---

## 2. Modules implémentés — avant/après v11.0

### Avant (v11.0)

| Module | Description |
|--------|-------------|
| `_GridPerceptor` | Features grille |
| `_EpisodicMemory` | Score par état |
| `_CognitiveEngine` (4 signaux) | mem + prog + div + hint |
| `_TransformType` + `_RuleMemory` | Synthèse de règles |
| `_KaggleForensicLogger v1` | Log NS stdout basique |

### Après (v12.0) — nouveaux modules et modifications

| Module / Changement | Fichier ligne | Description |
|---------------------|---------------|-------------|
| `_GoalDeltaTracker` | `my_agent.py` ~825 | Inspecte FrameData pour attrs `goal/target/answer/output_grid/expected_output/solution`. Si trouvé, calcule `goal_delta = _frame_delta(current, goal)`. Retourne `goal_delta_improvement` par action. |
| `_KaggleForensicLogger v2` | `my_agent.py` ~100 | `FRAME_INVENTORY`, `ACTION_ID_UNKNOWN`, `ACTION_ID_AUDIT`, `GOAL_DELTA` ; `ACTION_BEFORE` étendu, `ACTION_AFTER` avec `pixel_diff` + `goal_delta` |
| `_pixel_diff_detail()` | `my_agent.py` ~499 | Diff pixel-level : `changed_pixels`, `changed_frac`, `added_pixels`, `removed_pixels`, `net_change`, `total_pixels` |
| `_get_available_actions()` | `my_agent.py` ~530 | Retourne `(list[GameAction], list[int])` — audit IDs bruts |
| `_CognitiveEngine.score_all()` | `my_agent.py` ~783 | Signal `W_GOAL_DELTA=5.0` × `goal_delta_improvement` ajouté |
| `_describe_shape()` | `my_agent.py` ~447 | Décrit forme frame sans sérialiser le contenu complet |

---

## 3. Avant/après détaillé — lignes exactes

### 3.1 Horloge forensic — AVANT vs APRÈS

**Avant (v11.0 `_KaggleForensicLogger.__init__`, ligne 109) :**
```python
# my_agent_v110.py ligne 109
self._game_start_ns: int = time.time_ns()
```

**Après (v12.0 `_KaggleForensicLogger.__init__`) :**
```python
self._game_start_ns: int = time.monotonic_ns()  # monotone pour durées
self._wall_start_ns: int = time.time_ns()        # horloge civile pour ts
```

**Raison :** `time.time_ns()` est une horloge civile susceptible d'être ajustée (NTP, DST, etc.) — elle ne garantit pas une mesure de durée fiable. `time.monotonic_ns()` est garantie monotone sur la durée du processus. Distinction documentée dans chaque événement via `note_timing`.

### 3.2 `on_action_before()` — AVANT vs APRÈS

**Avant (v11.0 ligne 143-155) :**
```python
def on_action_before(self, action_count, phase, candidates, fp, stuck_streak, levels_completed) -> int:
    ts_before = time.time_ns()
    self._emit("ACTION_BEFORE", {
        "action_count": action_count,
        "phase": phase,
        "fp_prefix": fp[:8],
        "stuck_streak": stuck_streak,
        "levels_completed": levels_completed,
        "n_candidates": len(candidates),
        "candidates": [a.name for a in candidates],
        "ts_before_ns": ts_before,
    })
    return ts_before
```

**Après (v12.0) — nouveaux paramètres et champs :**
```python
def on_action_before(self, action_count, phase, candidates, fp, stuck_streak,
                     levels_completed, win_levels, raw_available_ids,
                     goal_delta, frame_shape) -> int:
    # ... émet aussi : win_levels, raw_available_ids, raw_known_ids,
    # raw_unknown_ids, n_unknown_ids, goal_delta_before, frame_shape
```

**Apport :** Pour la première fois, les logs Kaggle montreront les IDs entiers bruts de `available_actions` et signaleront ceux hors de la plage 0-7.

### 3.3 `on_action_after()` — AVANT vs APRÈS

**Avant (v11.0 ligne 157-165) :**
```python
def on_action_after(self, action_count, action_name, phase, ts_before_ns, is_complex) -> None:
    ts_after = time.time_ns()
    self._emit("ACTION_AFTER", {
        "action_count": action_count,
        "action": action_name,
        "phase": phase,
        "is_complex": is_complex,
        "selection_dur_ns": ts_after - ts_before_ns,
    })
```

**Après (v12.0) — ajout pixel_diff + goal_delta :**
```python
def on_action_after(self, action_count, action_name, phase, ts_before_ns, is_complex,
                    pixel_diff, goal_delta_after, goal_delta_improvement, transform_type):
    # ... émet aussi :
    # pixel_diff: {changed_pixels, changed_frac, added_pixels, removed_pixels, net_change, total_pixels}
    # goal_delta_after, goal_delta_improvement, transform_type
```

**Apport :** `changed_frac=0.000000` sur toutes les actions confirmera que le moteur de jeu ne change pas le frame — ou au contraire révèlera des changements sub-perceptuels ignorés par les agrégats v11.

### 3.4 `_get_available_actions()` — AVANT vs APRÈS

**Avant (v11.0, signature) :**
```python
def _get_available_actions(latest_frame: FrameData) -> list[GameAction]:
```

**Après (v12.0) :**
```python
def _get_available_actions(latest_frame: FrameData, logger=None) -> tuple[list[GameAction], list[int]]:
```

**Avant (v11.0, traitement IDs inconnus) :**
```python
elif isinstance(a, int):
    try:
        ga = GameAction.from_id(a)
        ...
    except ValueError:
        pass  # ← SILENCIEUX — l'ID inconnu disparaît
```

**Après (v12.0) :**
```python
if raw_id in _VALID_GAMEACTION_IDS:
    try:
        ga = GameAction.from_id(raw_id)
        ...
    except ValueError:
        if logger:
            logger.on_action_id_unknown(raw_id, ...)  # ← AUDITÉ
else:
    if logger:
        logger.on_action_id_unknown(raw_id, ...)      # ← AUDITÉ
```

### 3.5 `win_levels` tracking — AVANT vs APRÈS

**Avant (v11.0, choose_action ligne ~734) :**
```python
current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
current_levels = max(current_levels_raw, self._max_levels_seen)
level_up = current_levels > self._levels_completed
```

**Après (v12.0) :**
```python
current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
current_win_raw = getattr(latest_frame, "win_levels", 0) or 0
current_levels = max(current_levels_raw, self._max_levels_seen)
current_win = max(current_win_raw, self._max_win_levels_seen)
self._max_win_levels_seen = current_win
level_up = current_levels > self._levels_completed or current_win > self._win_levels
```

**Raison :** `FrameData.win_levels: int = Field(0, ge=0, le=254)` confirmé dans `arcengine/enums.py` ligne 136. C'est le compteur officiel de victoires du moteur.

---

## 4. Nouveau module : `_GoalDeltaTracker`

```
_GoalDeltaTracker
├── inspect_frame(FrameData)         ← cherche goal/target/answer/output_grid/...
├── current_delta(frame)             ← _frame_delta(current, goal_frame)
├── record_action_result(action, δ)  ← retourne improvement = δ_prev - δ_after
└── goal_delta_map(candidates)       ← {action.value: improvement}
```

**Attributs cherchés (par ordre) :**
`goal`, `target`, `answer`, `output_grid`, `expected_output`, `puzzle_output`, `solution`, `goal_frame`, `target_frame` + inspection dynamique de tous les attrs contenant `goal/target/answer/output/expect/solution`.

**Si goal_found=false** (attendu pour la plupart des jeux) : module dormant, `W_GOAL_DELTA` non appliqué, comportement identique à v11.

**Si goal_found=true** : `goal_delta_improvement > 0` → action rapproche du but → bonus `W_GOAL_DELTA × improvement` dans le scoring cognitif.

---

## 5. Événements forensic nouveaux

| Événement | Déclencheur | Informations clés |
|-----------|-------------|-------------------|
| `FRAME_INVENTORY` | 1ère frame de chaque jeu | Tous les attrs FrameData, types, valeurs scalaires, `goal_related_attrs` |
| `ACTION_ID_UNKNOWN` | Chaque ID entier hors 0-7 | `raw_id`, `attempt_count`, implication |
| `ACTION_ID_AUDIT` | Chaque `ACTION_BEFORE` | `raw_ids`, `known_ids`, `unknown_ids`, `fallback_triggered` |
| `GOAL_DELTA` | 1ère frame | `goal_found`, `goal_attr_used`, delta initial |

---

## 6. Résultats du run v12.0

| Métrique | v11.0 | v12.0 |
|----------|-------|-------|
| Run local exécuté | ✅ 25 jeux | ⚠️ **NON** — arcengine non importable hors Kaggle |
| `levels_completed` | 0 | **À MESURER** |
| `win_levels` | non suivi | **SUIVI** |
| P0-actions audit | silencieux | **ACTIF** — logs ACTION_ID_UNKNOWN |
| Pixel diff / action | absent | **ACTIF** — changed_frac dans ACTION_AFTER |
| goal_delta / action | absent | **ACTIF** si goal attr trouvé |
| Events forensic / jeu | 320 | **estimé 400-500** |

**Note :** `arcengine` (le moteur ARC-AGI-3) ne peut pas être importé en dehors du sandbox Kaggle. La syntaxe de v12.0 est vérifiée par inspection (aucune erreur de syntaxe évidente), mais l'exécution réelle et les résultats Kaggle restent à mesurer.

---

## 7. Questions ouvertes — à lire dans les logs Kaggle après soumission

| Q | Question | Log à lire |
|---|----------|-----------|
| Q1 | Les FrameData attrs contiennent-ils un goal frame ? | `FRAME_INVENTORY.goal_related_attrs` |
| Q2 | Les jeux utilisent-ils des IDs > 7 ? | `ACTION_ID_UNKNOWN` + `GAME_DONE.action_id_audit` |
| Q3 | `win_levels` incrémente-t-il lors d'une victoire ? | `LEVEL_UP.new_win_levels` |
| Q4 | `pixel_diff.changed_frac` — distribution sur 25 jeux ? | `ACTION_AFTER.pixel_diff` |
| Q5 | Quels raw_ids sont dans `available_actions` pour chaque jeu ? | `ACTION_BEFORE.raw_available_ids` |

---

## 8. Comparaison architecturale v1.0 → v12.0

| Version | Approche | Résultat |
|---------|----------|---------|
| v1.0 – v6.0 | Actions aléatoires, heuristiques basiques | 0/25 |
| v7.0 – v8.0 | UCB1 simple | 0/25 |
| v9.0 | UCB1 amélioré + fingerprint | 0/25 |
| v10.0 | Noyau cognitif (perception + mémoire) | 0/25 |
| v11.0 | Program synthesis + règles | 0/25 |
| **v12.0** | **Forensic max + win_levels + action-ID audit + goal-delta** | **→ PROCHAINE** |
| v13.0 | Actions correctes (si Q2=IDs inconnus) OU pixel_diff dans PS OU goal-delta exploitation | → SELON Q1-Q5 |

---

## 9. Commits

| Fichier | Action |
|---------|--------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | MODIFIÉ → v12.0 (1335 lignes) |
| `agent/my_agent_v120.py` | CRÉÉ (archive) |
| `logs/lucy_L031_20261015T120000Z.json` | CRÉÉ |
| `rapports/L-031_lucy_v120_forensic_maximal_2026-10-15.md` | CRÉÉ (ce fichier) |

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**
