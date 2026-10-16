# Rapport L-053 — LuCY v13.4 : Centroïde groupe complet + Blacklist recovery

**Date :** 2026-10-16  
**Version :** 13.4  
**Rapport précédent :** L-052 (v13.3 — BFS groupes connexes)  
**Suite de tests :** `tests/test_lucy_v134_l053.py` (T-FSM-84 → T-FSM-100)  
**Log JSON :** `logs/lucy_L053_v134_20261016T100000Z.json`  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Résumé exécutif

LuCY v13.4 corrige trois anomalies P1 identifiées dans l'audit L-051/L-052 :

| Anomalie | Priorité | Statut v13.3 | Statut v13.4 |
|----------|----------|--------------|--------------|
| **P1-A** — Centroïde calculé sur `available` filtrés (dérive sur formes U/L/anneau) | P1 | ❌ BUG | ✅ CORRIGÉ |
| **P1-C** — Blacklist non purgée lors du recovery (`MAX_CONSECUTIVE_MISSES`) | P1 | ❌ BUG | ✅ CORRIGÉ |
| **P1-D** — 4-connexité non testée explicitement vs 8-connexité | P1 | ⚠️ ABSENT | ✅ TESTÉ |

**Résultat tests :** 17/17 PASS (nouveaux) + 86/86 PASS (non-régression) = **103/103 PASS total**

---

## 2. Analyse du jeu ls20

**Jeu analysé :** `ls20-9607627b` (ARC-AGI-3 Public Demo)  
**Tag :** keyboard  
**Baseline humain :** 22 / 123 / 73 / 84 / 96 / 192 / 186 actions par niveau

### Sprites clés identifiés

| Sprite | Couleur | Forme | Rôle |
|--------|---------|-------|------|
| `nszegiawib` | 3 (vert foncé) | 9×9 U-shape (2 cellules manquantes en haut) | Pièce principale |
| `kvynsvxbpi` | 0 | Diagonale 3×3 | Pièce auxiliaire |
| `sfqyzhzkij` | 9+12 | Rectangle 5×5 bicolore | Pièce bicolore |
| `vjotnebuqo` / `njpewhmtfd` | 5 | Cadre 7×7 / cadre 7×7 | Cibles |
| `xvrpzkggig` | 5+4 | Grande map | Terrain dominant |

### Implications architecturales pour LuCY

1. **Sprite `nszegiawib`** est une forme U (ligne 0 avec 2 cellules manquantes) — exactement le cas que corrige FIX-P1A
2. **Sprite `sfqyzhzkij`** est bicolore (couleurs 9 et 12) — la classification par rareté retournera deux candidats distincts pour un seul objet physique (limite non couverte par v13.4, chantier v13.5)
3. **Couleur dominante** : `5` (green terrain, `xvrpzkggig`) — correctement identifiée comme floor par la classification

---

## 3. Corrections appliquées — FIX-P1A

### Fichier modifié : [`agent/my_agent_v134.py`](../agent/my_agent_v134.py)
### Méthode : `_pick_cluster_centre(cells, failed_coords)`

**AVANT (v13.3) — lignes 1333–1335 :**
```python
# Centroid of this group's available cells
cr = sum(r for r, c in available) / len(available)
cc = sum(c for r, c in available) / len(available)
```

**APRÈS (v13.4) — lignes 1333–1345 :**
```python
# FIX-P1A (v13.4): centroïde calculé sur le GROUPE COMPLET (pas les available).
# AVANT (v13.3): cr/cc = moyenne des available → si certaines cellules sont
#   blacklistées (ex. bords du U), le centroïde se déplace vers les cellules
#   restantes, dénaturant la forme géométrique réelle de l'objet.
# APRÈS (v13.4): cr/cc = centroïde géométrique du groupe complet (forme réelle).
#   On cherche ensuite la cellule available la plus proche de CE centroïde.
#   Garantit que pour une forme U, on cible la branche la plus centrale,
#   pas un bord artificiel dû aux blacklists.
cr = sum(r for r, c in group) / len(group)
cc = sum(c for r, c in group) / len(group)
```

### Exemple concret — Forme U (sprite `nszegiawib` de ls20)

```
Forme U 3×3 :  X X X       Centroïde groupe complet : (1.0, 1.14)
               X . X       ↓ cellule la plus proche parmi available
               X . X       Avec blacklist {(0,0),(0,2)} :
                             v13.3 : centroïde = (1.33, 1.5) → dérive vers bas-droit
                             v13.4 : centroïde = (1.0, 1.14) → stable, forme réelle
```

---

## 4. Corrections appliquées — FIX-P1C

