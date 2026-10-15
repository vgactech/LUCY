# L-034 — Stratégie de curriculum d'apprentissage par arcade
## Du niveau le plus facile au plus difficile — Analyse croisée L-032 / L-033

**Date :** 2026-10-15  
**Version LuCY :** 12.1 (commit `e051b59`)  
**Sources :** `logs/lucy_L032_20261015T095357Z.json` + `logs/lucy_L033_20261015T083115Z.json` + `logs/lucy_L033_run_20261015T083115Z.log` + `agent/my_agent_v121.py` (lignes 1–1300 lues intégralement)  
**Rapport précédent :** L-033 | **Espace :** LuCY (L-001→L-034+)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Synthèse exécutive

**25 jeux joués, 0 victoire, 0 niveau terminé.** Cette situation ne s'explique pas par un manque de budget (79 actions consommées par jeu), mais par un défaut structurel fondamental : **LuCY optimise le changement visuel au lieu d'optimiser la progression vers la victoire**. Le curriculum proposé ici vise à corriger ce défaut de la base, en commençant par les jeux offrant le moins d'ambiguïté possible sur la condition de victoire.

Le raisonnement de l'utilisateur — *apprendre les premiers niveaux de chaque arcade avant de passer aux suivants, du plus facile au plus difficile* — est **architecturalement correct**. Mais il est actuellement inapplicable : la condition de victoire de chaque arcade n'est pas encore connue de LuCY (ni mesurable depuis les logs). Le curriculum commence donc par un prérequis absolu.

---

## 2. Ce que les logs démontrent réellement (analyse forensique brute)

### 2.1 Cas concret : `tn36` — action unique, boucle pure

Extrait du log L-033 (lignes 17–56) :
```
ACTION_BEFORE | action_count=1 | candidates=["ACTION6"] | raw_available_ids=[6]
ACTION_AFTER  | action_count=1 | transform_type=UNKNOWN | pixel_diff.comparable=false
ACTION_BEFORE | action_count=2 | candidates=["ACTION6"]
ACTION_AFTER  | action_count=2 | transform_type=IDENTITY | changed_pixels=0
...
COGNITIVE_SCORE | action_count=10 | top3={"ACTION6":0.75}  ← seul candidat, score figé
...
79 fois ACTION6 | 0 level_up | 0 real_progress | reason=BUDGET_EXHAUSTED
```

**Observation directe :** LuCY ne peut jouer qu'`ACTION6` sur ce jeu. Elle joue 79 fois la même action. Le `_GoalDeltaTracker` retourne `goal_found=false` depuis la première frame. Le score cognitif `ACTION6=0.75` reste figé car il n'y a pas d'alternative. Il n'y a aucun signal de progression.

**Conclusion forensique `tn36` :** LuCY ne sait pas si `ACTION6` est la bonne action ou si elle est même utile. Elle la joue parce que c'est la seule disponible. Sans signal de victoire ou de progression, le budget est épuisé mécaniquement.

### 2.2 Cas concret : `sk48` — 6 actions disponibles, transformations GROWING/SHRINKING observées

Extrait du log L-033 (lignes 2000–2100) :
```
action_count=54 | ACTION1 → SHRINKING | changed_pixels=138 | changed_frac=0.033691
action_count=59 | ACTION2 → GROWING   | changed_pixels=139 | changed_frac=0.033936
action_count=62 | RESET: per_level_budget
action_count=63 | explore → ACTION1 → UNKNOWN
ps_rules=57 (hypothèses accumulées) | goal_found=False | lp_map_active=False
```

**Observation directe :** `sk48` dispose de 6 actions et produit des transformations réelles (GROWING, SHRINKING). Le moteur de synthèse accumule 57 hypothèses, puis 65, puis 70. LuCY *apprend* des règles de transformation, mais ces règles ne sont jamais reliées à une condition de victoire. Les `PS_FOLLOW` avec `confidence>2.0` montrent que LuCY a appris quelle action produit quoi, mais pas si ce "quoi" est la solution.

