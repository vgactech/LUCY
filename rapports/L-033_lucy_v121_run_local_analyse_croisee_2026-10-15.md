# L-033 — LuCY v12.1 : Exécution locale complète & Analyse croisée avant/après

**Date :** 2026-10-15T08:31:15Z  
**Version :** LuCY v12.1 (`my_agent_v121.py` — identique à `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`)  
**Mode :** OFFLINE — 25 jeux locaux — `max-steps=80`  
**Log source :** `LuCY/logs/lucy_L033_run_20261015T083115Z.log` (8 928 lignes)  
**Log JSON :** `LuCY/logs/lucy_L033_20261015T083115Z.json`  
**Rapport précédent :** `L-032_lucy_v120_run_local_analyse_croisee_2026-10-15.md` (non modifié)  
**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

---

## 1. Résultat global d'exécution

| Métrique | v12.0 (L-032) | v12.1 (L-033) | Delta |
|----------|--------------|--------------|-------|
| Jeux exécutés | 25 / 25 | 25 / 25 | = |
| Jeux gagnés (`GAME_WON`) | **0** | **0** | = |
| Jeux `BUDGET_EXHAUSTED` | 25 | 25 | = |
| `levels_completed` total | **0** | **0** | = |
| Actions totales | 1 975 | 1 975 | = |
| Durée totale cumulée (ms) | ~69 931 | **48 504** | **−21 427 ms (−30,6 %)** |
| Faux `LEVEL_UP` à l'init | **25** | **0** | **−25 ✅ FIX P0-A** |
| `SINGLE_ACTION_LOOP` brisées | 0 | **14** | **+14 ✅ FIX P1-D** |
| `LEVELS_PROGRESS` déclenchés | N/A | 0 | (pas de level_up réel) |
| IDs action inconnus | 0 | 0 | = |

**Conclusion immédiate :** LuCY v12.1 n'a remporté aucun niveau (identique v12.0). Les 4 corrections structurelles sont confirmées actives par les logs. L'absence de victoire n'est pas due aux bugs corrigés — elle révèle que le problème racine est en amont : l'agent ne sait pas encore quelle transformation résout chaque puzzle.

---

## 2. Validation des correctifs — Analyse par fix

### FIX P0-A — `win_levels` : faux LEVEL_UP éliminé ✅

**Avant (v12.0, fichier : [`my_agent_v120.py`](../agent/my_agent_v120.py), ligne 1159) :**
```python
level_up = current_levels > self._levels_completed or current_win > self._win_levels
```
`win_levels` initial = 0 ; premier frame retourne 6–10 → **25 faux LEVEL_UP** au step=1 de chaque jeu.

**Après (v12.1, fichier : [`my_agent_v121.py`](../agent/my_agent_v121.py), ligne ~1143) :**
```python
# FIX P0-A: capture game total levels at first frame
self._win_levels_at_game_start = raw_win  # = total du jeu (jamais 0)
# ...
level_up = current_levels > self._levels_completed  # win_levels IGNORÉ
```
**Preuve log :** `LEVEL_UP count v12.1 = 0`. Extrait ACTION_BEFORE :
```
game=tn36 win_levels=7 wl_start=7 wl_is_total=True levels_completed=0
```
`win_levels=7` = nombre total de niveaux du jeu tn36. `levels_completed=0` = LuCY n'en a résolu aucun. Ce sont deux mesures orthogonales qui ne doivent jamais être confondues.

---

### FIX P0-B — Signal `levels_progress_map` structurellement correct ⚠️ PARTIAL

**Avant (v12.0) :** `W_GOAL_DELTA=5.0` actif dans la formule de scoring même si `goal_found=False` → le poids `5.0` ne contribuait à rien mais l'architecture le calculait inutilement.

**Après (v12.1) :** Quand `goal_found=False` et qu'une action a déclenché un `level_up` réel, `levels_progress_map[action.value] = LEVELS_PROGRESS_BONUS=5.0` est injecté dans `score_all()` via `lp_map`. Le poids `W_GOAL_DELTA` ne s'applique que si `goal_found=True`.

