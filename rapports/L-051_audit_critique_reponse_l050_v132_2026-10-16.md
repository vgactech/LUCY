# Rapport L-051 — Audit critique : réponse à L-050 (LuCY v13.2)

**Date :** 2026-10-16  
**Agent audité :** LuCY v13.2 (`agent/my_agent_v132.py`)  
**Rapport soumis à l'audit :** L-050 (`rapports/L-050_rarity_classification_cluster_v132_2026-10-16.md`)  
**Audit source :** utilisateur (session Bob IDE)  
**HEAD Git :** `84ede4b`  
**Statut :** VALIDÉ PARTIEL — corrections P0 appliquées, exécution Kaggle requise  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 0. Périmètre de l'audit

Expertises mobilisées : ingénierie des agents autonomes, vision par ordinateur,
apprentissage par renforcement, analyse de grilles ARC-AGI-3, algorithmique de
décision, tests logiciels et audit de fiabilité.

Cet audit répond point par point aux anomalies P0 et P1 soulevées dans la
session utilisateur (L-050 critique). Pour chaque anomalie, la vérification
a été faite **sur le code source réel** de `my_agent_v132.py`, ligne par ligne.

---

## 1. Résultat des tests — vérification locale

```
python3 -m pytest tests/test_lucy_v130_l048_fsm.py \
                  tests/test_lucy_v131_l049.py \
                  tests/test_lucy_v132_l050.py -v
```

```
69 passed in 1.09s   ← confirmé localement sur HEAD 84ede4b
```

L'affirmation du rapport L-050 (69/69 PASS) est **vérifiée et reproductible**.

---

## 2. Anomalie P0-1 — La rareté comme seul critère de classification

### 2.1 Ce que dit l'audit utilisateur

> La classification par rareté pourrait sélectionner un effet décoratif à la place
> de la pièce. Elle ne comprend pas la fonction de l'objet.
> Si deux fonds sont présents, ou si un objet occupe plus de cellules que le sol,
> l'hypothèse "dominant = terrain" peut devenir incorrecte.

### 2.2 Vérification sur le code réel (lignes 1182–1214)

Le code de `_classify_frame` en v13.2 :

```python
MAX_PIECE_CELLS_RATIO = 0.15   # exclut les couleurs > 15 % des cellules
MIN_PIECE_CELLS = 3            # exclut les artefacts isolés

candidates = [(count, colour) for colour, count in counter.items()
              if colour != floor and colour != 0
              and MIN_PIECE_CELLS <= count <= max_piece_cells]
candidates.sort(key=lambda x: (x[0], -x[1]))  # tri par rareté croissante
```

**Constat :** L'audit utilisateur est **fondé**. La rareté est le seul critère de
sélection après filtrage. Sur `r11l`, ce critère produit le bon résultat
(pièce=3, cible=15), mais il ne généralisera pas correctement sur des jeux où :
- Un effet décoratif a moins de cellules que la vraie pièce ;
- Deux fonds de couleurs différentes existent (le dominant varie selon le niveau) ;
- La pièce occupe plus de 15 % de la surface (seuil `MAX_PIECE_CELLS_RATIO`).

**Priorité maintenue : P0** — la classification produit le bon résultat sur le
jeu connu mais repose sur une hypothèse non universelle.

### 2.3 Évaluation du risque immédiat

| Scénario | Comportement v13.2 | Risque |
|----------|-------------------|--------|
| r11l (connu) | piece=3, target=15 — CORRECT | FAIBLE |
| Jeu avec effet décoratif < 12 cells | effet sélectionné comme pièce | MOYEN |
| Jeu avec two fonds (dominant change) | floor mal identifié → tout dérègle | ÉLEVÉ |
| Pièce > 15 % de la grille | pièce exclue des candidats | ÉLEVÉ |

### 2.4 Recommandation pour v13.3 (sans bloquer l'exécution Kaggle)