**Conclusion forensique `sk48` :** Jeu plus riche en information que `tn36`, mais toujours bloqué au même problème : absence totale de signal de victoire.

### 2.3 Problème racine confirmé dans le code

Dans [`agent/my_agent_v121.py`](../agent/my_agent_v121.py:961) :

```python
# NOTE v12.1: goal_found=False on all 25 ARC-AGI-3 local games (confirmed L-032).
# Kept for future compatibility; FIX P0-B provides alternative signal via
# levels_progress_map when goal_found=False.
```

**Le `_GoalDeltaTracker` recherche 9 attributs** (`goal`, `target`, `answer`, `output_grid`, `expected_output`, `puzzle_output`, `solution`, `goal_frame`, `target_frame`) **et échoue sur les 25 jeux**. Il n'y a donc aucun signal "je me rapproche de la solution". Le fallback `levels_progress_map` (FIX P0-B) ne s'active jamais non plus car `n_progress_real=0` sur tous les jeux.

**LuCY navigue à l'aveugle sur les 25 jeux.**

---

## 3. Classification des jeux : du plus facile au plus difficile

### Critères de classification utilisés (issus des logs réels)

| Critère | Indicateur log | Poids |
|---------|---------------|-------|
| Nombre d'actions disponibles | `raw_available_ids` | Fort — moins d'actions = moins d'ambiguïté |
| Type de transformation dominant | `transform_type` dans `ACTION_AFTER` | Fort — IDENTITY = muet, SHIFT/GROWING = signal |
| Diversité des transformations observées | distribution `IDENTITY/SHIFT/GROWING/SHRINKING` | Moyen |
| Boucles détectées | `SINGLE_ACTION_LOOP` dans L-033 | Moyen — boucle = mécanisme détectable |
| Coût de calcul (ms) | `elapsed_ms` L-033 | Faible — indicateur de complexité interne |
| `max_stuck` (dépassements seuil=5) | donnée L-032 | Moyen |

**Note importante :** cette classification mesure la *facilité à obtenir un signal utile*, PAS la facilité à gagner. Un jeu avec une seule action peut être très difficile à résoudre même s'il est simple à explorer.

### Tableau de classification (25 jeux classés)

