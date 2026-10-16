# L-054 — LuCY v13.5 : Guards rareté + tests T-FSM-49/51/56 renforcés

**Date :** 2026-10-16  
**Version :** 13.5  
**HEAD précédent :** `7332d7b` (L-053/v13.4)  
**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**  
**Audit source :** L-050 (anomalies P0/P1 identifiées dans le message utilisateur)

---

## 1. Contexte — Ce que demandait l'audit

L'audit critique fourni par l'utilisateur (correspondant au contenu de L-050) identifiait trois niveaux de problèmes :

### Anomalie P0-1 : Classification par rareté non universelle
La fonction `_classify_frame()` assigne piece/target uniquement par fréquence croissante. Deux risques :
- Un objet décoratif plus rare que la pièce prend sa place.
- Aucune vérification explicite que `piece_colour != target_colour`.
- Pas de détection d'un double fond (deux couleurs quasi-égales).

### Anomalie P0-2 : Centroïde sans groupes connexes réels
**DÉJÀ CORRIGÉ en v13.3 (BFS) + v13.4 (centroïde groupe complet).** L'audit reprenait le texte de L-050 qui décrivait l'état AVANT ces corrections. Les 103 tests de v13.3/v13.4 couvrent exactement ce point.

### Anomalie P1 : Trois tests faibles (T-FSM-49, T-FSM-51, T-FSM-56)
- **T-FSM-49** : vérifiait uniquement `piece != target` et `in (3,7)` — pas les IDs exacts.
- **T-FSM-51** : logique de vérification ambiguë (OR entre deux conditions).
- **T-FSM-56** : vérifiait `result is not None` et `result in cells` — pas que c'est le centroïde global.

---

## 2. Corrections appliquées dans v13.5

### 2.1 GUARD-DISTINCT (v13.5)

**AVANT (v13.4) :**
```python
if len(candidates) >= 2:
    self._target_colour = candidates[1][1]
```

**APRÈS (v13.5) :**
```python
if len(candidates) >= 2:
    target_candidate = candidates[1][1]
    if target_candidate == self._piece_colour:
        for _, c in candidates[2:]:
            if c != self._piece_colour:
                target_candidate = c
                break
        else:
            target_candidate = self.COLOUR_UNKNOWN
    self._target_colour = target_candidate
```

**Fichier :** [`agent/my_agent_v135.py`](../agent/my_agent_v135.py) — `_classify_frame()` ligne ~1242  
**Raison :** Cas dégénéré documenté. Le tri `(count, -colour)` garantit déjà la distinction dans les cas normaux ; le guard rend la propriété explicite et mesurable.

---

### 2.2 GUARD-FLOOR-COVERAGE (v13.5)

**AVANT (v13.4) :** aucune détection d'un double fond.

**APRÈS (v13.5) :**
```python
floor_count = counter.get(self._floor_colour, 0)
floor_ratio = floor_count / total_cells if total_cells > 0 else 1.0
self._ambiguous_floor = floor_ratio < 0.20
```

**Fichier :** [`agent/my_agent_v135.py`](../agent/my_agent_v135.py) — `_classify_frame()` après l'assignation de `_target_colour`  
**Initialisation :** `self._ambiguous_floor: bool = False` ajouté dans `__init__()`.  
**Raison :** Ne modifie pas la logique de classification — observation uniquement. Si `floor < 20%` des cellules, le flag est `True` et peut être exploité par les logs forensics et des tests futurs.

---

### 2.3 Attribut `_ambiguous_floor` ajouté dans `__init__`

**AVANT :** attribut absent.  
**APRÈS :** `self._ambiguous_floor: bool = False  # GUARD-FLOOR-COVERAGE (v13.5)`

---

## 3. Tests renforcés (réponse aux anomalies P1)

### T-FSM-101 — Renfort de T-FSM-49

**AVANT T-FSM-49 (trop faible) :**
```python
assert fsm._piece_colour != fsm._target_colour
assert fsm._piece_colour in (3, 7)
assert fsm._target_colour in (3, 7)
```

**APRÈS T-FSM-101 (renforcé) :**
```python
assert fsm._piece_colour == 7   # 3 cells — plus rare
assert fsm._target_colour == 3  # 4 cells — deuxième
```
Vérifie les IDs EXACTS. Échoue si la classification intervertit les deux.

---

### T-FSM-102 — Renfort de T-FSM-51

**AVANT T-FSM-51 (ambigu) :** vérifiait `piece_count <= MAX_RATIO*total OR piece_count == most_common[0][1]` — passait même si sky=2 était piece.

**APRÈS T-FSM-102 (renforcé) :** grille 10×10 construite sans aucune égalité :
- `floor=5` : 50 cells (50% — dominant)
- `sky=2` : 35 cells (35% > 15% → doit être exclu)
- `piece=3` : 10 cells
- `target=9` : 5 cells

Assertions :
```python
assert fsm._piece_colour != 2   # sky exclu de piece
assert fsm._target_colour != 2  # sky exclu de target
assert fsm._piece_colour == 9   # 5 cells, plus rare des valides
assert fsm._target_colour == 3  # 10 cells, deuxième
```

---

### T-FSM-103 — Renfort de T-FSM-56

