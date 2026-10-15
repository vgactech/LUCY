# L-038 — Audit critique Tier 1 : sk48 / tr87 / sb26
## Analyse des runs à 200 actions + réponse à l'audit C-003/C-004

**Date :** 2026-10-16  
**Rapport précédent :** L-037  
**Espace de numérotation :** LuCY (L-001→) — distinct de ARTCB (R-xxx) (règle D-091)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Résultats mesurés (logs forensic réels)

Sources : `LuCY/logs/lucy_L038_sk48_20261015T150000Z.log`,
`LuCY/logs/lucy_L038_tr87_20261015T150000Z.log`,
`LuCY/logs/lucy_L038_sb26_20261015T150000Z.log`

| Jeu | Actions consommées | `levels_completed` | Raison d'arrêt | `elapsed_ms` | `n_visual_change` | `n_progress_real` |
|-----|-------------------|-------------------|----------------|-------------|-------------------|-------------------|
| **sk48** | 199/200 | **0** | `BUDGET_EXHAUSTED` | 3 687 ms | `{1:28, 2:20, 3:5, 4:1, 6:1, 7:6}` | `{}` |
| **tr87** | 199/200 | **0** | `BUDGET_EXHAUSTED` | 2 616 ms | `{4:2}` | `{}` |
| **sb26** | 199/200 | **0** | `BUDGET_EXHAUSTED` | 27 087 ms | `{5:1}` | `{}` |

**Constat absolu** : `n_progress_real={}` sur les 3 jeux. Aucune progression réelle mesurée.  
`goal_found=False` sur les 3 jeux. `real_level_ups=0` sur les 3 jeux.

---

## 2. Réponse à l'audit C-003 — Budget d'actions

### Verdict confirmé : modification utile, efficacité non démontrée

L'audit utilisateur (section 2, C-003) était correct : augmenter le budget de 80 à 200 permet
d'explorer plus longtemps, mais **ne corrige pas une stratégie incapable de discriminer
les actions utiles des inutiles**.

**Preuve mesurée dans les logs** :