| Rang | Jeu | Actions | Transform dominant | Boucles | ms L-033 | Stuck | Difficulté signal |
|------|-----|---------|-------------------|---------|----------|-------|------------------|
| **1** | **s5i5** | 1 ([6]) | IDENTITY:74 | 0 | 819 | 0 | TRÈS FAIBLE |
| **2** | **vc33** | 1 ([6]) | IDENTITY:74 | 0 | 901 | 0 | TRÈS FAIBLE |
| **3** | **tn36** | 1 ([6]) | IDENTITY:72 | 0 | 1118 | 0 | TRÈS FAIBLE |
| **4** | **lp85** | 1 ([6]) | IDENTITY:66 | **8** | 793 | 9 | FAIBLE (boucle détectable) |
| **5** | **r11l** | 1 ([6]) | **GROWING:72** | 0 | 2663 | 0 | FAIBLE (signal GROWING pur) |
| **6** | **ft09** | 1 ([6]) | IDENTITY:47, SHIFT:25 | **6** | 3324 | 9 | FAIBLE/MOYEN |
| **7** | **tr87** | 4 ([1–4]) | IDENTITY:74 | 0 | 901 | 0 | MOYEN |
| **8** | **re86** | 5 ([1–5]) | IDENTITY:74 | 0 | 851 | 1 | MOYEN |
| **9** | **ka59** | 5 ([1,2,3,4,6]) | IDENTITY:74 | 0 | 909 | 1 | MOYEN |
| **10** | **wa30** | 5 ([1–5]) | IDENTITY:74 | 0 | 829 | 2 | MOYEN |
| **11** | **dc22** | 5 ([1,2,3,4,6]) | IDENTITY:71, GROWING:3 | 0 | 872 | 1 | MOYEN |
| **12** | **m0r0** | 6 ([1–6]) | IDENTITY:71, SHRINKING:3 | 0 | 851 | 1 | MOYEN |
| **13** | **cn04** | 6 ([1–6]) | IDENTITY:74 | 0 | 847 | 1 | MOYEN |
| **14** | **sp80** | 6 ([1–6]) | IDENTITY:74 | 0 | 2454 | 0 | MOYEN |
| **15** | **cd82** | 6 ([1–6]) | IDENTITY:72 | 0 | 2325 | 1 | MOYEN |
| **16** | **ls20** | 4 ([1–4]) | IDENTITY:70 | 0 | 933 | 2 | MOYEN |
| **17** | **ar25** | 7 ([1–7]) | IDENTITY:74 | 0 | 871 | **9** | MOYEN/ÉLEVÉ |
| **18** | **su15** | 2 ([6,7]) | **SHIFT:54** | 0 | 1882 | 2 | ÉLEVÉ (SHIFT dominant) |
| **19** | **bp35** | 4 ([3,4,6,7]) | SHRINKING:32, GROWING:24 | 0 | 2981 | 0 | ÉLEVÉ |
| **20** | **lf52** | 6 ([1,2,3,4,6,7]) | IDENTITY:59, SHIFT:12 | 0 | 2598 | 0 | ÉLEVÉ |
| **21** | **sk48** | 6 ([1,2,3,4,6,7]) | IDENTITY:55, GROWING:10, SHRINKING:9 | 0 | 1190 | 6 | ÉLEVÉ |
| **22** | **g50t** | 5 ([1–5]) | IDENTITY:42, SHIFT:28 | 0 | 3828 | 1 | ÉLEVÉ |
| **23** | **sc25** | 5 ([1,2,3,4,6]) | IDENTITY:41, SHIFT:33 | 0 | 2948 | 0 | ÉLEVÉ |
| **24** | **tu93** | 4 ([1–4]) | IDENTITY:37, SHIFT:37 | 0 | 3407 | 0 | TRÈS ÉLEVÉ |
| **25** | **sb26** | 3 ([5,6,7]) | IDENTITY:41, SHIFT:31 | 0 | **7409** | **9** | TRÈS ÉLEVÉ |

---

## 4. Stratégie de curriculum : 4 paliers opérationnels

### Palier 0 — Prérequis absolu (AVANT tout curriculum)
**Rendre la victoire mesurable.**

Sans ce palier, aucun curriculum ne peut fonctionner. LuCY ne sait pas ce que signifie gagner.

**Actions requises :**
1. **Identifier la condition de victoire de chaque jeu.** Pour chaque arcade, déterminer : quelle transformation de la grille déclenche `GameState.WIN` ? S'appuyer sur les fichiers de jeu dans `environment_files/` (exemple : `environment_files/tn36/ef4dde99/tn36.py`). C'est un **travail d'analyse de code humain**, pas automatisable par LuCY seule.
2. **Exposer l'état cible à LuCY.** Le `_GoalDeltaTracker` cherche des attributs `goal`, `target`, etc. Si l'API des jeux ne les expose pas, il faut soit étendre les attributs cherchés, soit injecter l'état cible autrement.
3. **Définir un signal de progression minimal par jeu.** Une métrique qui monte quand LuCY se rapproche de la solution, même approximativement.

**Critère de passage au Palier 1 :** `goal_found=True` sur au moins 5 jeux, avec `goal_delta_improvement > 0.0` mesurable.

---

### Palier 1 — Premiers niveaux, jeux Groupe A (action unique)
**Jeux concernés :** `s5i5`, `vc33`, `tn36`, `lp85`, `r11l`, `ft09`

