# L-052 — LuCY v13.3 : BFS groupes connexes + renforcement tests P0-2 / P1

**Date :** 2026-10-16  
**Agent :** LuCY v13.3 (`my_agent_v133.py`)  
**Log JSON :** `logs/lucy_L052_v133_20261016T082932Z.json`  
**Tests :** 86/86 PASS (17 nouveaux + 69 non-régressés)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Objectif

Corriger les anomalies identifiées dans l'audit L-051 :

- **P0-2** : `_pick_cluster_centre()` calculait un centroïde global sur toutes les cellules d'une couleur sans détecter les groupes connexes. Si deux objets de même couleur existaient à deux endroits distincts de la grille, le centroïde tombait dans le vide entre eux.
- **P1 (T-FSM-49)** : le test acceptait n'importe lequel des deux rôles (pièce ou cible) sans vérifier lequel était attribué à quelle couleur.
- **P1 (T-FSM-51)** : la grille de test contenait une égalité entre `floor` et `sky` (40 cells chacun), rendant le choix du terrain dominant non déterministe.
- **P1 (T-FSM-56)** : le test vérifiait uniquement l'absence de crash, sans contrôler que le fallback retournait le centroïde attendu.

---

## 2. Corrections appliquées

### 2.1 FIX-BFS — Nouvelle méthode `_find_connected_groups()`

**Fichier source :** [`agent/my_agent_v133.py`](../agent/my_agent_v133.py)

**AVANT (v13.2, lignes 1249–1275) :**
```python
@staticmethod
def _pick_cluster_centre(cells: list, failed_coords: set) -> Optional[tuple]:
    """Pick the centroid of the largest cluster of cells, excluding blacklist.
    FIX-CLUSTER (v13.2): compute the geometric centre of the available cells
    and return the cell closest to that centroid.
    """
    if not cells:
        return None
    available = [rc for rc in cells if rc not in failed_coords]
    working = available if available else cells  # fallback: ignore blacklist
    if not working:
        return None
    cr = sum(r for r, c in working) / len(working)
    cc = sum(c for r, c in working) / len(working)
    return min(working, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)
```

Problème : `working` = toutes les cellules disponibles de la couleur, sans distinction de groupe. Le centroïde global peut tomber hors de tout objet réel.

**APRÈS (v13.3, nouvelles lignes 1249–1360) :**
```python
@staticmethod
def _find_connected_groups(cells: list) -> list:
    """Detect connected groups of cells using 4-connectivity BFS.
    Returns list of groups sorted by size descending (largest first).
    """
    if not cells:
        return []
    cell_set: set = set(cells)
    visited: set = set()
    groups: list = []
    for start in cells:
        if start in visited:
            continue
        group: list = []
        queue: list = [start]
        visited.add(start)
        while queue:
            r, c = queue.pop(0)
            group.append((r, c))
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in cell_set and nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        groups.append(group)
    groups.sort(key=len, reverse=True)
    return groups

@staticmethod
def _pick_cluster_centre(cells: list, failed_coords: set) -> Optional[tuple]:
    """Pick the centroid of the largest connected cluster, excluding blacklist.
    FIX-BFS (v13.3): parcourt les groupes connexes par taille décroissante.
    """
    if not cells:
        return None
    groups = _SelectPlaceFSM._find_connected_groups(cells)
    for group in groups:
        available = [rc for rc in group if rc not in failed_coords]
        if not available:
            continue  # passe au groupe suivant
        cr = sum(r for r, c in available) / len(available)
        cc = sum(c for r, c in available) / len(available)
        return min(available, key=lambda rc: (rc[0] - cr)**2 + (rc[1] - cc)**2)
    # Fallback : tous les groupes blacklistés
    cr = sum(r for r, c in cells) / len(cells)
    cc = sum(c for r, c in cells) / len(cells)
    return min(cells, key=lambda rc: (rc[0] - cr)**2 + (rc[1] - cc)**2)
```

### 2.2 Renforcement T-FSM-49 → T-FSM-79

**Fichier source :** [`tests/test_lucy_v133_l052.py`](../tests/test_lucy_v133_l052.py)

**AVANT (T-FSM-49) :**
```python
assert fsm._piece_colour != fsm._target_colour
assert fsm._piece_colour in (3, 7)
assert fsm._target_colour in (3, 7)
```
Ne dit pas lequel est la pièce et lequel est la cible.

**APRÈS (T-FSM-79) :**
```python
# piece=7 (3 cells, plus rare), target=3 (4 cells, second rare)
assert fsm._piece_colour == 7   # attribution exacte imposée
assert fsm._target_colour == 3
assert len(fsm._piece_cells) == 3
assert len(fsm._target_cells) == 4
```

### 2.3 Renforcement T-FSM-51 → T-FSM-80

**AVANT (T-FSM-51) :** grille avec floor=5 à 40 cells ET sky=2 à 40 cells — égalité non déterministe.

**APRÈS (T-FSM-80) :** grille 10×10 avec floor=5 à 50 cells, sky=2 à 40 cells, piece=3 à 5 cells. Aucune égalité. Vérification explicite que `piece_colour != 2` (sky exclu) ET `piece_colour == 3` (valide).

### 2.4 Renforcement T-FSM-56 → T-FSM-81

