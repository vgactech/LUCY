# Rapport L-049 — Réponse à l'audit critique L-048 + Plan LuCY v13.1

**Date :** 2026-10-16  
**Agent :** LuCY v13.0 (commit `c77dfe8` — branch `main`)  
**Audit source :** L-048 — Audit critique de la machine à états ACTION6  
**Statut :** RÉPONSE COMPLÈTE + PLAN v13.1  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Vérification indépendante des 30 tests

L'audit L-048 demandait une confirmation indépendante des 30 tests annoncés, qui
utilisent un stub `arcengine` et non le moteur Kaggle réel.

**Résultat d'exécution locale (Python 3.11.9, pytest 9.1.1) :**

```
30 passed in 0.66s
```

Détail par groupe :

| Groupe | Tests | Résultat |
|---|---|---|
| T-FSM-01…05 — `_validate_transposition` assertions A1–A5 | 5/5 | ✅ PASS |
| T-FSM-06…10 — `_classify_frame` (floor/piece/target) | 5/5 | ✅ PASS |
| T-FSM-11…15 — `_is_confirmed_selection` | 5/5 | ✅ PASS |
| T-FSM-16…20 — `_is_confirmed_placement` | 5/5 | ✅ PASS |
| T-FSM-21…25 — `step()` transitions | 5/5 | ✅ PASS |
| T-FSM-26…30 — Robustesse / edge cases | 5/5 | ✅ PASS |

**Confirmation :** les 30 tests passent sur le code effectivement présent sur `main`. Ce
résultat valide la *logique isolée* de la FSM sur des grilles synthétiques. Il ne valide
pas son comportement sur le moteur ARC-AGI-3 réel — point reconnu dans l'audit et
confirmé ci-dessous.

---

## 2. Réponse point par point aux anomalies P0-A → P0-F

### P0-A — Classification par fréquence de couleur (RETENU — correction v13.1)

**L'audit a raison.** La méthode `_classify_frame()` à la ligne 1064–1098 de
[`my_agent_v130.py`](../agent/my_agent_v130.py:1064) fait exactement l'hypothèse
signalée : `dominant = most_common()[0]`, puis piece/target = 2ᵉ/3ᵉ fréquence.

**Cas problématique confirmé dans le code (ligne 1079) :**
```python
# AVANT (v13.0) — si seulement 2 couleurs :
self._target_colour = non_floor[1] if len(non_floor) >= 2 else self._piece_colour
# → target_colour = piece_colour → target_cells contient des pièces
```

**Correction v13.1 :**
- Ajouter une catégorie `UNKNOWN` quand la grille n'a que 2 couleurs distinctes.
- Introduire un paramètre `min_target_cells=2` : ne promouvoir une couleur en cible que
  si ses cellules sont peu nombreuses ET spatialement distinctes des pièces.
- Tester la classification sur des screenshots réels de `r11l` (à faire via Kaggle).

**Critère de validation :** T-FSM-10 déjà présent couvre le cas 2-couleurs ; ajouter
T-FSM-31 (pièce plus fréquente que le fond) et T-FSM-32 (fond noir avec objets
multi-couleurs) dans v13.1.

---

### P0-B — Confirmation de sélection par changement de couleur (RETENU — correction v13.1)

**L'audit a raison.** `_is_confirmed_selection()` (ligne 1158) vérifie qu'au moins une
cellule du voisinage 3×3 autour du clic a changé. C'est un proxy visuel, pas une
confirmation d'état logique du moteur.

**Faiblesse identifiée dans le code :** le test T-FSM-11 construit exactement la
situation favorable (la cellule cliquée change de `2` à `7`). Il démontre que
*si le changement attendu apparaît, la fonction le détecte* — pas que le moteur
*produit* ce changement quand la sélection réussit.

**Correction v13.1 :**
- Ajouter un état intermédiaire `SELECT_PENDING` : après le clic, attendre 1 frame
  supplémentaire avant de conclure.
- Logger `selection_confidence` : nombre de cellules changées / taille du voisinage.
- Distinguer : `confirmed_selection_visual` (changement vu) vs `confirmed_selection_engine`
  (non disponible sans trace moteur — reste UNKNOWN).

**Critère de validation :** comparer `confirmed_selections` du log forensic au nombre
de sélections *effectives* observées sur une capture vidéo Kaggle.

---

### P0-C — Faux positif sur confirmation de placement (RETENU — correction v13.1)

**L'audit a raison.** `_is_confirmed_placement()` (ligne 1192) utilise deux heuristiques :

1. `active_count < _prev_active_count` — sensible à toute variation de classification.
2. `piece_colour absent du voisinage 5×5` — peut être vrai si la pièce s'est déplacée
   *ailleurs* sur la grille sans être placée en cible.