Ces 6 jeux n'ont qu'une seule action disponible ([6]). Le curriculum y est trivial en termes d'exploration (pas de choix). Ils sont néanmoins les **prérequis logiques** pour une raison précise : ils éliminent la variable "quelle action choisir" et forcent LuCY à se concentrer sur **la relation action → transformation → victoire**.

**Ce que LuCY doit apprendre sur ces jeux :**
- La séquence exacte d'`ACTION6` qui mène à la victoire (nombre de répétitions ? conditions ?)
- Si `ACTION6` est *toujours* la même transformation ou si elle dépend d'un état précédent
- Quelle différence entre `r11l` (GROWING:72 — signal fort) et `tn36` (IDENTITY:72 — signal muet)

**Cas particulier `r11l` :** c'est le seul jeu à action unique avec GROWING dominant (72/79). C'est le **candidat le plus favorable au palier 1** — LuCY voit une transformation réelle à chaque action. Si `goal_found` devient actif ici, `goal_delta` devrait décroître mécaniquement.

**Cas particulier `lp85` :** 8 boucles détectées en v12.1. La détection de boucle (FIX P1-D) fonctionne. LuCY sait qu'elle tourne en rond. L'apprentissage ici est : "tourner en rond → reset → recommencer différemment".

**Critère de passage au Palier 2 :**
- 100% des premiers niveaux de ces 6 jeux validés (= `levels_completed >= 1` sur chaque jeu)
- Pour chaque jeu : la règle "ACTION6 × N = victoire" est mémorisée dans `_RuleMemory` avec `confidence > PS_CONFIDENCE_THRESHOLD`
- Reproductibilité : le premier niveau doit être résolu en < 10 actions sur 3 runs consécutifs

---

### Palier 2 — Premiers niveaux, jeux Groupe B (IDENTITY dominant, actions multiples)
**Jeux concernés :** `tr87`, `re86`, `ka59`, `wa30`, `dc22`, `m0r0`, `cn04`, `sp80`, `cd82`, `ls20`

Ces 10 jeux ont plusieurs actions disponibles mais produisent majoritairement des transformations IDENTITY. C'est le groupe le plus **trompeur** : les actions semblent n'avoir aucun effet, mais l'une d'elles déclenche probablement la progression.

**Ce que LuCY doit apprendre ici :**
- Distinguer "l'action ne fait rien visuellement" de "l'action fait quelque chose d'utile mais invisible"
- Explorer systématiquement TOUTES les actions avant d'épuiser le budget
- Mémoriser quelle action, dans quel état, a déjà produit un résultat (même minime)

**Stratégie recommandée :**
- Phase EXPLORE obligatoire = tester chaque action disponible AU MOINS ONCE avant de passer en EXPLOIT (déjà implémenté dans le code, mais le budget de 30 actions/niveau peut être insuffisant si la solution demande une séquence)
- Enregistrer l'ordre de découverte : si ACTION3 a déclenché une progression sur `dc22`, cette règle doit survivre entre les runs

**Critère de passage au Palier 3 :**
- 100% des premiers niveaux de ces 10 jeux validés
- `_RuleMemory` contient une règle avec `confidence > 1.5` pour au moins une action non-IDENTITY par jeu

---

### Palier 3 — Premiers niveaux, jeux à signal fort (SHIFT/GROWING/SHRINKING)
**Jeux concernés :** `ar25`, `su15`, `bp35`, `lf52`, `sk48`, `g50t`, `sc25`, `tu93`, `sb26`

Ces 9 jeux produisent des transformations significatives. Les patterns sont détectables, mais la séquence gagnante est plus complexe.