**AVANT T-FSM-56 (trop faible) :** `assert result is not None` et `assert result in cells` seulement.

**APRÈS T-FSM-103 (renforcé) :** vérifie que le fallback retourne la cellule la plus proche du centroïde global exact :
```python
cr = sum(r for r, c in cells) / len(cells)
cc = sum(c for r, c in cells) / len(cells)
expected = min(cells, key=lambda rc: (rc[0]-cr)**2 + (rc[1]-cc)**2)
assert result == expected
```

---

## 4. Nouveaux tests T-FSM-101→T-FSM-120

| Test | Vérifie |
|------|---------|
| T-FSM-101 | IDs exacts piece=7 (3 cells), target=3 (4 cells) |
| T-FSM-102 | sky=2 (35%) absent de piece ET target, piece=9, target=3 |
| T-FSM-103 | Fallback = cellule la plus proche du centroïde global |
| T-FSM-104 | GUARD-DISTINCT : piece != target sur 3 grilles différentes |
| T-FSM-105 | GUARD-FLOOR-COVERAGE : floor < 20% → ambiguous_floor=True |
| T-FSM-106 | floor > 20% → ambiguous_floor=False |
| T-FSM-107 | Grille r11l simulée : floor=5, piece=3, target=15 — IDs exacts |
| T-FSM-108 | Décoratif 2 cells (< MIN_PIECE_CELLS) exclu — pièce détectée |
| T-FSM-109 | Décoratif 3 cells (= MIN_PIECE_CELLS) DEVIENT piece — limite documentée |
| T-FSM-110 | Classification idempotente sur 3 appels identiques |
| T-FSM-111 | 1 seul candidat → target=COLOUR_UNKNOWN |
| T-FSM-112 | Fallback blacklist totale : non-None et dans cells |
| T-FSM-113 | piece_colour et target_colour sont dans la grille réelle |
| T-FSM-114 | floor_colour = couleur dominante réelle |
| T-FSM-115 | ambiguous_floor=False sur r11l typique |
| T-FSM-116 | 2 objets séparés → BFS = 2 groupes distincts |
| T-FSM-117 | piece_cells non vide quand piece_colour valide |
| T-FSM-118 | target_cells vide quand COLOUR_UNKNOWN |
| T-FSM-119 | VERSION == "13.5" |
| T-FSM-120 | Non-régression 103 tests v13.0→v13.4 |

---

## 5. Résultats des tests

```
tests/test_lucy_v135_l054.py   20 passed  (T-FSM-101→120)
Suite complète v13.0→v13.5    123 passed / 0 failed / 0 skipped
Durée : 1.27s
```

---

## 6. Limite P0-1 documentée (non résolue à ce stade)

**T-FSM-109** documente explicitement la limite principale de la stratégie rareté :

> Si un objet décoratif a `>= MIN_PIECE_CELLS` cellules **et** est plus rare que la vraie pièce, il devient `piece_colour`. Ce n'est pas un bug de code — c'est la limite architecturale de l'heuristique rareté.

**Ce qui serait nécessaire pour la résoudre :**
1. Détecter les groupes connexes par couleur (BFS — déjà présent dans v13.3).
2. Vérifier si une sélection provoque une transition compatible avec une pièce saisie (feedback boucle de contrôle).
3. Conserver plusieurs hypothèses piece/target et les confirmer par observation.

**Décision** : ne pas implémenter à ce stade — valider d'abord la chaîne complète sur Kaggle (ls20 en premier, protocole audit §6) avant d'ajouter une couche cognitive supplémentaire.

---

## 7. Avant / Après résumé

| Élément | AVANT (v13.4) | APRÈS (v13.5) |
|---------|--------------|--------------|
| `_classify_frame()` GUARD-DISTINCT | absent | `piece_colour != target_colour` vérifié |
| `_classify_frame()` GUARD-FLOOR | absent | `_ambiguous_floor` flag |
| `__init__` | 10 attributs | 11 attributs (+`_ambiguous_floor`) |
| T-FSM-49 | IDs non vérifiés | T-FSM-101 : IDs exacts |
| T-FSM-51 | OR ambigu | T-FSM-102 : grille sans égalité, sky exclu explicitement |
| T-FSM-56 | result not None | T-FSM-103 : centroïde global exact |
| Total tests FSM | 103/103 | 123/123 |

---

## 8. Prochaine étape — Protocole de validation Kaggle

Conformément à la recommandation de l'audit (§6) :

1. **Vérifier la version** : confirmer que Kaggle exécute v13.5.
2. **Contrôler la perception** : `piece_colour=3`, `target_colour=15` sur observation initiale `r11l` (ou `floor=5`, `piece=3` sur `ls20` — jeu de départ obligatoire).
3. **Contrôler les clics** : compter sélections confirmées, échecs, répétitions.
4. **Contrôler les placements** : vérifier déplacement réel de la pièce.
5. **Contrôler la progression** : niveaux terminés, état final.
6. **Conserver les preuves** : commit exact, ID exécution Kaggle, logs bruts.

**Jeu de départ OBLIGATOIRE** : `ls20` (règle gravée — commencer par le plus facile).

---

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**
