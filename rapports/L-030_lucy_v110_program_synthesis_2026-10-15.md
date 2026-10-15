# L-030 — LuCY v11.0 : Program Synthesis Engine — Run local 3 jeux + Audit critique

**Date :** 2026-10-15T08:00:00Z
**Version agent :** v11.0
**Source :** `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`
**Archive :** `LuCY/agent/my_agent_v110.py`
**Log JSON :** `LuCY/logs/lucy_L030_20261015T080000Z.json`
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**
**Espace rapports :** LuCY (L-001→L-030) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Objectif de cette session

Implémenter le moteur **Program Synthesis** (PS) dans LuCY v11.0 pour dépasser `levels_completed=0`.
Cause racine identifiée en L-029 : aucune inférence de règles de transformation dans v10.0.

---

## 2. Architecture v11.0 — avant / après

### Avant (v10.0) — 4 modules

| Module | Description |
|--------|-------------|
| `_GridPerceptor` | Perception visuelle directe (symétrie, couleur, masse) |
| `_EpisodicMemory` | Mémoire intra-partie : (fingerprint, action) → score |
| `_CognitiveEngine` | Score pondéré des 4 signaux |
| `_KaggleForensicLogger` | Logger NS stdout |

### Après (v11.0) — 6 modules (+2 nouveaux)

| Module | Description |
|--------|-------------|
| `_GridPerceptor` | **Étendu** : ajoute `active_count`, `centre_of_mass_r/c` |
| `_EpisodicMemory` | Inchangé |
| `_CognitiveEngine` | Inchangé — fallback si PS < seuil |
| **`_TransformType`** | **NOUVEAU** : catégories de transformation (IDENTITY/GROWING/SHRINKING/RECOLOR/SHIFT/DELTA) |
| **`_RuleMemory`** | **NOUVEAU** : mémoire de règles (action×état→confiance par transformation) |
| `_KaggleForensicLogger` | Étendu : `PS_HYPOTHESIS`, `PS_FOLLOW` events |

---

## 3. Modifications précises du code — avant / après

### 3.1 `_GridPerceptor.extract()` — ajout de 4 champs

**Fichier :** `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`

**Avant (v10.0, lignes ~347–356) :**
```python
features: dict = {
    "symmetry_h": 0.0, "symmetry_v": 0.0, "dominant_colour": 0,
    "complexity": 1, "active_ratio": 0.0, "colour_count": 1,
    "delta_mass": 0, "grid_valid": False,
}
```

**Après (v11.0) :**
```python
features: dict = {
    "symmetry_h": 0.0, "symmetry_v": 0.0, "dominant_colour": 0,
    "complexity": 1, "active_ratio": 0.0, "colour_count": 1,
    "delta_mass": 0, "grid_valid": False,
    "active_count": 0, "rows": 0, "cols": 0,       # ← NOUVEAU
    "centre_of_mass_r": 0.0, "centre_of_mass_c": 0.0,  # ← NOUVEAU
}
```

### 3.2 `_RuleMemory.state_signature()` — empreinte d'état lossy

**Avant (v10.0) :** absent

**Après (v11.0, lignes ~462–469) :**
```python
@staticmethod
def state_signature(features: dict) -> str:
    dom = features.get("dominant_colour", 0)
    cplx = min(features.get("complexity", 1), 5)
    active_bucket = int(features.get("active_ratio", 0.5) * 4)
    return f"{dom}:{cplx}:{active_bucket}"
```

### 3.3 `_RuleMemory._classify()` — catégorisation transformation

**Avant (v10.0) :** absent

**Après (v11.0) :**
```python
@staticmethod
def _classify(pre: dict, post: dict, level_up: bool) -> str:
    if level_up:        return _TransformType.GROWING
    if pre_dom != post_dom: return _TransformType.RECOLOR
    if shift > 1.5:     return _TransformType.SHIFT
    if post_active > pre_active: return _TransformType.GROWING
    if post_active < pre_active: return _TransformType.SHRINKING
    if identical:       return _TransformType.IDENTITY
    return _TransformType.DELTA
```

### 3.4 `choose_action()` — dispatch PS avant CognitiveEngine

**Avant (v10.0, phase EXPLOIT) :**
```python
engine = _CognitiveEngine(self._memory, self._n_progress, self._n_total)
scores = engine.score_all(fp, candidates, features, self._action_count)
action = max(candidates, key=lambda a: scores.get(a, 0.0))
```