**Ce que LuCY doit apprendre ici :**
- `su15` (SHIFT:54) : ACTION6/7 déplace le centre de masse. LuCY doit apprendre la direction et la distance cible.
- `bp35` (SHRINKING:32, GROWING:24) : alternance de croissance et rétrécissement. La solution est probablement une séquence précise.
- `tu93` (IDENTITY:37, SHIFT:37) : équilibre parfait entre deux types. L'action gagnante est celle qui SHIFT dans la bonne direction.
- `sb26` (7409ms, stuck=9) : le jeu le plus coûteux. À traiter en dernier dans ce palier.

**Critère de passage au Palier 4 :**
- 100% des premiers niveaux de ces 9 jeux validés
- Transfert de compétence démontré : une règle apprise sur `su15` (SHIFT) est réutilisée sur `tu93` ou `sc25` sans réapprentissage complet

---

### Palier 4 — Deuxièmes niveaux (APRÈS validation de TOUS les premiers niveaux)
Ne commencer le Palier 4 qu'une fois 25/25 premiers niveaux résolus avec reproductibilité.

---

## 5. Questions ouvertes — trous identifiés

### Q-001 [BLOQUANT] Conditions de victoire par jeu
**Trou :** On ne sait pas ce que chaque jeu attend comme état final pour déclencher `GameState.WIN`.
**Action :** Lire les fichiers source de chaque jeu dans `environment_files/`. Chercher la méthode `check_win()` ou équivalent.
**Impact :** Sans cette information, aucun curriculum n'est vérifiable.

### Q-002 [BLOQUANT] Pourquoi `goal_found=False` sur les 25 jeux ?
**Trou :** Le `_GoalDeltaTracker` cherche 9 attributs dans `FrameData`. Aucun n'existe dans les jeux locaux.
**Questions spécifiques :**
- Quels attributs sont réellement exposés par chaque jeu ? (vérifiable via `FRAME_INVENTORY` dans les logs)
- La condition de victoire est-elle encodée dans la grille elle-même (état final à atteindre) ou dans une variable externe ?
- Si c'est une grille cible : est-elle accessible via un autre attribut non listé dans `_GOAL_ATTRS` ?

### Q-003 [IMPORTANT] Combien d'actions sont nécessaires pour résoudre le niveau 1 de chaque jeu ?
**Trou :** Le budget actuel est 30 actions/niveau, 80 total. Si un premier niveau demande > 30 actions, LuCY ne peut jamais le résoudre.
**Action :** Analyser les fichiers source des jeux pour estimer la longueur minimale de la solution.

### Q-004 [IMPORTANT] La transformation gagnante est-elle déterministe ou stochastique ?
**Trou :** Si le jeu a une part aléatoire, la même séquence ne mène pas toujours à la victoire. La mémoire épisodique de LuCY suppose la déterminisme.
**Indicateur log :** Pour les jeux avec `transform_type=UNKNOWN` sur la première action, vérifier si le même fingerprint + même action produit le même `fp_after`.

### Q-005 [IMPORTANT] Le signal `GROWING` de `r11l` correspond-il à la progression vers la victoire ?
**Trou :** GROWING:72 est très fort, mais GROWING peut signifier "la grille grossit" sans que ça soit la solution.
**Action :** Vérifier dans `environment_files/r11l/` quelle est la transformation gagnante. Si c'est "atteindre une grille de taille N", alors GROWING est directement le bon signal.

### Q-006 [MOYEN] Les budgets actuels (30/niveau, 80/total) sont-ils adaptés ?
**Trou :** Ces valeurs sont des constantes non justifiées par les données des jeux.
**Recommandation :** Augmenter `MAX_ACTIONS_PER_LEVEL` à 50 et `MAX_ACTIONS_TOTAL` à 200 pour les phases d'apprentissage initial. Les contraintes compétitives Kaggle peuvent être réintroduites une fois les premiers niveaux maîtrisés.