La correction complète décrite dans l'audit utilisateur (groupes connexes,
vérification par interaction, multi-hypothèses) est la cible correcte à moyen terme.

**Pour la prochaine version :**
1. Ajouter une détection de groupes connexes par BFS (`_find_connected_groups`) —
   une couleur présente sur 3 groupes disjoints est probablement une texture
   décoratives, pas une pièce unique.
2. Conserver le critère de rareté comme premier filtre, non comme critère final.

---

## 3. Anomalie P0-2 — Le centroïde ne détecte pas les groupes

### 3.1 Ce que dit l'audit utilisateur

> Le code réel ne recherche pas les groupes connexes et ne sélectionne pas le plus
> grand groupe. Il calcule un centroïde global pour toutes les cellules de la couleur.
> Si une couleur apparaît dans deux objets disjoints, le centroïde peut tomber entre
> les deux.

### 3.2 Vérification sur le code réel (lignes 1237–1261)

```python
@staticmethod
def _pick_cluster_centre(cells: list, failed_coords: set) -> Optional[tuple]:
    if not cells:
        return None
    available = [rc for rc in cells if rc not in failed_coords]
    working = available if available else cells
    # Compute centroid
    cr = sum(r for r, c in working) / len(working)
    cc = sum(c for r, c in working) / len(working)
    # Return cell closest to centroid
    return min(working, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)
```

**Constat :** L'audit utilisateur est **exactement correct**. Le centroïde est
calculé sur l'ensemble des cellules de la couleur, **sans détection de groupes
connexes**. La documentation dit "centroid of the largest cluster" mais le code
calcule le centroïde global de toutes les cellules.

**C'est un écart documentation / code.** Ce n'est pas un bug bloquant sur `r11l`
(la pièce forme un groupe compact de 12 cellules), mais c'est une fragilité réelle.

### 3.3 Cas concret où le centroïde global échoue

Sur une grille où la couleur 3 apparaît en `(5,5)` et en `(5,55)` (deux groupes
disjoints), le centroïde global sera `(5, 30)` — un point vide entre les deux
objets. LuCY clique sur une cellule de fond, jamais confirmée, la blackliste,
et tourne en rond.

### 3.4 Concernant la blacklist totale (T-FSM-56)

Le test vérifie : « si tout est blacklisté → retourner un résultat non None ».
C'est vrai. Mais l'audit utilisateur soulève le problème plus profond : retourner
une coordonnée blacklistée sans que l'état ait changé peut répéter un clic déjà
échoué. La logique de récupération ne vérifie pas si l'état a changé depuis
l'échec précédent.

**Avant (T-FSM-56) :**
```python
# Test actuel — vérifie uniquement l'absence de crash
result = fsm._pick_cluster_centre(cells, blacklist)
assert result is not None   # ← PASS mais ne vérifie pas la logique
assert result in cells
```

**Ce que le test devrait vérifier en plus :**
- que la coordonnée retournée en fallback diffère d'un état identique préalable, OU
- que la logique de `step()` ne rappelle pas `_pick_cluster_centre` avec la même
  blacklist si `_state` n'a pas changé.

### 3.5 Recommandation pour v13.3

Implémenter `_find_connected_groups(cells)` par BFS. Coût O(n) sur n cellules.
Sélectionner le groupe le plus grand, calculer son centroïde. Ajouter un test
T-FSM-67 démontrant le cas des deux groupes disjoints.

---

## 4. Anomalie P1 — Faiblesse de certains tests

### 4.1 T-FSM-49 — attribution non vérifiée

**Code du test :**
```python
assert fsm._piece_colour != fsm._target_colour
assert fsm._piece_colour in (3, 7)
assert fsm._target_colour in (3, 7)
```

**Faiblesse identifiée :** Le test vérifie que les deux couleurs sont distinctes
et appartiennent à `{3, 7}`, mais n'impose pas quelle couleur est la pièce et
quelle est la cible. Sur la grille fournie (colour 3 = 4 cells, colour 7 = 3 cells),
`piece` devrait être 7 (plus rare) et `target` devrait être 3.