**Cas de faux positif concret (ligne 1229–1231) :**
```python
for dr in range(-2, 3):
    for dc in range(-2, 3):
        if v == self._piece_colour:
            return False  # piece still present → not placed
return True               # ← FAUX POSITIF si piece s'est déplacée hors zone
```
Si la pièce se déplace de (1,1) vers (4,4) sans se placer en cible, et que le clic était
en (1,1), la zone 5×5 ne contiendra plus la pièce → `True` retourné à tort.

**Correction v13.1 :**
- Vérifier la présence de la pièce sur *toute* la grille, pas seulement dans la zone de clic.
- Ajouter un troisième état de résultat : `PLACEMENT_AMBIGUOUS`.
- Ne réinitialiser le cycle que si `active_count < _prev_active_count AND
  piece_colour absent de toute la grille`.

---

### P0-D — `_validate_transposition` teste des grilles synthétiques, pas la capture courante (RETENU — documentation)

**L'audit a raison.** Le paramètre `frame` reçu par `_validate_transposition(frame)` (ligne
848) n'est utilisé dans *aucune* des 5 assertions. Chaque assertion A1–A5 construit sa
propre grille en dur :

**Avant (v13.0) :**
```python
def _validate_transposition(frame: Any) -> dict:   # frame inutilisé
    ...
    f_a1 = [[[1, 2], [3, 4]]]   # grille synthétique, pas `frame`
    f_a2 = [[[5, 5, 5], ...]]
    f_a3 = [[[0, 0, 0, 0], ...]]
    ...
```

**Correction v13.1 :**
- Renommer en `_validate_transposition_regression()` pour clarifier qu'il s'agit d'un
  test de régression et non d'une vérification de la capture courante.
- Ajouter `_validate_live_frame(frame)` qui vérifie sur `frame` réel : dimensions non
  nulles, toutes valeurs entières, cohérence colonnaire vs rangée, pas de sous-liste
  irrégulière.
- Appeler `_validate_live_frame` à chaque `step()` en mode DEBUG.

---

### P0-E — Les tests vérifient les heuristiques elles-mêmes, pas le moteur (RETENU — plan traces réelles)

**L'audit a raison.** Ce point est structurel : on ne peut pas écrire des tests
d'intégration vrais sans accès au moteur ARC-AGI-3 hors Kaggle.

**Approche v13.1 :**
- Ajouter dans le logger forensic un champ `action_trace` : pour chaque action,
  enregistrer `(prev_fp, action, curr_fp, fsm_state, confirmed_selection, confirmed_placement)`.
- Après une exécution Kaggle, extraire les traces du stdout et rejouer en local pour
  mesurer :
  - **Taux de vrais positifs** : `confirmed=True` ET frame réellement différente de
    manière significative (>5% de cellules changées).
  - **Taux de faux positifs** : `confirmed=True` mais changement local < 2 cellules
    dans le voisinage 3×3.

Ce travail est prévu dans v13.1 mais reste conditionnel à une exécution Kaggle réussie.

---

### P0-F — Récupération après 5 échecs sans stratégie différente (RETENU — correction v13.1)

**L'audit a raison.** `FSM_RECOVERY` (ligne 1259–1267) remet `_consecutive_misses = 0`
et retourne en `OBSERVE`, mais ne conserve pas le diagnostic de l'échec.

**Correction v13.1 :**
```python
# AVANT (v13.0) :
if self._consecutive_misses >= self.MAX_CONSECUTIVE_MISSES:
    self._state = self.OBSERVE
    self._consecutive_misses = 0

# APRÈS (v13.1) :
if self._consecutive_misses >= self.MAX_CONSECUTIVE_MISSES:
    self._failed_state = self._state          # mémoriser l'état en échec
    self._failed_coords.add((self._last_click_r, self._last_click_c))  # blacklist
    self._state = self.OBSERVE
    self._consecutive_misses = 0
```
- `_failed_coords` : ensemble des coordonnées déjà essayées sans succès — exclues des
  prochains choix dans `SELECT` et `PLACE`.
- `_failed_state` : état dans lequel l'échec s'est produit — loggé dans `FSM_RECOVERY`
  pour analyse post-exécution.

---

## 3. Correction du tableau de statut T-04

L'audit signale que le rapport L-048 présente T-04 comme "entièrement résolu".
**Formulation corrigée :**

| Élément | État réel |
|---|---|
| Machine à états implémentée | ✅ Confirmé (code lu + testé) |
| Tests unitaires 30/30 PASS | ✅ Confirmé indépendamment |
| Assertions de transposition A1–A5 | ✅ Correctes sur grilles synthétiques |
| Classification correcte sur captures réelles `r11l` | ❌ Non démontrée |
| Sélections confirmées par le moteur | ❌ Non démontrées |
| Placements confirmés sans faux positif | ❌ Non démontrés |
| Progression dans `r11l` avec v13.0 | ❌ Non démontrée |
| Victoire confirmée | ❌ Non démontrée |

