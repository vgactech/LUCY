# L-046 — Diagnostic r11l : budget, stratégie, condition de victoire

**Date :** 2026-10-16  
**Agent :** LuCY v12.1  
**Dépôt :** `vgactech/LUCY`  
**HEAD :** `a231368` (avant modifications L-046)  
**Espace de numérotation :** L-xxx (distinct ARTCB R-xxx — règle D-091)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 0. Contexte et objectif

Ce rapport répond directement à l'audit critique soumis par l'utilisateur (reprise après L-036). L'audit pose la question centrale :

> **LuCY apprend-elle effectivement à résoudre les jeux, ou se contente-t-elle d'exécuter des actions en accumulant des données ?**

L'expérience P0 recommandée était : tester r11l avec 500 actions maximum. Ce rapport documente les résultats mesurés, les preuves extraites des logs bruts, et les conclusions architecturales.

---

## 1. Modifications effectuées (avant / après)

### Fichier : `LuCY/agent/my_agent_v121.py`

**AVANT (lignes 85–88) :**
```python
# Action budgets — C-003 curriculum phase (2026-10-15): extended for r11l diagnosis
# AVANT: MAX_ACTIONS_TOTAL=80, MAX_ACTIONS_PER_LEVEL=30
# APRÈS: MAX_ACTIONS_TOTAL=200, MAX_ACTIONS_PER_LEVEL=80
MAX_ACTIONS_TOTAL = 200
```

**APRÈS (lignes 85–91) :**
```python
# Action budgets — C-003 curriculum phase (2026-10-15): extended for r11l diagnosis
# AVANT: MAX_ACTIONS_TOTAL=80, MAX_ACTIONS_PER_LEVEL=30
# C-003: MAX_ACTIONS_TOTAL=200, MAX_ACTIONS_PER_LEVEL=80
# L-046 (2026-10-16): extended to 500 for r11l budget diagnosis (T-02)
# AVANT: MAX_ACTIONS_TOTAL=200
# APRÈS: MAX_ACTIONS_TOTAL=500
MAX_ACTIONS_TOTAL = 500
```

**Motivation :** Anomalie T-02 — `play_local.py --max-steps 500` est ignoré car `MyAgent` lit uniquement `MAX_ACTIONS_TOTAL` (ligne 1117 : `if self._action_count >= MAX_ACTIONS_TOTAL - 1`), jamais le paramètre CLI. La seule façon d'étendre le budget est de modifier la constante.

**Synchronisation vendor :**
```bash
cp LuCY/agent/my_agent_v121.py LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py
```

---

## 2. Expérience contrôlée — r11l 500 actions

### Commande exécutée
```bash
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter
source .venv/bin/activate
python scripts/play_local.py --game r11l --max-steps 500
```

### Résultats mesurés

| Indicateur | Valeur |
|------------|--------|
| Log produit | `logs/lucy_L046_r11l_500steps_20261016T030337Z.log` (982 KB) |
| Total actions exécutées | **499** |
| Niveaux complétés | **0** |
| Score final | **0.0** |
| État final | `GameState.NOT_FINISHED` |
| Raison d'arrêt | `BUDGET_EXHAUSTED` |
| Durée d'exécution | 14,27 secondes |
| FPS moyen | 34,99 |
| real_level_ups | **0** |

### Comparaison L-045 vs L-046

| Métrique | L-045 (200 actions) | L-046 (500 actions) | Delta |
|----------|---------------------|---------------------|-------|
| Actions totales | 199 | 499 | +300 |
| Niveaux complétés | 0 | 0 | 0 |
| real_progress | False constant | False constant | aucun |
| goal_found | False constant | False constant | aucun |
| stuck_streak | 0 constant | 0 constant | aucun |
| transform_type | GROWING constant | GROWING constant | aucun |
| net_change/action | +3 pixels | +3 pixels | aucun |
| PS confidence finale | ~41 | **127** | +86 |

**La confiance PS a triplé, mais le résultat est identique : 0 niveau.**

---

## 3. Lecture brute des logs — observations ligne par ligne (L-060)

### O-001 — `max_actions_total=200` dans GAME_INIT malgré MAX=500
**Log ligne 15 (L-045) :** `"max_actions_total":200` dans l'événement `GAME_INIT`  
**Log ligne 15 (L-046) :** `"max_actions_total":500` dans l'événement `GAME_INIT` ✅  
→ La modification a bien été prise en compte.