Avec le tri par rareté croissante (`candidates.sort(key=lambda x: (x[0], -x[1]))`),
le code attribue effectivement `piece=7` (3 cells < 4 cells). Le test ne le
vérifie pas explicitement.

**Correction recommandée pour T-FSM-49 :**

```python
# Correction : vérifier l'attribution exacte
assert fsm._piece_colour == 7   # plus rare (3 cells)
assert fsm._target_colour == 3  # moins rare (4 cells)
```

### 4.2 T-FSM-51 — égalité floor/ciel non contrôlée

**Grille du test :**
```python
# row 0-3  : colour 2 (40 cells sky)
# row 4-7  : colour 5 (40 cells floor)
# row 8-9  : colour 3 ou 5
```

Couleur 2 et couleur 5 ont toutes les deux 40 cellules (ex aequo). Le floor est
choisi par `most_common(1)[0][0]`, qui dépend de l'ordre de parcours du Counter
en cas d'égalité — non déterministe entre implémentations Python.

**Constat :** L'audit utilisateur est fondé. La grille de T-FSM-51 contient une
ambiguïté. L'assertion `if fsm._piece_colour >= 0: assert piece_count <= ...`
est trop permissive.

**Correction recommandée pour T-FSM-51 :**
Construire une grille sans égalité : floor=5 à 50 %, ciel=2 à 40 % (> 15 %),
pièce=3 à 5 %. Vérifier que `piece_colour == 3` et que `floor_colour == 5`.

### 4.3 T-FSM-56 — répétition d'un clic échoué

**Constat :** confirmé §3.4 ci-dessus. Le test vérifie l'absence de crash mais
pas l'absence de répétition de clic échoué dans un état identique.

### 4.4 Tableau récapitulatif P1

| Test     | Faiblesse documentée | Sévérité | Action |
|----------|---------------------|----------|--------|
| T-FSM-49 | Attribution piece/target non vérifiée explicitement | P1 | Ajouter assert explicite |
| T-FSM-51 | Grille avec égalité floor/ciel — non déterministe | P1 | Reconstruire sans égalité |
| T-FSM-56 | Fallback blacklist totale : répétition possible | P1 | Tester invariant état-changé |

---

## 5. Avant / après — synthèse des corrections v13.2

### `agent/my_agent_v132.py` — `_SelectPlaceFSM._classify_frame()`

| Fichier | Ligne | Avant (v13.1) | Après (v13.2) |
|---------|-------|---------------|---------------|
| `my_agent_v131.py` | ~1178 | `non_floor = [c for c in by_freq if c != floor and c != 0]` | (absent) |
| `my_agent_v132.py` | 1186–1196 | (absent) | `candidates = [(count, colour) ... MIN_PIECE_CELLS <= count <= max_piece_cells]` |
| `my_agent_v131.py` | ~1180 | `self._piece_colour = non_floor[0]` | (absent) |
| `my_agent_v132.py` | 1201–1205 | (absent) | `candidates.sort(...); self._piece_colour = candidates[0][1]` |

### `agent/my_agent_v132.py` — `_SelectPlaceFSM._pick_cluster_centre()` (NEW)

| Aspect | v13.1 | v13.2 |
|--------|-------|-------|
| Méthode | `random.choice(piece_cells)` | Centroïde global → cellule la plus proche |
| Blacklist | présente (FIX-P0F) | présente — fallback si tout blacklisté |
| Groupes connexes | absent | **absent** (écart doc/code, risque P0-2) |

---

## 6. Validation de la chaîne complète (trois niveaux)

Conformément au protocole d'interprétation de l'audit utilisateur :