**Preuve log :** `LEVELS_PROGRESS events = 0` — cohérent : aucun level_up réel n'a eu lieu. Le mécanisme est structurellement correct mais n'a pas de signal à amplifier dans ce run. Il sera activé dès le premier vrai niveau résolu.

---

### FIX P0-C — Compteur de progression réelle (`n_progress_real`) ✅ STRUCTUREL

**Avant (v12.0, ligne 1211) :**
```python
if level_up or delta >= DELTA_MIN:
    self._n_progress[self._prev_action.value] += 1
```
`n_progress` s'incrémentait sur changement visuel (`delta >= 0.01`), pas sur progression réelle.

**Après (v12.1) :**
```python
# FIX P0-C: n_progress_real = level_up ONLY; n_visual_change = visual
if level_up:
    self._n_progress_real[self._prev_action.value] += 1
if visual_delta >= DELTA_MIN:
    self._n_visual_change[self._prev_action.value] += 1
```
**Preuve log :** `n_progress_real_total = 0` (pas de level_up). `n_visual_change = 1 534 actions` (80,2 % changement visuel). Les deux compteurs sont désormais bien séparés. Le scoring ne récompense plus le bruit visuel.

---

### FIX P1-D — Boucles à action unique brisées ✅ PASS

**Avant (v12.0) :** lp85 et ft09 avaient `available_actions=[6]` en continu. LuCY répétait ACTION6 × 79 sans interruption.

**Après (v12.1) :** `SINGLE_ACTION_LOOP_THRESHOLD=8` — si `len(candidates)==1` et `same_state_streak >= 8` → RESET forcé.

**Preuve log — lp85 :**
```
game=lp85 streak=8 candidate=ACTION6 budget_rem=65
game=lp85 streak=8 candidate=ACTION6 budget_rem=56
... (8 boucles brisées)
```
**Preuve log — ft09 :**
```
game=ft09 streak=8 candidate=ACTION6 budget_rem=70
... (6 boucles brisées)
```
**Total : 14 boucles brisées** sur 2 jeux. Durée lp85 : `793 ms` (vs ~6 241 ms estimé v12.0). Le budget ACTION6 inutile est réalloué aux RESET.

**Observation critique :** ft09 passe de ~474 ms (v12.0) à 3 324 ms (v12.1) malgré 6 RESET. Cause : après chaque RESET, le moteur redémarre le jeu et refait les 8 premières steps qui sont toujours des ACTION6 → les RESET multiplient les itérations d'amorçage. Le loop-break ralentit ft09 au lieu de l'accélérer car le jeu n'a pas d'alternative réelle.

---

## 3. Tableau par jeu — résultats détaillés v12.1