**sk48** — `n_visual_change={1:28, 2:20, 3:5, 7:6, 6:1, 4:1}` montre qu'ACTION1 a provoqué
28 changements visuels, soit le signal le plus fort. Or à action 190+ (log ligne seq=670),
LuCY est toujours en phase `exploit` avec ACTION6 répété plusieurs fois de suite avec
`visual_delta=0.0` (aucun changement). L'agent a bien identifié que ACTION1 produit
des changements (transform_type GROWING), mais n'a **jamais** déclenché la condition de
victoire (`lgdrixfno >= 35` via `gvtmoopqwy()`). Raison : LuCY n'enchaîne pas les
actions dans la séquence requise (sélection sprite → navigation → vérification d'alignement).

**tr87** — `n_visual_change={4:2}` : seules 2 actions sur 199 ont produit un changement
visible significatif (≥ DELTA_MIN=0.01). LuCY alterne ACTION1/2/3/4 sans comprendre
que ACTION3/4 déplacent le curseur et que ACTION1/2 modifient la couleur de la
tuile *actuellement sélectionnée*. La quasi-totalité des actions produisent des deltas
sub-pixel inférieurs au seuil de détection.

**sb26** — `n_visual_change={5:1}` : une seule action a produit un changement visible
sur 199 actions. Avec `elapsed_ms=27 087 ms` (27 s pour 199 actions = 136 ms/action),
sb26 déclenche des animations longues. LuCY envoie des actions pendant les animations
(qui n'ont aucun effet), ne sachant pas qu'elle doit attendre la fin de l'animation
avant d'agir.

**Conclusion C-003** : 500 actions (comme proposé en L-036) permettraient probablement
de résoudre sk48 *uniquement si* LuCY découvre la bonne séquence par hasard, ce qui reste
improbable avec une architecture d'exploration purement visuelle sans modèle séquentiel.

---

## 3. Réponse à l'audit C-004 — Diagnostic de r11l

### Verdict : diagnostic incomplet confirmé par les données Tier 1

L'estimation « 400 actions » pour r11l n'était pas fondée sur la condition de victoire
réelle mais sur une extrapolation linéaire (+3 pixels/action). Les données Tier 1
confirment que cette approche est insuffisante :

- tr87 : 2 changements visuels sur 199 actions → l'extrapolation linéaire donnerait
  **0 actions utiles sur 500**, soit un budget inutile
- sb26 : 1 changement visuel sur 199 actions → même problème

**La question critique n'est pas le nombre d'actions mais la compréhension du mécanisme**.

---

## 4. État des 5 lacunes (T-01 → T-05)

| Lacune | Statut | Données mesurées |
|--------|--------|-----------------|
| **T-01 — Condition de victoire** | ⚠️ PARTIELLEMENT ADRESSÉ | sk48 : `lgdrixfno >= 35` via `gvtmoopqwy()` identifiée. tr87 : `bsqsshqpox()` identifiée. sb26 : `pmygakdvy == len(wcfyiodrx) - 1 and wrudcanmwy` identifiée. LuCY ne détecte pas ces signaux. |
| **T-02 — Budget d'actions** | ⚠️ PARTIELLEMENT ADRESSÉ | 200 actions OK pour sk48 (si séquence correcte) ; insuffisant pour tr87/sb26 sans compréhension mécanique |
| **T-03 — Définition d'arcade** | ❌ OUVERT | Les 3 jeux nécessitent des séquences conditionnelles — pas classifiés comme tels |
| **T-04 — Jeux à une seule action** | ❌ OUVERT | tr87 `n_visual_change={4:2}` prouve que seule ACTION4 a eu un effet; LuCY n'en tire pas de stratégie |
| **T-05 — Copies de l'agent** | ✅ FERMÉ | `VERSION="12.1"` confirmé dans les 3 logs forensic. Fichier actif : `vendor/.../agent/my_agent.py` |

---

## 5. Diagnostic architectural fondamental (confirmation)

Les 3 jeux Tier 1 partagent le **même défaut structurel** vis-à-vis de l'architecture v12.1 :

### Défaut A — Absence de modèle séquentiel

Le `_CognitiveEngine` score chaque action **indépendamment** via `visual_delta`.  
Preuve log sk48 : `COGNITIVE_SCORE top3={ACTION4:1.7, ACTION6:1.7, ACTION7:1.7}`  
→ 3 actions ex-aequo, scores identiques → pas de discrimination.  
Le `_RuleMemory` (`PS_HYPOTHESIS`, `PS_FOLLOW` dans les logs) stocke des règles  
`(action → transform_type)` mais **pas de séquences** (A → B si état=X).

### Défaut B — Absence de détection de phase d'animation

sb26 : `elapsed_ms=27 087ms` pour 199 actions = **136ms/action en moyenne**.  
Les actions ARC-AGI-3 prennent normalement <10ms.  
→ Le jeu est bloqué dans des animations longues.  
LuCY envoie des actions pendant l'animation sans mécanisme d'attente.

### Défaut C — `_GoalDeltaTracker` inopérant

`goal_found=False` sur les 3 jeux.  
`_GOAL_ATTRS` ne correspond à aucun attribut présent dans sk48/tr87/sb26.  
Le moteur de guidage le plus sophistiqué de v12.1 est **silencieux** sur tous les Tier 1.

### Défaut D — Phase EXPLOIT sans signal réel

Après l'exploration initiale (actions 1-6), LuCY passe immédiatement en phase `exploit`
(visible dès action 7 sur sk48) mais avec **0 signal de progression réelle**.
La phase EXPLOIT répète les actions à plus haut `visual_delta` historique,
créant une boucle visuelle sans progression vers la victoire.

---

## 6. Avant / Après — État des métriques clés

### sk48

| Métrique | Valeur L-033 (v12.0, 80 actions) | Valeur L-038 (v12.1, 200 actions) |
|----------|--------------------------------|----------------------------------|
| Actions consommées | 79/80 | 199/200 |
| `levels_completed` | 0 | **0** (inchangé) |
| `n_progress_real` | `{}` | **`{}`** (inchangé) |
| `n_visual_change ACTION1` | Non mesuré séparément | **28** |
| `goal_found` | False | **False** (inchangé) |
| Phase dominante | explore → exploit | **exploit** (dès action 7) |

### tr87

| Métrique | L-038 (v12.1, 200 actions) | Observation |
|----------|--------------------------|-------------|
| `n_visual_change` total | 2 (uniquement ACTION4) | **Critique** : 197 actions sans effet visible |
| Phases d'animation détectées | 0 | Mécanisme curseur non compris |
| `stuck_streak` max observé | Variable mais < 8 | FIX P1-D ne se déclenche pas |

### sb26

| Métrique | L-038 (v12.1, 200 actions) | Observation |
|----------|--------------------------|-------------|
| `elapsed_ms` | **27 087 ms** | 14× plus lent que sk48 |
| `n_visual_change` total | 1 (uniquement ACTION5) | **Critique** : 1 action utile sur 199 |
| Temps moyen/action | 136 ms | Animation en cours pendant les actions |

---

## 7. Réponse à la décision architecturale (section 5 de l'audit)

L'audit affirme : *"une autonomie utile nécessite des mécanismes internes de contrôle :
détection de blocage, vérification des résultats, gestion des ressources et capacité à
revenir sur une stratégie inefficace."*

**État actuel de v12.1** :
- Détection de blocage : `stuck_streak` + `FIX_P1D_SINGLE_ACTION_LOOP` ✅ présents mais
  seuil trop élevé (8 tours) pour les jeux à peu d'actions visibles
- Vérification des résultats : `n_progress_real` mesure les `level_up` réels ✅
  mais ne mesure pas la progression interne au niveau
- Gestion des ressources : budget respecté ✅
- Capacité à revenir : RECOVER phase ✅ mais déclenche un `RESET` (retour début)
  plutôt qu'une stratégie alternative

**Lacune principale** : absence de **détection d'animation en cours** et de modèle
de **causalité séquentielle** (action A doit précéder action B pour que B ait un effet).

---

## 8. Priorités recommandées pour C-006+

### P0 — Immédiat

1. **C-006 : Détection d'animation en cours** (sb26)  
   Si `elapsed_ms / n_actions > 50ms`, déduire qu'une animation est en cours.  
   Attendre que le frame soit stable avant d'agir.  
   Fichier cible : `my_agent.py`, méthode `_select_action()` ou `__call__()`.

2. **C-007 : Budget adaptatif par signal** (tr87)  
   Si `n_visual_change` total < 5 après 20 actions, activer un mode de sondage
   systématique : essayer chaque action isolément et mesurer l'effet précis.

### P1 — Court terme

3. **C-008 : Modèle de séquences** (sk48)  
   Stocker des paires `(état_avant, action_A, état_après, action_B)` dans `_RuleMemory`.
   Détecter les séquences nécessaires à la victoire via la condition de victoire.

4. **C-009 : Inspection des conditions de victoire**  
   Lire les attributs `win_condition_*` dans chaque `GameState` si exposés.
   Construire un contrat par jeu : état initial, actions autorisées, condition de fin.

### P1 — Validation

5. **Tester r11l avec 500 actions** (recommandation de l'audit)  
   Sans C-006/C-007/C-008, le résultat probable est identique : `BUDGET_EXHAUSTED, levels=0`.
   Ce test vaut la peine *après* C-006/C-007 pour mesurer l'amélioration.

---

## 9. Résumé des lacunes ouvertes

| ID | Lacune | Statut |
|----|--------|--------|
| T-01 | Condition de victoire | ⚠️ Identifiée en code, non détectée par LuCY |
| T-02 | Budget d'actions | ⚠️ 200 insuffisant sans séquences |
| T-03 | Définition d'arcade | ❌ Classification séquentielle manquante |
| T-04 | Jeux à une seule action utile | ❌ tr87 prouve le problème (2/199 actions utiles) |
| T-05 | Copies de l'agent | ✅ FERMÉ — VERSION 12.1 confirmée × 3 logs |

---

## 10. Fichiers sources

| Fichier | Rôle |
|---------|------|
| `LuCY/logs/lucy_L038_sk48_20261015T150000Z.log` | Run sk48 — 199 actions, 3687ms, BUDGET_EXHAUSTED |
| `LuCY/logs/lucy_L038_tr87_20261015T150000Z.log` | Run tr87 — 199 actions, 2616ms, BUDGET_EXHAUSTED |
| `LuCY/logs/lucy_L038_sb26_20261015T150000Z.log` | Run sb26 — 199 actions, 27087ms, BUDGET_EXHAUSTED |
| `LuCY/vendor/.../agent/my_agent.py` | Agent actif VERSION="12.1" |
| `LuCY/rapports/L-037_strategie_curriculum_conditions_victoire_c005_2026-10-15.md` | Rapport précédent (Q1-Q3) |

---

**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**  
**Rapport suivant recommandé : L-039** — résultats après implémentation C-006 (détection animation)