### Q-007 [MOYEN] Le `_RuleMemory` mémorise-t-il entre les resets au sein d'un même jeu ?
**Vérification code :** Oui — `_RuleMemory` est initialisé dans `__init__` et survit aux RESTes. Les règles s'accumulent pendant toute la partie. **Mais** : elles ne survivent pas d'un jeu à l'autre (instance détruite à chaque jeu).
**Question de transfert :** Les règles apprises sur `tn36` (ACTION6=IDENTITY) pourraient-elles accélérer l'apprentissage sur `vc33` ou `s5i5` (mêmes caractéristiques) ?

### Q-008 [MOYEN] Quelle est la règle de passage d'un niveau au suivant ?
**Trou :** `levels_completed` s'incrémente, mais le log ne montre jamais ce déclenchement (car 0 level_up sur 25 jeux).
**Action :** Chercher dans les fichiers source : est-ce `GameState.LEVEL_COMPLETE` ? Un état spécifique de la grille ? Un compteur interne ?

### Q-009 [FAIBLE] L'ordre des jeux dans la session affecte-t-il les performances ?
**Observation :** Les 25 jeux sont joués séquentiellement dans un ordre fixe. Une mauvaise performance sur un jeu tôt (ex. `tn36` = épuisement) n'affecte pas les jeux suivants car les instances sont indépendantes.
**Confirmation :** Vérifiée dans le code — chaque jeu crée une nouvelle instance `MyAgent`.