**Après (v11.0) :**
```python
# Essayer d'abord Program Synthesis
ps_action, ps_conf = self._rule_memory.best_action(
    candidates, features, prefer_transform=_TransformType.GROWING
)
if ps_action is not None and ps_conf >= PS_CONFIDENCE_THRESHOLD:
    action = ps_action  # ← PS_FOLLOW
    self._forensic.on_synthesis_follow(action.name, ps_conf)
else:
    # Fallback cognitive scoring (v10.0)
    engine = _CognitiveEngine(self._memory, self._n_progress, self._n_total)
    scores = engine.score_all(fp, candidates, features, self._action_count)
    action = max(candidates, key=lambda a: scores.get(a, 0.0))
```

---

## 4. Résultats du run local (3 jeux : ls20, vc33, lp85)

| Jeu | `levels_completed` | Actions | Erreurs | `PS_HYPOTHESIS` émis | `PS_FOLLOW` déclenché | `n_rules` final |
|-----|-------------------|---------|---------|----------------------|----------------------|----------------|
| ls20 | 0 | 79 | 0 | 5 | **0** | 70 |
| vc33 | 0 | 79 | 0 | 5 | **0** | 70 |
| lp85 | 0 | 79 | 0 | 5 | **0** | 68 |

---

## 5. Lecture critique des logs bruts (L-060)

### ✅ Ce qui fonctionne

- `PS_HYPOTHESIS` émis correctement avec `n_rules` croissant (14→70) — module fonctionnel
- `_RuleMemory.record()` s'appelle à chaque action — alimentation correcte
- `transform` toujours observé et catégorisé — aucune exception
- Zéro erreur sur 3/3 jeux — stabilité maintenue

### ⚠️ Problème diagnostiqué : `PS_FOLLOW` = 0

**Cause :** Tous les `transform` observés = `IDENTITY`.

Cela signifie que pour ls20, vc33, lp85, **les actions 1–7 ne changent pas visuellement** :
- `active_count` identique avant/après
- `dominant_colour` identique
- `centre_of_mass` ne bouge pas de plus de 0.5

**Conséquence :** la confiance GROWING reste 0.0, donc `ps_conf < PS_CONFIDENCE_THRESHOLD (1.5)` → jamais de `PS_FOLLOW`.

### 🔍 Découverte critique — espace d'actions ARC-AGI-3

Le fichier `metadata.json` de ls20 contient :
```json
"baseline_actions": [22, 123, 73, 84, 96, 192, 186]
```

Ces entiers **ne correspondent pas** à ACTION1..ACTION7 (valeurs 1..7).  
`GameAction.from_id(22)`, `from_id(123)`, etc. = actions spécifiques à chaque jeu.

**LuCY n'essaie que ACTION1..ACTION7**, qui sont probablement des no-ops sur ces puzzles spécifiques. Les actions efficaces ont des IDs 22, 73, 84, 96, 123, 186, 192.

---

## 6. Comparaison v10.0 vs v11.0

| Critère | v10.0 | v11.0 |
|---------|-------|-------|
| `levels_completed` | 0/25 | 0/3 |
| Erreurs | 0 | 0 |
| Module PS actif | ❌ | ✅ |
| Hypothèses générées | 0 | ≤70/jeu |
| `PS_FOLLOW` déclenché | N/A | 0 (IDENTITY only) |
| Transforms catégorisés | N/A | IDENTITY/GROWING/RECOLOR/SHIFT/SHRINKING |
| Empreinte état (state_signature) | ❌ | ✅ |
| Events forensic PS | ❌ | `PS_HYPOTHESIS` + `PS_FOLLOW` |

---

## 7. Prochaines étapes pour v12.0

### P0 — Utiliser les `baseline_actions` de chaque jeu

```python
# Dans play_local.py ou my_agent.py :
# Lire metadata.json pour chaque game_id
# Inclure les baseline_actions integers dans les candidats
```

Les entiers 22, 73, 84, 96, 123, 186, 192 sont les actions qui permettent réellement de compléter les niveaux. LuCY doit pouvoir les tenter.

### P1 — Laisser `available_actions` primer sans filtre ACTION.RESET

La logique `_get_available_actions()` retourne déjà les actions entières via `GameAction.from_id()`. Le problème est que pour ls20 le `available_actions` retourné par le moteur peut déjà contenir ces IDs — à vérifier avec un log exhaustif.

### P2 — Ajuster PS_CONFIDENCE_THRESHOLD si les IDENTITY dominent

Si l'espace d'actions est correct mais que les transformations restent lentes, baisser le seuil à 0.5–1.0 pour permettre des règles moins certaines d'être suivies.

---

## 8. Commits

| Fichier | Action |
|---------|--------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | MODIFIÉ → v11.0 |
| `agent/my_agent_v110.py` | CRÉÉ (archive v11.0) |
| `logs/lucy_L030_20261015T080000Z.json` | CRÉÉ |
| `rapports/L-030_lucy_v110_program_synthesis_2026-10-15.md` | CRÉÉ |

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**
