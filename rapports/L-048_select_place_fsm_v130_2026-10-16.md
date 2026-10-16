# L-048 — Machine à états SELECT→PLACE : implémentation et validation

**Date :** 2026-10-16  
**Agent :** LuCY v13.0  
**Jeux ciblés :** r11l (et tout jeu ACTION6 à deux phases)  
**Espace numérotation :** L-xxx (ARTCB-TERMINATOR distinct — D-091)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Objectif

Compléter la correction T-04 (initiée en L-047) en implémentant la boucle décisionnelle
complète pour ACTION6 :

| Étape | v12.2 (L-047) | v13.0 (L-048) |
|-------|--------------|--------------|
| Ciblage des pièces | ✅ visuel | ✅ visuel (hérité) |
| Distinction SELECT/PLACE | ❌ absent | ✅ _SelectPlaceFSM |
| Confirmation de sélection | ❌ absent | ✅ delta couleur 3×3 |
| Confirmation de placement | ❌ absent | ✅ delta comptage actif |
| Récupération sur échec | ❌ absent | ✅ MAX_CONSECUTIVE_MISSES=5 |
| Validation transposition | Diagnostic seul | ✅ 5 assertions déterministes |

---

## 2. Modifications apportées — avant / après

### 2.1 Nouveau fichier agent

| Élément | AVANT (v12.2) | APRÈS (v13.0) |
|---------|--------------|--------------|
| Fichier | `agent/my_agent_v121.py` | `agent/my_agent_v130.py` |
| `VERSION` | `"12.2"` | `"13.0"` |
| Architecture | LuCY VISUAL TARGETING | L-048 SELECT→PLACE FSM |

### 2.2 Nouvelles classes et fonctions (insérées après la ligne 842)

**`_validate_transposition(frame)` (lignes 843–942)**

**AVANT :** Diagnostic conversationnel du bug y=0 (rapport L-047 §3.2).

**APRÈS :**
```python
def _validate_transposition(frame: Any) -> dict:
    """5 assertions déterministes sur la logique de transposition columnar."""
    # A1: 2×2 asymétrique — pixel(0,0)≠pixel(1,0)
    # A2: uniforme — toutes valeurs égales après conversion
    # A3: cellule unique en (col=1, row=2) → grid[2][1]=7
    # A4: frame vide/None → pas de crash
    # A5: dimensions préservées (4 cols × 3 rows → 3 rows × 4 cols)
    return {"ok": bool, "passed": int, "failed": int, "details": list}
```

**`_SelectPlaceFSM` (lignes 943–1240)**

**AVANT :** `_pick_active_cell()` — ciblage visuel sans état.

**APRÈS :**
```
États :
  OBSERVE  → classifier les cellules (pièce/cible/fond) → SELECT
  SELECT   → viser une pièce → confirmer sélection → PLACE
             (échec × MAX_CONSECUTIVE_MISSES → OBSERVE)
  PLACE    → viser une cible → confirmer placement → OBSERVE
             (échec × MAX_CONSECUTIVE_MISSES → OBSERVE)

Confirmation sélection : changement de couleur dans zone 3×3 autour du clic.
Confirmation placement : comptage actif diminue OU couleur pièce absente près du clic.
```

### 2.3 MyAgent.__init__ (lignes ~1827)

**AVANT :**
```python
self._forensic = _KaggleForensicLogger(...)
self._perceptor = _GridPerceptor()
```

**APRÈS :**
```python
self._forensic = _KaggleForensicLogger(...)
self._perceptor = _GridPerceptor()
# L-048 : FSM SELECT→PLACE (une instance par jeu)
self._fsm = _SelectPlaceFSM()
self._transposition_validated: bool = False
```

### 2.4 Premier frame — validation transposition (lignes ~1920)

**AVANT :** capture `win_levels_at_game_start` uniquement.

**APRÈS :** + appel `_validate_transposition()` une fois avec émission forensique
`TRANSPOSITION_VALIDATION` (5/5 attendus).

### 2.5 Section ACTION6 (lignes ~2188)

**AVANT (v12.2) :**
```python
x, y, targeting_method = _pick_active_cell(latest_frame.frame, self._prev_frame)
```

**APRÈS (v13.0) :**
```python
x, y, targeting_method = self._fsm.step(
    latest_frame.frame, self._prev_frame,
    logger=self._forensic, action_count=self._action_count,
)
```

### 2.6 Robustesse `_to_int_grid` dans `_SelectPlaceFSM`