### Q-010 [FAIBLE — À COMBLER] Éléments non précisés par l'utilisateur
L'utilisateur n'a pas précisé :
- Si le curriculum doit respecter l'ordre de présentation Kaggle ou peut choisir un ordre différent
- Si "100% des premiers niveaux" signifie 1 victoire par jeu ou N victoires reproductibles (recommandation : 3 victoires consécutives)
- Si des jeux peuvent être temporairement exclus du curriculum (ex. `sb26` trop coûteux en début d'apprentissage)
- La durée maximale acceptable par run d'entraînement
- Si un LLM externe peut être utilisé pour injecter les conditions de victoire (D-LUCY-001 dit non, mais cela doit être confirmé pour l'analyse des fichiers source)

---

## 6. Avant / Après : état actuel vs état cible du curriculum

### État actuel (baseline L-033)

| Métrique | Valeur |
|----------|--------|
| Jeux joués | 25 |
| Victoires | **0** |
| Niveaux terminés | **0** |
| Actions budget_exhausted | 25/25 |
| `goal_found=True` | 0/25 |
| `real_progress=True` | 0 occurrences |
| Transformations IDENTITY | 1374/1912 (71.9%) |
| Boucles détectées | 14 (lp85×8 + ft09×6) |
| PS hypothèses accumulées | > 500 sur les jeux actifs |

### État cible après Palier 0

| Métrique cible | Valeur attendue |
|----------------|-----------------|
| `goal_found=True` | ≥ 5 jeux |
| `goal_delta_improvement > 0.0` | ≥ 1 par partie concernée |
| Condition de victoire documentée | 25/25 jeux |

### État cible après Palier 1

| Métrique cible | Valeur attendue |
|----------------|-----------------|
| Premiers niveaux résolus (Groupe A) | 6/6 jeux |
| Règle PS confidence > 1.5 | ≥ 4/6 jeux |
| Actions nécessaires niveau 1 `r11l` | < 15 (estimation) |

### État cible après Paliers 1+2+3 (tous premiers niveaux)

| Métrique cible | Valeur attendue |
|----------------|-----------------|
| Premiers niveaux résolus | 25/25 jeux |
| Score Kaggle (niveau 1) | > 0 (actuellement 0) |
| Transfert de règles inter-jeux | ≥ 1 cas documenté |

---

## 7. Corrections techniques prioritaires recommandées (sans GO requis)

Ces corrections ne changent pas l'architecture de LuCY — elles comblent des lacunes directement visibles dans les logs.

### C-001 — Élargir `_GOAL_ATTRS` dans `_GoalDeltaTracker`
**Fichier :** [`agent/my_agent_v121.py`](../agent/my_agent_v121.py:968)  
**Ligne 968 :**
```python
# AVANT
_GOAL_ATTRS = ["goal", "target", "answer", "output_grid", "expected_output",
               "puzzle_output", "solution", "goal_frame", "target_frame"]

# APRÈS — ajouter les attributs ARC-AGI-3 probables
_GOAL_ATTRS = ["goal", "target", "answer", "output_grid", "expected_output",
               "puzzle_output", "solution", "goal_frame", "target_frame",
               "test_output", "expected", "output", "correct_output",
               "win_state", "solved_state", "level_solution"]
```
**Impact attendu :** `goal_found` pourrait devenir `True` sur certains jeux sans autre modification.

### C-002 — Logguer le contenu de `FRAME_INVENTORY` de façon plus lisible
**Observation log :** La ligne `FRAME_INVENTORY` contient tous les attributs de la frame initiale, mais ils sont dans un JSON compact difficile à analyser manuellement. La clé `all_attrs` avec `type` et `repr` est présente mais peu détaillée pour les types complexes.
**Recommandation :** Ajouter un dump de `dir(latest_frame)` filtré (sans `_`) dans le log GAME_INIT pour identifier les attributs disponibles non listés dans `_GOAL_ATTRS`.

### C-003 — Augmenter les budgets pour la phase d'apprentissage
**Fichier :** [`agent/my_agent_v121.py`](../agent/my_agent_v121.py:1057)  
```python
# AVANT
MAX_ACTIONS_TOTAL = 80
MAX_ACTIONS_PER_LEVEL = 30

# APRÈS (phase curriculum uniquement — réduire avant soumission Kaggle)
MAX_ACTIONS_TOTAL = 200
MAX_ACTIONS_PER_LEVEL = 60
```

---

## 8. Chantiers antérieurs — état de suivi (non abandonnés)

| Réf | Chantier | Statut |
|-----|----------|--------|
| L-031 | Forensic maximal v12.0 | ✅ DONE — base de données logs disponible |
| L-032 | Analyse croisée v12.0 | ✅ DONE — 25 jeux, classification préliminaire |
| L-033 | Analyse croisée v12.1 (fixes P0A/B/C/P1D) | ✅ DONE — 0 faux LEVEL_UP, 14 boucles |
| C-001 | Élargir `_GOAL_ATTRS` | ❌ OPEN — bloquant Palier 0 |
| C-002 | Meilleur log FRAME_INVENTORY | ❌ OPEN — recommandé |
| C-003 | Budget d'apprentissage | ❌ OPEN — recommandé avant Palier 1 |
| Q-001 | Conditions de victoire par jeu | ❌ OPEN BLOQUANT |
| Q-002 | Pourquoi `goal_found=False` × 25 | ❌ OPEN BLOQUANT |
| Q-005 | Signal GROWING `r11l` = victoire ? | ❌ OPEN IMPORTANT |

---

## 9. Résumé des décisions à prendre par l'utilisateur

| ID | Question | Décision requise |
|----|----------|-----------------|
| DU-001 | L'analyse des fichiers `environment_files/` par l'agent est-elle autorisée ? | OUI / NON |
| DU-002 | Les budgets MAX_ACTIONS peuvent-ils être augmentés pour l'apprentissage ? | OUI / NON + valeurs |
| DU-003 | "100% Palier 1" = combien de victoires reproductibles par jeu ? | 1 / 3 / autre |
| DU-004 | L'ordre des jeux peut-il être modifié (en dehors de Kaggle) ? | OUI / NON |
| DU-005 | Un jeu peut-il être mis en pause si ses conditions de victoire sont inconnues ? | OUI / NON |

---

**État d'avancement de ce rapport : 100 %**  
**Prochaine action :** Commit + push du rapport sur `git@github.com:vgactech/LUCY.git`  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**