### O-002 — `win_levels=6` constant depuis le départ
**Log ligne 19 :** `win_levels_at_game_start=6 (= total game levels, NOT LuCY wins)`  
→ `win_levels` est le **nombre total de niveaux du jeu**, PAS les victoires de LuCY. Ce champ ne peut jamais diminuer. Il restera à 6 jusqu'à la fin.

### O-003 — `stuck_streak=0` constant sur 499 actions
Présent dans chaque événement `ACTION_BEFORE`, de seq=5 à seq=1998.  
→ L'agent ne détecte jamais qu'il est bloqué. Le mécanisme `STUCK_THRESHOLD=5` ne se déclenche pas parce que l'empreinte visuelle (`fp_prefix`) change à chaque action (+3 pixels aléatoires).

### O-004 — Phase `exploit` dès l'action 2
`phase="explore"` à l'action 1, `phase="exploit"` dès l'action 2, et **jamais plus `explore`**.  
→ La règle PS est validée après 1 seule observation. Confidence atteint 127 à la fin. L'agent est **convaincu** que son comportement est correct, alors qu'il ne progresse pas.

### O-005 — `goal_delta=null` sur toutes les 499 actions
`goal_delta_before=null`, `goal_delta_after=null`, `goal_delta_improvement=0.0` sur TOUS les événements.  
→ `goal_found=false` constant. Le `_GoalDeltaTracker` n'a jamais trouvé de frame goal dans r11l. Sans état cible connu, il est impossible de mesurer la progression vers la victoire.

### O-006 — `net_change=+3` sur 490 des 499 actions (quelques +6)
Exemples d'actions 3, 4, 5, 6, 7… : `net_change=3` constant. Quelques actions : `net_change=6`.  
→ À chaque ACTION6 avec coordonnées (x, y) aléatoires, le jeu génère 3 nouveaux pixels visibles. Ce n'est pas un mouvement de pièce : c'est l'animation d'une **opération de clic invalide** sur la caméra.

### O-007 — `comparable=false` sur la première action, `comparable=true` ensuite
L'action 1 produit `"comparable":false` (pas encore de frame précédent).  
À partir de l'action 2 : `"comparable":true` avec `changed_pixels` variant de 231 à 365.  
→ L'agent voit des changements visuels réels, mais ils ne correspondent pas à des coups valides.

### O-008 — `n_visual_change: {"6": 432}` dans le GAME_DONE
432 des 491 actions effectives ont généré un changement visuel.  
`n_progress_real: {}` — aucune progression réelle.  
→ LuCY **voit** du mouvement à 88% des coups, mais **0%** de ces mouvements constituent une progression.

---

## 4. Analyse de la mécanique r11l (lecture du code source)

### Source lue : `environment_files/r11l/495a7899/r11l.py`

**Mécanique réelle du jeu r11l :**
1. La grille contient des **pièces de puzzle** (`bbijaigbknc`) et des **obstacles** (`tdriqoljcbs`)
2. ACTION6 avec `data={"x": X, "y": Y}` est un **clic** sur la grille
3. Si le clic tombe sur une pièce → **sélection** de la pièce (`ecernfbexd`, ligne 1532)
4. Si une pièce est sélectionnée et le clic tombe sur une case libre → **déplacement** vers la cible (`hcpsunmfnx`, ligne 1568)
5. Si le déplacement est valide : la pièce se déplace en **animation** (`yfbjozweime=True`)
6. Si la pièce atteint sa **position cible** (`xaalmogcsnh`) → validation (`ongkreqtjqjqfq=True`)
7. Quand **toutes les pièces** sont sur leur cible → `next_level()` (ligne 1706)
8. **Budget moteur interne :** `_max_actions=60` (ligne 1407) — le moteur impose `lose()` si épuisé

**Condition de victoire r11l :**
> Toutes les pièces du puzzle (`bbijaigbknc`) doivent être placées sur leur cible (`xaalmogcsnh`). Le niveau suivant est déclenché quand `uyawyyswbya=True` ET aucune animation en cours (`flgzyjcqcspeg=False`).