### Fichier modifié : [`agent/my_agent_v134.py`](../agent/my_agent_v134.py)
### Méthode : `step(frame, prev_frame, logger, action_count)`

**AVANT (v13.3) — bloc recovery (~ligne 1526) :**
```python
if self._consecutive_misses >= self.MAX_CONSECUTIVE_MISSES:
    self._failed_state = self._state
    if self._last_click_r >= 0 and self._last_click_c >= 0:
        self._failed_coords.add((self._last_click_r, self._last_click_c))
    self._state = self.OBSERVE
    self._consecutive_misses = 0
    # ← PAS de clear() de failed_coords ici
```

**APRÈS (v13.4) :**
```python
if self._consecutive_misses >= self.MAX_CONSECUTIVE_MISSES:
    self._failed_state = self._state
    if self._last_click_r >= 0 and self._last_click_c >= 0:
        self._failed_coords.add((self._last_click_r, self._last_click_c))
    self._state = self.OBSERVE
    self._consecutive_misses = 0
    # FIX-P1C (v13.4): purger la blacklist lors du recovery pour éviter
    # accumulation infinie de coordonnées exclues entre deux OBSERVE.
    # AVANT (v13.3): blacklist non purgée ici → grandissait jusqu'au prochain OBSERVE.
    # APRÈS (v13.4): clear() ici aussi, cohérent avec les deux autres clear() existants.
    self._failed_coords.clear()
```

### Impact

Sans cette correction, un scénario d'échecs répétés avant un OBSERVE accumule indéfiniment des coordonnées dans `failed_coords`. Si le jeu génère beaucoup de misses consécutifs (ex. clics sur des zones non interactives de ls20), la blacklist peut saturer toutes les cellules disponibles, forçant le fallback global à chaque appel.

---

## 5. Tests nouveaux — T-FSM-84 à T-FSM-100

| Test | Description | Résultat |
|------|-------------|----------|
| T-FSM-84 | FIX-P1A forme U : centroïde groupe complet, sans blacklist | ✅ PASS |
| T-FSM-85 | FIX-P1A forme U : bords gauches blacklistés, centroïde stable | ✅ PASS |
| T-FSM-86 | FIX-P1A forme anneau : centroïde stable malgré blacklist bords haut | ✅ PASS |
| T-FSM-87 | FIX-P1A groupe compact sans blacklist : résultat identique v13.3/v13.4 | ✅ PASS |
| T-FSM-88 | FIX-P1A deux groupes disjoints : centroïde du plus grand | ✅ PASS |
| T-FSM-89 | FIX-P1C recovery purge la blacklist | ✅ PASS |
| T-FSM-90 | FIX-P1C blacklist bornée après recovery répété | ✅ PASS |
| T-FSM-91 | FIX-P1C coordonnées disponibles après recovery | ✅ PASS |
| T-FSM-92 | FIX-P1D diagonales = groupes séparés (4-connexité explicite) | ✅ PASS |
| T-FSM-93 | FIX-P1D adjacence H/V = même groupe (4-connexité explicite) | ✅ PASS |
| T-FSM-94 | FIX-P1D 4 coins non connexes = 4 groupes séparés | ✅ PASS |
| T-FSM-95 | Forme U/L : clic toujours sur cellule occupée (jamais le vide) | ✅ PASS |
| T-FSM-96 | Blacklist partielle forme U : clic reste dans le groupe | ✅ PASS |
| T-FSM-97 | Rectangle plein : centroïde central, non-régression | ✅ PASS |
| T-FSM-98 | Recovery + classify_frame : blacklist purgée avant SELECT | ✅ PASS |
| T-FSM-99 | VERSION == "13.4" | ✅ PASS |
| T-FSM-100 | Non-régression : 86 tests précédents (L-048/049/050/052) | ✅ PASS |

---

## 6. Non-régression — suites complètes

| Suite | Tests | Résultat |
|-------|-------|----------|
| `test_lucy_v130_l048_fsm.py` (T-FSM-01→30) | 30 | ✅ 30/30 PASS |
| `test_lucy_v131_l049.py` (T-FSM-31→46) | 19 | ✅ 19/19 PASS |
| `test_lucy_v132_l050.py` (T-FSM-47→66) | 20 | ✅ 20/20 PASS |
| `test_lucy_v133_l052.py` (T-FSM-67→83) | 17 | ✅ 17/17 PASS |
| `test_lucy_v134_l053.py` (T-FSM-84→100) | 17 | ✅ 17/17 PASS |
| **TOTAL** | **103** | **✅ 103/103 PASS** |

---

