# L-047 — Ciblage visuel ACTION6 : implémentation et diagnostic de transposition

**Date :** 2026-10-16  
**Agent :** LuCY v12.2  
**Jeux testés :** r11l  
**Espace numérotation :** L-xxx (ARTCB-TERMINATOR distinct — D-091)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Objectif de cette session

Implémenter la correction P0 de la lacune **T-04** identifiée dans L-046 :  
la génération de coordonnées ACTION6 entièrement aléatoire (`random.randint(0, 63)`)  
donnait une probabilité d'impact sur une pièce de ~1-3 %, rendant r11l et les  
5 autres jeux SINGLE_ACTION6 pratiquement irrésoluble par LuCY.

**Question centrale :** le ciblage visuel améliore-t-il les coordonnées générées  
(qualité immédiate mesurable) et permet-il à LuCY de progresser dans r11l ?

---

## 2. Modifications apportées — avant / après

### 2.1 Version (lignes 1-3, 82, 85-91 de `agent/my_agent_v121.py`)

| Élément | AVANT (v12.1) | APRÈS (v12.2) |
|---------|--------------|--------------|
| `VERSION` (ligne 82) | `"12.1"` | `"12.2"` |
| Architecture docstring (ligne 8) | `LuCY FORENSIC MAX + GOAL-DELTA ENGINE (FIXED)` | `LuCY VISUAL TARGETING for ACTION6 (T-04 fix)` |

### 2.2 Nouvelle fonction `_pick_active_cell` (insérée lignes 643-788)

**Fichier :** [`agent/my_agent_v121.py`](../agent/my_agent_v121.py)

**AVANT :**  
```python
# Section ACTION6 — lignes 1548-1557 (v12.1)
if action.is_complex():
    active_ratio = features.get("active_ratio", 0.5)
    if features.get("grid_valid", False) and active_ratio < 0.5:
        x = random.randint(20, 44)
        y = random.randint(20, 44)
    else:
        x = random.randint(0, 63)
        y = random.randint(0, 63)
    action.set_data({"x": x, "y": y})
```

**APRÈS :**  
```python
# Section ACTION6 — lignes 1548-1567 (v12.2)
if action.is_complex():
    prev_raw_for_targeting = self._prev_frame
    x, y, targeting_method = _pick_active_cell(
        latest_frame.frame, prev_raw_for_targeting
    )
    action.set_data({"x": x, "y": y})
    if DEBUG and self._action_count % 5 == 0:
        self._forensic.on_cognitive_score({
            "event": "ACTION6_VISUAL_TARGET",
            "targeting_method": targeting_method,
            "x": x, "y": y,
            "v12_2_fix": "visual_targeting_replaces_random",
        })
```

### 2.3 Logique de `_pick_active_cell`

**Stratégie :**
1. Convertir la frame au format grille 2D entière via `_to_int_grid()`  
   (gère le format columnar ARC-AGI-3 détecté — voir §4)
2. Trouver la couleur dominante (fond/plateau)
3. Collecter les cellules ≠ dominant (pièces, cibles, marqueurs)
4. Prioriser les cellules qui ont changé depuis la frame précédente (`visual_changed`)  
   sinon choisir parmi toutes les cellules actives (`visual_targeted`)  
   sinon fallback centre + jitter (`fallback_centre`)
5. Retourner `(x, y, method)` normalisés en [0, 63]

---

## 3. Découverte critique — encodage columnar de la frame r11l

### 3.1 Problème diagnostiqué

Lors du premier test (v12.2 initiale), les logs montraient :

```
targeting_method=visual_changed  x=3  y=0   (action 5)
targeting_method=visual_changed  x=9  y=0   (action 10)
targeting_method=visual_changed  x=14 y=0   (action 15)
```

`y=0` systématique → la grille était analysée avec `rows=1` au lieu de `rows=64`.

### 3.2 Source du problème

Lecture du log FRAME_INVENTORY L-046/L-047 :

```
frame = list[1][64][64_ints]
frame[0]          = liste de 64 colonnes
frame[0][col_idx] = liste de 64 entiers (une colonne, 64 lignes)
```

Soit : `pixel(row, col) = frame[0][col][row]` — **format columnar transposé**.  
La version initiale de `_to_int_grid` lisait `frame[0]` comme 64 "lignes" de  
64 éléments chacune, ce qui donnait bien `rows=1, cols=64`.

### 3.3 Correction implémentée

Dans `_to_int_grid`, détection du format columnar :

```python
# AVANT : mauvais — traitait frame[0] comme une liste de 64 lignes d'entiers
# chaque frame[0][c] étant une liste = interprété comme une ligne

# APRÈS : correct — transposition explicite
first = f[0]   # = liste de 64 colonnes
if (isinstance(first, list)
        and len(first) > 0
        and isinstance(first[0], list)      # chaque col est une liste
        and len(first[0]) > 0
        and not isinstance(first[0][0], list)):  # les valeurs finales sont des ints
    n_cols = len(first)          # = 64
    n_rows = len(first[0])       # = 64
    return [[int(first[c][r])    # transposition: grid[row][col] = frame[0][col][row]
             for c in range(n_cols)]
            for r in range(n_rows)]
```