**AVANT :** branche 3D `isinstance(cell, list)` sans guard sur liste vide → TypeError.

**APRÈS :**
```python
try:
    return [[int(cell[0]) if isinstance(cell, list) and cell
             else (int(cell) if not isinstance(cell, list) else 0)
             for cell in row] for row in frame]
except (TypeError, ValueError):
    return None
```

---

## 3. Résultats des tests

### 3.1 Suite L-048 : 30/30 PASS

**Fichier :** `tests/test_lucy_v130_l048_fsm.py`

| Groupe | Tests | Résultat |
|--------|-------|----------|
| T-FSM-01→05 _validate_transposition | 5 | ✅ PASS |
| T-FSM-06→10 _classify_frame | 5 | ✅ PASS |
| T-FSM-11→15 _is_confirmed_selection | 5 | ✅ PASS |
| T-FSM-16→20 _is_confirmed_placement | 5 | ✅ PASS |
| T-FSM-21→25 .step() transitions | 5 | ✅ PASS |
| T-FSM-26→30 Robustesse | 5 | ✅ PASS |
| **Total** | **30** | **30/30 PASS** |

---

## 4. État de la lacune T-04 après L-048

| Lacune | Statut après L-048 |
|--------|-------------------|
| T-01 Condition de victoire | ✅ Boucle SELECT→PLACE implémentée |
| T-02 Budget d'actions | ✅ RÉSOLU (L-046) |
| T-03 Classification | ✅ FERMÉ (L-045) |
| T-04 ACTION6 aléatoire | ✅ RÉSOLU — FSM SELECT→PLACE avec confirmation |
| T-05 Copies agent | ✅ FERMÉ (L-043) |

**Note :** La validation expérimentale sur r11l (progression mesurable confirmée par
le moteur ARC-AGI-3) reste à démontrer via un run Kaggle. La FSM est fonctionnelle et
testée sur frames synthétiques — le run réel est la prochaine étape.

---

## 5. Limites documentées

- **Heuristiques vs règles du jeu :** la FSM utilise des heuristiques de changement de
  couleur pour détecter sélection/placement. Si r11l utilise une animation (couleur
  transitoire) plutôt qu'un changement permanent, la confirmation peut être prématurée.
- **Couleur dominante = fond :** hypothèse non vérifiée sur tous les jeux ARC-AGI-3.
  Le fond peut ne pas être la couleur la plus fréquente (ex: grille vide).
- **Un seul type de pièce :** la classification distingue 3 couleurs maximum. Des jeux
  avec plus de types d'objets nécessiteront une extension.
- **`unique_human_proven=False`, `CERTIFIED_100=False`** — invariants maintenus dans tout le code.

---

## 6. Fichiers modifiés

| Fichier | Action | Détail |
|---------|--------|--------|
| `agent/my_agent_v130.py` | CRÉÉ | v13.0 — FSM + validation transposition |
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | SYNCHRONISÉ | Identique à v13.0 |
| `tests/test_lucy_v130_l048_fsm.py` | CRÉÉ | 30 tests T-FSM-01→30 |

---

## 7. Nouveaux événements forensiques (logger)

| Événement | Déclencheur |
|-----------|-------------|
| `TRANSPOSITION_VALIDATION` | Premier frame — 5 assertions A1–A5 |
| `FSM_OBSERVE` | Chaque transition vers OBSERVE (classification) |
| `FSM_TRANSITION` | SELECT→PLACE ou PLACE→SELECT |
| `FSM_MISS` | Confirmation échouée (SELECT ou PLACE) |
| `FSM_RECOVERY` | MAX_CONSECUTIVE_MISSES atteint → reset OBSERVE |
| `FSM_ACTION` | Coordonnées choisies + état courant |

---

## 8. Conclusion

T-04 est maintenant **entièrement implémentée** du côté logique :

✅ **Machine à états SELECT→PLACE** avec 3 états, 2 heuristiques de confirmation, récupération automatique.  
✅ **Validation transposition** : 5 assertions déterministes, aucune régression.  
✅ **30/30 tests PASS**.  
✅ **Robustesse** : pas de crash sur frames None, vides, mal formées.

❌ **Non encore validé :** progression mesurable confirmée sur r11l via run Kaggle réel.

**Prochaine étape :** run local `make play-local` sur r11l avec v13.0, mesurer
`confirmed_selections`, `confirmed_placements` et niveaux complétés.

---

*Rapport produit conformément au PROTOCOLE_ARTCB — jamais écraser les anciens rapports.*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