**Pourquoi LuCY ne peut pas gagner avec la stratégie actuelle :**
- ACTION6 est généré avec des coordonnées aléatoires dans une grille 64×64 discrétisée par pas de 4 (256 positions possibles)
- La probabilité de cliquer sur une pièce est : `nb_pièces / 256 ≈ 3–8 / 256 ≈ 1–3%` par action
- Même en cliquant sur une pièce, la probabilité de cliquer ensuite sur la bonne case cible est encore `1/256`
- La probabilité de compléter un niveau par aléatoire pur = `(3%) × (3%) × (n_pieces)^2 ≈ 0.01%`

**Preuve du blocage moteur :**
```python
# r11l.py ligne 1809
if self._action_count >= self._max_actions:  # _max_actions=60
    self.lose()
    self.complete_action()
    return
```
Chaque fois que l'agent dépasse 60 coups sans compléter un niveau, le moteur appelle `lose()`. Ceci réinitialise probablement l'état interne du niveau, effaçant toute progression partielle.

---

## 5. Résolution des 5 lacunes — état mis à jour

### T-01 — Condition de victoire
**AVANT L-046 :** Non formalisée pour r11l  
**APRÈS L-046 :** ✅ **FORMALISÉE**

```
JEU : r11l (puzzle d'assemblage de pièces)
ÉTAT INITIAL : N pièces à positions initiales, M cases cibles
ACTIONS VALIDES : [ACTION6 (x, y)] — clic sur la grille
CONDITION DE VICTOIRE :
  Pour chaque pièce P_i :
    position(P_i) = cible(P_i)  AND  aucune animation en cours
  → next_level() déclenché
  → 6 niveaux au total (win_levels=6)
BUDGET MOTEUR INTERNE : 60 actions max (lose() si dépassé)
STRATÉGIE REQUISE : sélection précise (clic sur pièce) + placement précis (clic sur cible)
```

**Statut T-01 global :** ⚠️ Formalisée pour r11l et ls20 (L-044). Reste 23/25 jeux non formalisés.

### T-02 — Budget d'actions
**AVANT L-046 :** `MAX_ACTIONS_TOTAL=200` non extensible via CLI  
**APRÈS L-046 :** `MAX_ACTIONS_TOTAL=500` — correctement étendu  
**Résultat du test :** 499 actions → **0 niveaux** — confirme que le budget n'est PAS le facteur limitant  
**Statut T-02 :** ✅ **RÉPONSE DÉFINITIVE** — augmenter le budget ne résout pas r11l

### T-03 — Classification
**Statut T-03 :** ✅ **FERMÉ** depuis L-045 (25/25 jeux classifiés)

### T-04 — ACTION6 aléatoire (jeux SINGLE_ACTION6)
**AVANT L-046 :** problème identifié mais non quantifié  
**APRÈS L-046 :** **QUANTIFIÉ** — 0% d'efficacité sur 499 coups  
**Root cause confirmée :** coordonnées (x, y) aléatoires ne permettent pas de cibler les pièces  
**Statut T-04 :** 🔴 **OUVERT** — nécessite une stratégie de ciblage

### T-05 — Copies de l'agent
**Statut T-05 :** ✅ **FERMÉ** depuis L-043

---

## 6. Réponse à la question centrale de l'audit

> **LuCY apprend-elle effectivement à résoudre les jeux ?**

**Réponse honnête basée sur les preuves mesurées :**

**NON** pour r11l, avec les preuves suivantes :

| Critère | Preuve | Verdict |
|---------|--------|---------|
| Progression réelle | `real_progress=False` sur 499 actions | ❌ Non |
| Adaptation stratégique | Phase `exploit` dès action 2, jamais remise en question | ❌ Non |
| Détection de blocage | `stuck_streak=0` constant | ❌ Non |
| Apprentissage transférable | `goal_found=False` → pas de modèle de victoire formé | ❌ Non |
| Accumulation utile | `PS confidence=127` → faux positif | ❌ Trompeuse |

**Ce que LuCY fait réellement :**
1. Elle exécute ACTION6 avec des coordonnées aléatoires
2. Elle observe des changements visuels (+3 pixels/action)
3. Elle renforce cette règle (confidence +1 par action)
4. Elle **croit progresser** car la règle est visuellement validée
5. Elle **ne progresse pas** car les changements ne constituent pas des coups valides

**Analogie :** c'est comme apprendre à jouer aux échecs en déplaçant les pièces au hasard et en notant que les cases changent de couleur.