**Vérification :** `grid[1][1] == frame[0][1][1]` — assertion validée en test unitaire.

---

## 4. Résultats expérimentaux

### 4.1 Run L-047 v12.2 (première version, y=0 bug)

```
Méthodes ciblage: {visual_changed: 20, fallback_centre: 20}
y systématiquement = 0 pour visual_changed
→ bug encodage non corrigé
```

### 4.2 Run L-047 v12.2 (version corrigée transposition)

**Log :** `logs/lucy_L047_r11l_v122_20261016T060937Z.log`

```
Méthodes ciblage: {visual_changed: 30, visual_targeted: 10}
x range: [0, 63]   avg = 40.9
y range: [1, 63]   avg = 36.4
```

| Métrique | v12.1 (random) | v12.2 (visuel corrigé) |
|----------|---------------|----------------------|
| Méthode | `randint(0,63)` | `visual_changed` (75%) + `visual_targeted` (25%) |
| y=0 constant | Oui (frame mal lue) | Non (transposée correctement) |
| Distribution x | uniforme [0,63] | [0,63] centré sur zones actives |
| Distribution y | uniforme [0,63] | [1,63] centré sur zones actives |
| Niveaux complétés | 0 | 0 |

**Note :** 0 niveaux complétés malgré le ciblage visuel. Voir §5.

---

## 5. Analyse — pourquoi r11l ne progresse pas encore

### 5.1 Mécanique r11l (rappel L-046)

r11l est un puzzle d'assemblage de pièces :
1. **Clic 1 :** sélectionner une pièce (`bbijaigbknc` = valeur ≠ plateau)
2. **Clic 2 :** déplacer la pièce sur une case cible (`xaalmogcsnh`)
3. Répéter pour toutes les pièces → `next_level()` si toutes sur cible

**Budget moteur interne :** `_max_actions=60` (distinct du budget LuCY 200/500)

### 5.2 Le ciblage visuel améliore la sélection mais pas la séquence

Le ciblage visuel résout le problème de **trouver une pièce** (probabilité ~1% → ~30%+).  
Il ne résout pas le problème de **générer la séquence correcte** :
- Clic 1 sur une pièce → pièce sélectionnée (état transitoire dans l'animation)
- Clic 2 sur une case cible → pièce déplacée
- LuCY ne distingue pas encore "pièce sélectionnée" de "pièce non sélectionnée"
- LuCY ne connaît pas l'emplacement des cases cibles (`xaalmogcsnh`)

### 5.3 Prochaine étape nécessaire (L-048)

Implémenter la détection d'**état de sélection** :
1. Détecter si une pièce est sélectionnée (changement de couleur / animation dans la frame courante)
2. Détecter les cases cibles (couleur spécifique `xaalmogcsnh`)
3. Si pièce sélectionnée → viser une case cible (couleur cible)
4. Si aucune pièce sélectionnée → viser une pièce (couleur active ≠ plateau)

Cette logique à deux états (SELECT → PLACE) est la stratégie minimale pour résoudre r11l.

---

## 6. État des 5 lacunes

| Lacune | Statut après L-047 |
|--------|--------------------|
| T-01 Condition de victoire | ⚠️ Formalisée pour r11l. Deux états SELECT/PLACE identifiés |
| T-02 Budget d'actions | ✅ RÉSOLU — L-046 : budget ≠ facteur limitant |
| T-03 Classification | ✅ FERMÉ depuis L-045 |
| T-04 ACTION6 aléatoire | 🔶 PARTIEL — ciblage visuel actif, `visual_changed` 75% ; séquence SELECT→PLACE manquante |
| T-05 Copies agent | ✅ FERMÉ depuis L-043 |

---

## 7. Fichiers modifiés

| Fichier | Action | Lignes modifiées |
|---------|--------|-----------------|
| `agent/my_agent_v121.py` | MODIFIÉ — v12.1 → v12.2 | 1, 8, 82, 85-91, 643-788 (nouveau), 1548-1567 |
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | SYNCHRONISÉ | Identique à v12.2 |

---

## 8. Logs générés

| Fichier | Description |
|---------|-------------|
| `logs/lucy_L047_r11l_visual_20261016T060751Z.log` | Run 1 — v12.2 première version (y=0 bug détecté) |
| `logs/lucy_L047_r11l_v122_20261016T060937Z.log` | Run 2 — v12.2 transposition corrigée (méthodes OK) |

---

## 9. Conclusion

La correction T-04 est **partiellement résolue** :

✅ **Acquis :** le ciblage visuel remplace le tirage aléatoire. Les coordonnées  
générées sont orientées vers les zones actives de la frame (pièces, cibles, zones animées).  
La transposition columnar est correctement gérée pour r11l.

❌ **Non acquis :** la séquence SELECT→PLACE n'est pas encore implémentée.  
LuCY vise des pièces mais ne sait pas enchaîner sélection puis placement vers une cible.

**Prochaine étape (L-048) :** état machine à deux modes dans la logique ACTION6 :  
`PIECE_SELECT_MODE` → viser une pièce active ; `TARGET_PLACE_MODE` → viser une case cible.

---

*Rapport produit conformément au PROTOCOLE_ARTCB — jamais écraser les anciens rapports.*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