**AVANT (T-FSM-56) :**
```python
assert result is not None
assert result in cells
```

**APRÈS (T-FSM-81) :**
```python
assert result is not None
assert result in cells
# Vérifie que le fallback retourne le centroïde défini — pas une cellule arbitraire
cr = sum(r for r, c in cells) / len(cells)
cc = sum(c for r, c in cells) / len(cells)
expected = min(cells, key=lambda rc: (rc[0]-cr)**2 + (rc[1]-cc)**2)
assert result == expected
```

---

## 3. Résultats des tests

### Suite complète

| Suite | Tests | Résultat |
|-------|-------|---------|
| `test_lucy_v130_l048_fsm.py` (v13.0) | 30 | ✅ 30/30 PASS |
| `test_lucy_v131_l049.py` (v13.1) | 19 | ✅ 19/19 PASS |
| `test_lucy_v132_l050.py` (v13.2) | 20 | ✅ 20/20 PASS |
| `test_lucy_v133_l052.py` (v13.3) | **17** | ✅ **17/17 PASS** |
| **Total** | **86** | **✅ 86/86 PASS** |

### Nouveaux tests v13.3 (T-FSM-67 à T-FSM-83)

| Test | Description | Résultat |
|------|-------------|---------|
| T-FSM-67 | BFS groupe unique compact → 1 groupe | ✅ PASS |
| T-FSM-68 | BFS deux groupes disjoints → 2 groupes | ✅ PASS |
| T-FSM-69 | BFS trois groupes → tri décroissant | ✅ PASS |
| T-FSM-70 | BFS liste vide → [] | ✅ PASS |
| T-FSM-71 | BFS cellule unique → groupe de 1 | ✅ PASS |
| T-FSM-72 | BFS tri par taille décroissante | ✅ PASS |
| T-FSM-73 | BFS diagonale → groupes séparés (4-conn) | ✅ PASS |
| T-FSM-74 | centroïde deux groupes → cible le PLUS GRAND | ✅ PASS |
| T-FSM-75 | plus grand blacklisté → passe au groupe suivant | ✅ PASS |
| T-FSM-76 | tous groupes blacklistés → fallback global | ✅ PASS |
| T-FSM-77 | groupe unique → rétrocompat v13.2 | ✅ PASS |
| T-FSM-78 | blacklist partielle → reste dans grand groupe | ✅ PASS |
| T-FSM-79 | attribution exacte pièce=couleur-plus-rare | ✅ PASS |
| T-FSM-80 | exclusion stricte sky sans égalité floor | ✅ PASS |
| T-FSM-81 | fallback blacklist totale = centroïde défini | ✅ PASS |
| T-FSM-82 | VERSION == "13.3" | ✅ PASS |
| T-FSM-83 | non-régression fixes v13.0/v13.1/v13.2 | ✅ PASS |

---

## 4. Cas critique validé (T-FSM-74)

Ce test démontre concrètement la correction de l'anomalie P0-2 :

- **Données :** groupe grand (6 cells, rows 0–1, cols 0–2) + groupe petit (2 cells, rows 8–9, col 9)
- **Centroïde global v13.2 :** (~3.0, ~3.4) — dans le vide entre les deux groupes
- **v13.3 :** retourne une cellule du grand groupe (row ≤ 1) ✅
- **Assertion explicite :** `assert result[0] <= 1`

---

## 5. Limites restantes (non traitées dans cette version)

| Anomalie | Description | Statut |
|----------|-------------|--------|
| Généralisation classification | La rareté reste une heuristique, pas une compréhension sémantique | OPEN — requiert interaction live |
| Validation Kaggle | v13.3 non encore exécutée sur `r11l` en conditions réelles | OPEN — prochaine étape |
| Score Kaggle v13.2 vs v13.3 | Comparaison quantitative des deux versions | OPEN |
| Compréhension règles jeu | L'agent ne comprend pas les règles — il perçoit + clique | OPEN |

---

## 6. Fichiers modifiés

| Fichier | Action | Description |
|---------|--------|-------------|
| `agent/my_agent_v133.py` | CRÉÉ | v13.3 — FIX-BFS : `_find_connected_groups()` + `_pick_cluster_centre()` BFS |
| `tests/test_lucy_v133_l052.py` | CRÉÉ | T-FSM-67 à T-FSM-83 — 17 nouveaux tests |
| `logs/lucy_L052_v133_20261016T082932Z.json` | CRÉÉ | Log JSON d'exécution |
| `rapports/L-052_bfs_connected_groups_v133_2026-10-16.md` | CRÉÉ | Ce rapport |

**Fichiers NON modifiés :** `my_agent_v132.py`, `test_lucy_v132_l050.py`, tous les rapports antérieurs.

---

## 7. Prochaine étape recommandée

**Exécuter v13.3 sur Kaggle** selon le protocole de validation défini dans L-051 §6 :

1. Vérifier que Kaggle charge bien `my_agent_v133.py`
2. Confirmer que la perception identifie `piece=3`, `target=15` sur `r11l`
3. Observer les clics — vérifier qu'ils tombent sur des objets réels (pas dans le vide)
4. Mesurer : sélections confirmées, placements réussis, niveaux terminés
5. Conserver commit + ID exécution + logs bruts comme preuves

**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**
