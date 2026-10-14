# L-029 — LuCY v10.0 : Noyau Cognitif Natif — Run local 25 jeux

**Date :** 2026-10-14T21:10:00Z  
**Version agent :** v10.0  
**Source :** `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
**Archive :** `LuCY/agent/my_agent_v100.py`  
**Log JSON :** `LuCY/logs/lucy_L029_20261014T211000Z.json`  
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**  
**Espace rapports :** LuCY (L-001→L-029) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Contexte

Le rapport L-028 a acté la décision **D-LUCY-001** : LuCY est son propre système cognitif natif,
sans LLM externe. Ce rapport documente l'implémentation v10.0 et son run local de validation sur 25 jeux.

---

## 2. Modules cognitifs implémentés — avant/après v9.0

### Avant (v9.0) — UCB1 aveugle

| Composant | Fichier | Ligne | Description |
|-----------|---------|-------|-------------|
| `_ActionModel` | `my_agent.py` | ~357 | Statistiques UCB1 : `n_level_up`, `n_progress`, `n_total` — aucune lecture de la grille |
| `ucb1_score()` | `my_agent.py` | ~382 | `reward + C×√(log(N)/n)` — optimise des chiffres, ne comprend pas la grille |
| Phase dispatch | `my_agent.py` | ~586 | `untried[0]` ou `best_action()` UCB1 |

### Après (v10.0) — Noyau Cognitif Natif

| Composant | Fichier | Rôle |
|-----------|---------|------|
| `_GridPerceptor` | `my_agent.py` | Lit directement `latest_frame.frame` → `symmetry_h/v`, `dominant_colour`, `complexity`, `active_ratio`, `colour_count`, `delta_mass` |
| `_EpisodicMemory` | `my_agent.py` | Stocke `(fingerprint, action) → score cumulé` : +2.0 level_up, +1.0 delta>DELTA_MIN, -0.1 sans progrès |
| `_CognitiveEngine` | `my_agent.py` | `score = W_MEM×mem + W_PROG×prog + W_DIV×div + W_PCT×hint` — 100 % Python pur |
| `_perception_hint()` | `my_agent.py` | Heuristique grille : symétrie haute → actions simples, complexité élevée → ACTION6 |

---

## 3. Bug identifié et corrigé lors du premier run

### BUG-D1 — `Counter(all_vals)` : `unhashable type: 'list'`

**Contexte :** `_GridPerceptor.extract()` construisait `all_vals = [mat[r][c] for ...]` mais certaines
cellules de la grille ARC peuvent être des listes imbriquées (pas des scalaires directs).

**Avant :**
```python
# my_agent.py ligne 360 (v10.0 initial)
all_vals = [mat[r][c] for r in range(rows) for c in range(cols)]
counter = Counter(all_vals)  # ← TypeError: unhashable type: 'list'
```

**Après :**
```python
# my_agent.py ligne 360 (v10.0 corrigé)
def _scalar(v: Any) -> int:
    if isinstance(v, (list, tuple)):
        return _scalar(v[0]) if v else 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

all_vals = [_scalar(mat[r][c]) for r in range(rows) for c in range(cols)]
mat = [[_scalar(mat[r][c]) for c in range(cols)] for r in range(rows)]
counter = Counter(all_vals)  # ← OK, toujours des int
```

---

## 4. Résultats du run local (25 jeux)

| Métrique | Valeur |
|----------|--------|
| Jeux joués | 25/25 |
| Erreurs d'exécution | **0** |
| `levels_completed` | **0/25** |
| Actions utilisées/jeu | 79 (budget MAX-1) |
| `cognitive_engine=true` | ✅ 25/25 |
| `external_llm=false` | ✅ 25/25 |
| Events forensic/jeu | 244 (PERCEPTION + ACTION + COGNITIVE_SCORE) |

### Exemple de features perçues sur ls20 (action 1)

```json
{
  "symmetry_h": 0.0,
  "symmetry_v": 0.625,
  "dominant_colour": 5,
  "complexity": 2,
  "active_ratio": 1.0,
  "colour_count": 2,
  "grid_valid": true
}
```

### Exemple de COGNITIVE_SCORE à n=10 (ls20)

```json
{"top3": {"ACTION3": 2.75, "ACTION4": 2.75, "ACTION2": 2.083}}
```

---

## 5. Analyse critique — pourquoi `levels_completed=0` persiste (lecture brute L-060)

**Ce n'est PAS un bug de l'algorithme.**

La perception fonctionne (PERCEPTION events émis avec features valides).
Le scoring cognitif fonctionne (COGNITIVE_SCORE émis, transitions explore→exploit visibles).
La mémoire épisodique fonctionne (MODEL_UPDATE enregistré à chaque action).

Le problème est **plus profond** : les puzzles ARC-AGI-3 nécessitent de comprendre
la **sémantique** des règles de transformation propres à chaque jeu. Sans connaître
a priori quelles actions correspondent à quels effets sémantiques sur un puzzle donné,
aucun moteur de scoring basé sur des heuristiques de symmetrie/couleur/masse
ne peut identifier la séquence exacte pour compléter un niveau en ≤79 actions.

### Ce qui manque à v10.0

| Capacité manquante | Impact |
|-------------------|--------|
| **Inférence de règles de jeu** | Ne peut pas déduire "cette combinaison d'actions résout ce puzzle" |
| **Mémoire cross-jeux** | Chaque partie recommence à zéro (mémoire intra-jeu seulement) |
| **Programme synthesis** | Ne peut pas synthétiser le programme de transformation à partir des frames observées |

---

## 6. Comparaison v9.0 vs v10.0

| Critère | v9.0 (UCB1) | v10.0 (Noyau Cognitif) |
|---------|-------------|----------------------|
| `levels_completed` | 0/25 | 0/25 |
| Erreurs | 0 | 0 (1 bug corrigé pendant dev) |
| Lit la grille ? | ❌ (hachage seulement) | ✅ (features extraites) |
| `external_llm` | N/A | `false` explicite |
| `cognitive_engine` | N/A | `true` explicite |
| Events forensic/jeu | 244 | 244 |
| D-LUCY-001 conforme | ❌ | ✅ |

---

## 7. Prochaine étape recommandée (v11.0)

Pour dépasser `levels_completed=0`, LuCY doit acquérir la capacité
**d'inférer les règles du jeu depuis les frames observées** pendant la partie.

Approche proposée pour v11.0 :
- **Program synthesis simplifié** : détecter les patterns de transformation entre frames consécutives
- **Hypothèses de règle** : "cette action dans cet état produit toujours cet effet"
- **Mémoire cross-épisodes** : conserver les hypothèses vérifiées d'une partie à l'autre

**Nécessite GO utilisateur avant implémentation.**

---

## 8. Commits

| Fichier | Action |
|---------|--------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | MODIFIÉ → v10.0 |
| `agent/my_agent_v100.py` | CRÉÉ (archive) |
| `rapports/L-028_lucy_d_lucy_001_architecture_native_2026-10-14.md` | CRÉÉ |
| `rapports/L-029_lucy_v100_noyau_cognitif_run_2026-10-14.md` | CRÉÉ |
| `logs/lucy_L029_20261014T211000Z.json` | CRÉÉ |

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**