---

## 7. Validation de l'audit critique C-003 et C-004

### C-003 — Augmentation du budget : verdict confirmé

L'audit a correctement prédit :
> *"si l'agent répète une action inefficace, il consomme davantage de ressources sans améliorer sa stratégie"*

**Confirmé par les données :** 200 actions → 499 actions → résultat identique (0 niveaux).

### C-004 — Diagnostic de r11l : verdict partiellement correct

L'audit a dit :
> *"environ 400 actions seraient nécessaires"*

Cette estimation était incorrecte dans son hypothèse implicite. Il ne s'agit pas d'un problème de budget mais de **précision de ciblage**. Même avec 10 000 actions, la probabilité de victoire par aléatoire pur reste inférieure à 1% pour ce type de puzzle.

---

## 8. Plan de correction — prochaines étapes

### P0 — Corriger le ciblage ACTION6 pour r11l et les 5 SINGLE_ACTION6

**Problème :** `random.randint(0, 63)` pour x et y (lignes 1404-1413 de `my_agent_v121.py`)  
**Solution requise :** analyse de la frame pour **identifier les pièces** (zones actives non-background) avant de générer une ACTION6 ciblée

**Algorithme minimal :**
```python
# 1. Scanner la frame pour trouver les objets (couleur != background)
# 2. Identifier les centroïdes des pièces
# 3. ACTION6 ciblé sur un centroïde de pièce
# 4. Si pièce sélectionnée (changement détecté), ACTION6 sur la zone cible vide
# 5. Répéter pour chaque pièce
```

### P1 — Formaliser les conditions de victoire pour les 23 jeux restants

En priorité : tn36, vc33, s5i5, lp85, ft09 (autres SINGLE_ACTION6), puis les MULTI_4/5/6.

### P1 — Corriger la détection de blocage

**Problème :** `stuck_streak=0` car l'empreinte `fp_prefix` change à chaque action  
**Solution :** mesurer la progression **vers les cibles** (delta de position des pièces), pas la variation de pixels totale

### P2 — Curriculum basé sur les résultats mesurés

Ordre recommandé (par probabilité de succès croissante) :
1. Jeux à actions séquentielles simples (mouvements directionnels)
2. Jeux avec signal de victoire détectable (`goal_found=True` possible)
3. Jeux MULTI_4 avec actions [1,2,3,4] (plus explicites)
4. Jeux SINGLE_ACTION6 en dernier (nécessitent ciblage précis)

---

## 9. Logs générés et vérification

| Fichier | Taille | Vérifié |
|---------|--------|---------|
| `logs/lucy_L046_r11l_500steps_20261016T030337Z.log` | 982 KB | ✅ |
| `logs/lucy_L046_r11l_500steps_20261016T030329Z.log` | 180 B (stdout) | ✅ |

```
GAME_DONE:
  reason: BUDGET_EXHAUSTED
  levels_completed: 0
  win_levels_at_start: 6
  win_levels_at_end: 6
  real_level_ups: 0
  total_actions: 499
  elapsed_ms: 14267.59
  n_progress_real: {}
  n_visual_change: {"6": 432}
```

---

## 10. Résumé exécutif

| Question | Réponse |
|----------|---------|
| 500 actions résolvent-elles r11l ? | **NON** — 0 niveau complété |
| Le budget est-il le facteur limitant ? | **NON** — stratégie incapable de cibler les pièces |
| LuCY apprend-elle à jouer ? | **NON** — renforcement d'une règle aléatoire inefficace |
| Quel est le vrai problème ? | **Ciblage** — ACTION6 doit viser les pièces, pas des positions aléatoires |
| Quelle est la prochaine étape ? | **Analyse visuelle de la frame** pour extraire les positions des pièces |

**T-02 (budget) : RÉSOLU** — budget étendu à 500, non-résolution confirmée  
**T-04 (ACTION6) : OUVERT** — nécessite un ciblage visuel  
**T-01 (condition victoire r11l) : FORMALISÉE**

---

*Rapport produit conformément au PROTOCOLE_ARTCB : logs lus intégralement, avant/après documenté, preuves mesurées uniquement, aucun hardcoding.*  
*Mode DEBUG actif | CERTIFIED_100=false | unique_human_proven=false*