**T-04 = IMPLEMENTED, NOT OPERATIONALLY VALIDATED.**

---

## 4. Incohérence T-01 ↔ T-04 signalée (ACCEPTÉE)

L'audit note que T-01 (condition de victoire) est lié dans le tableau des lacunes à
l'implémentation de SELECT→PLACE, ce qui est incorrect :

- **T-04** = implémenter un cycle structuré SELECT→PLACE (✅ fait en v13.0).
- **T-01** = comprendre et satisfaire la condition de victoire du niveau `r11l`
  (❌ pas encore traité — nécessite une exécution et des traces réelles).

Ces deux tâches sont indépendantes. Le tableau des lacunes sera corrigé dans v13.1.

---

## 5. Plan LuCY v13.1 — Modifications concrètes

**Périmètre v13.1 :** corrections des 6 anomalies P0 + tests supplémentaires.
Aucune nouvelle couche cognitive ajoutée avant validation de la boucle
perception → sélection → confirmation → placement → résultat.

### 5.1 Corrections du code (`my_agent_v131.py`)

| ID | Fichier | Ligne approx. | Modification |
|---|---|---|---|
| FIX-P0A | `_classify_frame()` | 1043 | Ajouter catégorie UNKNOWN + critère `min_target_cells` |
| FIX-P0B | `_is_confirmed_selection()` | 1158 | Ajouter `selection_confidence` + état `SELECT_PENDING` |
| FIX-P0C | `_is_confirmed_placement()` | 1192 | Vérifier piece_colour sur toute la grille, pas seulement zone clic |
| FIX-P0D | `_validate_transposition()` | 848 | Renommer en `_regression` + ajouter `_validate_live_frame()` |
| FIX-P0E | `_KaggleForensicLogger` | 161 | Ajouter champ `action_trace` pour analyse post-exécution |
| FIX-P0F | `_SelectPlaceFSM.step()` | 1259 | Ajouter `_failed_coords` + `_failed_state` à la récupération |

### 5.2 Tests supplémentaires (`tests/test_lucy_v131_l049.py`)

| ID | Ce que le test vérifie |
|---|---|
| T-FSM-31 | Classification quand pièce > fond en fréquence (P0-A cas inversé) |
| T-FSM-32 | Fond noir (0) avec 3 objets de couleurs différentes — pas de confusion floor/piece |
| T-FSM-33 | Faux positif P0-C : pièce déplacée hors zone clic → placement NOT confirmed |
| T-FSM-34 | `_validate_live_frame` détecte une frame malformée (sous-listes irrégulières) |
| T-FSM-35 | Récupération P0-F : coordonnées blacklistées non réutilisées immédiatement |
| T-FSM-36 | Uniformité grille (même couleur partout) → piece_colour=-1 + action fallback |

### 5.3 Indicateurs à mesurer en exécution Kaggle

| Indicateur | Source | Seuil cible |
|---|---|---|
| `confirmed_selections` / tentatives SELECT | Log FSM_TRANSITION | > 20 % |
| `confirmed_placements` / tentatives PLACE | Log FSM_TRANSITION | > 10 % |
| Faux positifs sélection | `changed_cells < 2` AND `confirmed=True` | < 30 % |
| Récupérations / partie | Log FSM_RECOVERY | < 10/partie |
| `levels_completed` après 500 actions | Log GAME_DONE | ≥ 1 |

---

## 6. Ce qui n'est PAS dans v13.1

Conformément à la recommandation de l'audit :

> *"Ne pas ajouter davantage de contrôleurs cognitifs pour l'instant."*

- ❌ Pas de nouveau module cognitif.
- ❌ Pas de modification du budget (reste 500 / 80).
- ❌ Pas de modification de `_GoalDeltaTracker`, `_EpisodicMemory`, `_RuleMemory`.
- ❌ Pas de V13.1 sans exécution Kaggle de V13.0 d'abord pour obtenir des traces.

---

## 7. État d'avancement

**Avancement L-049 : 100 %**

| Étape | Statut |
|---|---|
| Lecture code v13.0 ligne par ligne | ✅ |
| Exécution indépendante 30 tests | ✅ — 30/30 PASS en 0.66s |
| Réponse aux 6 anomalies P0 | ✅ |
| Correction du statut T-04 | ✅ |
| Plan v13.1 (corrections + tests) | ✅ |
| Rapport L-049 produit | ✅ |

**Prochaine action :** implémenter les FIX-P0A→P0F dans `my_agent_v131.py` + 6 tests
supplémentaires T-FSM-31→36 + commit + push.

---

*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