| Niveau | État | Preuve |
|--------|------|--------|
| **1. Correction technique** | ✅ VALIDÉ | Code relu ligne par ligne ; 69/69 PASS locaux |
| **2. Correction comportementale** | ⏳ NON PROUVÉ | Exécution Kaggle requise — `piece_colour=3` dans les logs FSM_ACTION |
| **3. Réussite réelle** | ⏳ NON PROUVÉ | `levels_completed ≥ 1` dans GAME_DONE après 500 actions |

---

## 7. Protocole de validation Kaggle (repris de l'audit utilisateur)

Étapes à exécuter sur Kaggle avec `my_agent_v132.py` sur le jeu `r11l` :

1. **Confirmer la version** : `grep VERSION agent/my_agent_v132.py` → `"13.2"`.
2. **Contrôler la perception** : chercher `"piece_colour": 3` et `"target_colour": 15`
   dans les premières lignes `FSM_OBSERVE` et `FSM_ACTION` des logs.
3. **Compter les sélections** : `grep confirmed_selection logs | wc -l` — cible > 5 % des 500 steps.
4. **Contrôler les placements** : chercher `"reason": "confirmed_placement"` dans les transitions.
5. **Contrôler la progression** : chercher `"level_up": true` dans `LEVELS_PROGRESS`.
6. **Résultat final** : chercher `GAME_DONE` + `"levels_completed"` ≥ 1.

**Grille d'interprétation :**

| Résultat observé | Diagnostic |
|-----------------|------------|
| `piece_colour` ≠ 3 dans les logs | Classification encore défaillante — vérifier déploiement |
| `piece_colour=3` + 0 `confirmed_selection` | Centroïde rate la zone cliquable — P0-2 actif |
| `confirmed_selection` > 0 + 0 `confirmed_placement` | FSM SELECT→PLACE fonctionne, PLACE échoue |
| `confirmed_placement` > 0 + `levels_completed=0` | La mécanique de jeu n'est pas comprise |
| `levels_completed ≥ 1` | Première preuve de progression — à reproduire |

---

## 8. Chantiers antérieurs ouverts (invariants, non abandonnés)

| Chantier | Statut | Référence |
|----------|--------|-----------|
| Boucle de contrôle cohérente | Partiellement adressé par FIX-P0B/P0C/P0F | L-049 |
| Distinction changement visuel / progression | Adressé par FIX-P0-C (v12.0) | L-032 |
| Mémoire modifiant une décision ultérieure | `_EpisodicMemory` présent, non prouvé live | L-030 |
| Moteur d'induction ARC | `_RuleMemory` présent, non prouvé live | L-031 |
| Persistance et reproductibilité | 69/69 reproducibles localement | ce rapport |
| Rapport L-035 — publication HTTP 403 | Non résolu — à confirmer | L-035 |
| Groupes connexes dans `_pick_cluster_centre` | OUVERT — anomalie P0-2 | ce rapport |
| Tests T-FSM-49/51/56 renforcés | OUVERT — anomalie P1 | ce rapport |

---

## 9. Conclusion et décision d'audit

**Décision : VALIDATION TECHNIQUE PARTIELLE — exécution Kaggle requise avant v13.3.**

| Critère | Verdict |
|---------|---------|
| 69/69 PASS reproductibles localement | ✅ |
| Correction bug classification v13.1 → v13.2 | ✅ CONFIRMÉ sur code source |
| Centroïde = global (pas groupes connexes) | ⚠️ ÉCART DOCUMENTATION/CODE — risque P0-2 |
| Tests T-FSM-49/51/56 faibles | ⚠️ NON BLOQUANT — à renforcer en v13.3 |
| Comportement comportemental prouvé | ❌ EXÉCUTION KAGGLE REQUISE |
| Réussite réelle prouvée | ❌ EXÉCUTION KAGGLE REQUISE |

**Ne pas ajouter de nouvelle couche cognitive avant l'exécution Kaggle.**  
Les corrections techniques sont réelles et améliorent la probabilité de succès sur
`r11l`. Les anomalies résiduelles P0-2 et P1 sont documentées pour v13.3.

**Avancement L-051 : 100 %**

---

*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