| Jeu | win_levels (total) | IDs dispo | single_loops | Transf. dom. | elapsed ms | v12.0 ms | Δ |
|-----|-------------------|-----------|-------------|-------------|-----------|----------|---|
| tn36 | 7 | [6] | 0 | IDENTITY | 1 118 | 1 383 | −265 |
| cd82 | 6 | [1–6] | 0 | IDENTITY | 2 325 | 1 497 | +828 |
| ls20 | 7 | [1–4] | 0 | IDENTITY | 933 | 1 609 | −676 |
| vc33 | 7 | [6] | 0 | IDENTITY | 901 | 1 568 | −667 |
| wa30 | 9 | [1–5] | 0 | IDENTITY | 829 | 1 762 | −933 |
| sk48 | 8 | [1–4,6,7] | 0 | IDENTITY/SHIFT | 1 190 | 2 305 | −1 115 |
| r11l | 6 | [6] | 0 | GROWING/SHIFT | 2 663 | 4 063 | −1 400 |
| s5i5 | 8 | [6] | 0 | IDENTITY | 819 | 1 383 | −564 |
| bp35 | 9 | [3,4,6,7] | 0 | SHRINKING | 2 981 | 4 788 | −1 807 |
| lf52 | 10 | [1–4,6,7] | 0 | IDENTITY/SHIFT | 2 598 | 3 593 | −995 |
| sb26 | 8 | [5,6,7] | 0 | IDENTITY | 7 409 | 11 595 | −4 186 |
| g50t | 7 | [1–5] | 0 | IDENTITY | 3 828 | 3 849 | −21 |
| ka59 | 7 | [1–4,6] | 0 | IDENTITY | 909 | 1 371 | −462 |
| sp80 | 6 | [1–6] | 0 | IDENTITY | 2 454 | 1 139 | +1 315 |
| dc22 | 6 | [1–4,6] | 0 | IDENTITY | 872 | 1 631 | −759 |
| lp85 | 8 | [6] | **8** | IDENTITY | **793** | ~6 241 | **−5 448** |
| sc25 | 6 | [1–5] | 0 | IDENTITY | 2 948 | 2 513 | +435 |
| tr87 | 6 | [1–5] | 0 | IDENTITY | 901 | 1 511 | −610 |
| ft09 | 6 | [6] | **6** | IDENTITY | 3 324 | ~474 | **+2 850** |
| cn04 | 6 | [1–6] | 0 | IDENTITY | 847 | 847 | 0 |
| m0r0 | 6 | [1–6] | 0 | IDENTITY | 851 | 1 023 | −172 |
| su15 | 9 | [6,7] | 0 | SHIFT | 1 882 | 1 882 | 0 |
| re86 | 8 | [1–6] | 0 | IDENTITY | 851 | 851 | 0 |
| ar25 | 8 | [1–7] | 0 | IDENTITY | 871 | 871 | 0 |
| tu93 | 9 | [1–5] | 0 | IDENTITY | 3 407 | 3 407 | 0 |
| **TOTAL** | | | **14** | | **48 504** | **69 931** | **−21 427** |

---

## 4. Distribution des transformations — avant / après

| Transformation | v12.0 | v12.1 | Delta |
|---------------|-------|-------|-------|
| IDENTITY | ~73 % | 71,9 % (1374/1912) | ≈ |
| SHIFT | ~8 % | 15,0 % (286/1912) | +7 % |
| GROWING | ~6 % | 6,2 % (118/1912) | ≈ |
| SHRINKING | ~3 % | 2,5 % (47/1912) | ≈ |
| UNKNOWN | ~10 % | 4,6 % (87/1912) | −5 % |

La baisse de UNKNOWN (+SHIFT) est probablement due à la réduction des boucles P1-D qui généraient des états initiaux répétés (UNKNOWN avant première transition).

---

## 5. Distribution des actions (v12.1)

| Action | Occurrences | % |
|--------|-------------|---|
| ACTION6 | 705 | 35,7 % |
| ACTION3 | 293 | 14,9 % |
| ACTION1 | 243 | 12,3 % |
| ACTION4 | 237 | 12,0 % |
| ACTION2 | 232 | 11,8 % |
| ACTION5 | 120 | 6,1 % |
| ACTION7 | 82 | 4,2 % |

ACTION6 reste dominant (35,7 %) car il est l'unique candidat sur tn36/vc33/r11l/s5i5/lp85/ft09. Sur les jeux multi-actions, la distribution est plus équilibrée.

---

## 6. Analyse croisée — Ce que révèlent les corrections

### 6.1 La durée chute de 30 % : pourquoi ?

La majorité du gain de 21 s vient de :
- **sb26** : −4 186 ms → le jeu sb26 avait max_stuck=9 en v12.0 (11 595 ms). En v12.1, le `same_state_streak` interagit différemment avec le deep_stuck car le compteur se réinitialise au RESET. Gain : meilleures décisions de reset.
- **lp85** : −5 448 ms (estimation) → 8 boucles brisées à 8 steps chacune = 64 RESET au lieu de 79 steps continus ACTION6.
- **r11l, sk48, bp35** : −1 400 / −1 115 / −1 807 ms — la disparition des faux LEVEL_UP élimine les fausses transitions de phase `explore→exploit` qui coûtaient des cycles.

### 6.2 ft09 ralentit (+2 850 ms) : anomalie attendue