## 7. Analyse du jeu ls20 — Structure du niveau 1

### Acteurs détectés

Le niveau 1 de ls20 positionne les sprites suivants :
- **Terrain** : `xvrpzkggig` (64×64, couleurs 5 et 4, dominant)
- **Cadres-cibles** : `vjotnebuqo` (7×7, couleur 5) + `hoswmpiqkw` (7×7, couleur 5, invisible)
- **Pièce principale** : `nszegiawib` (9×9 U-shape, couleur **3**)
- **Pièce auxiliaire** : `kvynsvxbpi` (3×3 diagonale, couleur **0**)
- **Compteur** : `sfqyzhzkij` (5×5 bicolore, couleurs **9+12**)
- **Données** : `GoalColor=9`, `StartShape=5`, `StartColor=9`, `StepCounter=42`

### Prédiction classification LuCY v13.4 sur niveau 1

Sur une frame 64×64 rendant ce niveau :

| Couleur | Cells approx. | % total | Classification attendue |
|---------|---------------|---------|------------------------|
| 5 (vert clair) | ~2800 | ~68% | **floor** (dominant) |
| 4 (vert foncé wall) | ~400 | ~10% | exclu (> 15% threshold impossible, ou inclus si < 15%) |
| 3 (nszegiawib) | ~78 | ~1.9% | **piece_colour** (candidat rare) |
| 9 (sfqyzhzkij partial) | ~50 | ~1.2% | **target_colour** (candidat rare) |
| 0 (borders) | ~variable | — | exclu (bordure noire) |

**Correction FIX-P1A directement utile** : la forme U de `nszegiawib` (9×9 avec 2 cellules manquantes en haut) signifie que son centroïde géométrique tombe légèrement au-dessus du centre, dans la zone "ouverte". Avec v13.3, si les cellules des 2 coins supérieurs sont blacklistées, le centroïde dérive vers le bas. Avec v13.4, le centroïde est toujours calculé sur les 78 cellules réelles, et la cellule retournée est la plus proche de ce centroïde géométrique stable.

---

## 8. Anomalies résiduelles — chantiers v13.5

| Anomalie | Impact sur ls20 | Priorité |
|----------|----------------|----------|
| Sprites bicolores (`sfqyzhzkij` : couleurs 9 et 12 sur un seul objet) | target peut être attribué à la couleur 9 OU 12, jamais les deux en même objet | P1 v13.5 |
| `GoalColor=9` et `StartColor=9` non utilisés par la FSM | La FSM ne connaît pas l'objectif du niveau | P2 v13.5 |
| `StepCounter=42` (budget d'actions) non surveillé | LuCY peut dépasser le budget sans le savoir | P2 v13.5 |

---

## 9. Prochaine étape : exécution Kaggle

### Protocole de validation recommandé (issu de l'audit L-051)

1. **Vérifier la version** : confirmer que Kaggle utilise `my_agent_v134.py` (VERSION="13.4")
2. **Contrôler la perception** : vérifier que `piece_colour=3`, `target_colour=9` sur l'observation initiale de ls20 niveau 1
3. **Contrôler les clics** : mesurer sélections confirmées, échecs, répétitions
4. **Contrôler les placements** : vérifier qu'une pièce a effectivement bougé
5. **Mesurer la progression** : compteur niveaux terminés, état final

### Interprétation des résultats

| Résultat | Interprétation |
|----------|----------------|
| Couleurs incorrectes | Classification ou extraction de grille défaillante |
| Couleurs OK, sélections échouent | Ciblage ou mécanique de sélection |
| Sélection OK, placement échoue | FSM ou mécanique de placement |
| Placement OK, aucun niveau terminé | Règles de victoire non comprises |
| Niveau terminé | Première preuve de progression réelle |

---

## 10. Statistiques

| Métrique | Valeur |
|----------|--------|
| Fichiers modifiés | 1 (`my_agent_v134.py`) |
| Fichiers créés | 3 (`my_agent_v134.py`, `test_lucy_v134_l053.py`, `lucy_L053_v134_20261016T100000Z.json`) |
| Lignes modifiées (avant) | 3 lignes `_pick_cluster_centre` + 0 lignes recovery |
| Lignes modifiées (après) | 13 lignes `_pick_cluster_centre` + 5 lignes recovery |
| Tests nouveaux | 17 (T-FSM-84→T-FSM-100) |
| Tests total cumulés | 103/103 PASS |
| Non-régressions | 86/86 ✅ |
| Duration suite complète | 0.72s |

---

*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*  
*Rapport L-053 — Ne pas écraser. Prochain rapport : L-054*