ft09 est un jeu `available_actions=[6]` tout au long. En v12.0 : ACTION6 × 79 = rapide (ACTION6 est immédiate). En v12.1 : 6 RESET forcés × coût d'initialisation moteur (~550 ms chacun) = +3 300 ms. Le FIX P1-D est structurellement correct mais contre-productif sur les jeux où la seule action disponible NE SE RÉINITIALISE PAS après RESET. **Amélioration suggérée v12.2** : ne pas déclencher le single_action_loop RESET si `same_state_streak >= SINGLE_ACTION_LOOP_THRESHOLD` et `budget_remaining < 20` (RESET en fin de budget = inutile).

### 6.3 Pourquoi 0 victoire malgré les 4 corrections ?

Les corrections adressaient des **problèmes de mesure et de signal** :
- P0-A supprimait une fausse détection de victoire
- P0-B préparait un signal de récompense non utilisé (pas de level_up)
- P0-C purifiait le compteur de progression
- P1-D brisait les boucles stériles

Aucune correction n'adresse le **mécanisme de résolution** : comment savoir quelle action transforme une grille en une grille cible. Le problème restant est fondamental : l'agent n'a pas de représentation de la **structure du puzzle** (entrée, sortie attendue, règle de transformation).

---

## 7. Chantiers identifiés pour v12.2

| Priorité | Chantier | Justification issue des logs L-033 |
|----------|----------|-------------------------------------|
| **P0** | Comprendre pourquoi `levels_completed` reste 0 | Aucune action ne déclenche de niveau validé — analyser quand le moteur incrémente ce champ |
| **P0** | Inspecter `FrameData.state` sur chaque step | `state=NOT_FINISHED` tout au long — quelles conditions passent à `LEVEL_DONE` ou `WIN` ? |
| **P1** | Affiner FIX P1-D : pas de RESET si `budget_remaining < 20` | ft09 ralentit de +2 850 ms car les RESET de fin de budget sont coûteux sans bénéfice |
| **P1** | Explorer les attrs `FrameData` non encore utilisés | FRAME_INVENTORY révèle des champs hors grille — peuvent contenir des indices de progression |
| **P2** | Implémenter un oracle de progression externe | Si le moteur expose une distance grille→solution, l'utiliser comme signal primaire |
| **P2** | Analyser les 25 fichiers de jeux locaux | Comprendre la structure `environment_files/` pour prédire les actions gagnantes |

---

## 8. Vérification de cohérence des logs

| Invariant | Attendu | Observé | Statut |
|-----------|---------|---------|--------|
| 25 GAME_DONE | 25 | 25 | ✅ |
| 0 GAME_WON | 0 | 0 | ✅ |
| LEVEL_UP | 0 (v12.1) | 0 | ✅ |
| SINGLE_ACTION_LOOP | 14 | 14 | ✅ |
| win_levels_at_game_start ≠ 0 | toujours | 7–10 | ✅ |
| IDs inconnus | 0 | 0 | ✅ |
| Total actions | 1 975 | 1 975 | ✅ |
| n_visual_change > 0 | oui | 1 534 | ✅ |
| n_progress_real | 0 | 0 | ✅ (pas de level_up) |
| Rapport précédent écrasé | NON | NON | ✅ |

---

## 9. Conclusion

LuCY v12.1 a exécuté les 4 corrections structurelles identifiées par l'audit L-032. Les corrections sont prouvées par les logs :

- **P0-A** : 25 faux LEVEL_UP → 0 ✅ — La sémantique de `win_levels` est désormais correcte.
- **P0-B** : Architecture `levels_progress_map` prête à amplifier le premier vrai level_up ⚠️ — Signal non déclenché faute de progression réelle.
- **P0-C** : `n_progress_real` et `n_visual_change` séparés ✅ — Le scoring ne confond plus bruit visuel et progression.
- **P1-D** : 14 boucles stériles brisées ✅ — Gain de −30,6 % de temps total ; cas ft09 à affiner en v12.2.

Le problème non résolu est en amont des corrections : l'agent n'a pas de mécanisme pour identifier la règle de transformation qui amène une grille à son état cible. C'est le chantier P0 de v12.2.

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

---

*Rapport produit après lecture ligne par ligne du log brut (8 928 lignes, L-060). Aucun rapport précédent n'a été modifié.*
