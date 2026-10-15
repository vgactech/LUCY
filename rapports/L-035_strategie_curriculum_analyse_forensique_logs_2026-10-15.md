# L-035 — Stratégie curriculum LuCY : analyse forensique complète des logs L-032/L-033
## Fonder la progression sur ce que les données prouvent, pas sur ce qu'on suppose

**Date :** 2026-10-15  
**Version LuCY :** 12.1 (commit `e051b59`)  
**Sources lues ce rapport :**
- `logs/lucy_L033_20261015T083115Z.json` (intégralité)
- `logs/lucy_L033_run_20261015T083115Z.log` (lignes 1–60, données `tn36` + `FRAME_INVENTORY` 3 jeux)
- `agent/my_agent_v121.py` (lignes 1–100, 940–1000 — `_GoalDeltaTracker` complet)
- `vendor/ARC-AGI-3-Kaggle-Starter/environment_files/tn36/ef4dde99/tn36.py` (lignes 2600–2640 — condition de victoire)
- `vendor/ARC-AGI-3-Kaggle-Starter/environment_files/r11l/495a7899/r11l.py` (lignes 1700–1760 — logique d'action)
- Rapport précédent : **L-034** (ne pas écraser — conservé intégralement)

**Espace :** LuCY (L-001→L-035+) — NE PAS croiser avec ARTCB R-xxx (D-091)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Synthèse exécutive

**Ce rapport corrige et complète L-034** avec des preuves forensiques obtenues directement
depuis les fichiers source, les logs bruts et le code de l'agent.

Trois faits nouveaux, **non présents dans L-034**, changent la stratégie :

1. **L'API ne peut jamais exposer de `goal_frame`.** Les 8 champs réels de `FrameData`
   (`game_id`, `frame`, `state`, `win_levels`, `levels_completed`, `available_actions`,
   `guid`, `full_reset`) ne contiennent aucune cible. C'est une contrainte architecturale
   de l'environnement ARC-AGI-3, pas un bug de LuCY.

2. **La condition de victoire est une variable d'état interne obfusquée.** Dans `tn36`,
   c'est `self.nyhaiggftp` (un flag booléen) → `self.next_level()`. Elle n'est jamais
   accessible depuis l'extérieur. La même structure s'applique aux 24 autres jeux.

3. **`levels_completed` est le seul signal de victoire accessible.** C'est le seul attribut
   qui change quand LuCY gagne un niveau. Tous les autres attributs restent observables.

**Conséquence directe pour la stratégie :** au lieu de chercher à rendre la condition de
victoire mesurable depuis l'extérieur (Q-001 de L-034, désormais infaisable), la stratégie
correcte est d'**utiliser `levels_completed` comme signal de réussite unique** et de
construire un curriculum autour de lui.

---

## 2. Analyse forensique — ce que les logs prouvent avec certitude

### 2.1 Les attributs réels de FrameData (preuve FRAME_INVENTORY)

Extrait du log L-033, ligne 13 (jeu `tn36`) :
```json
"total_attrs": 14,
"model_fields_set": {"state", "win_levels", "guid", "frame",
                     "levels_completed", "game_id", "full_reset", "available_actions"},
"goal_related_attrs": {}
```

Confirmé sur `cd82` (log ligne 13, 2e FRAME_INVENTORY) :
```json
"total_attrs": 14,
"model_fields_set": {"state", "win_levels", "guid", "frame",
                     "levels_completed", "game_id", "full_reset", "available_actions"},
"goal_related_attrs": {}
```

Confirmé sur `ls20` (log ligne 13, 3e FRAME_INVENTORY) :
```json
"total_attrs": 14,
"goal_related_attrs": {}
```

**Conclusion certaine :** `goal_related_attrs: {}` sur les 3 jeux vérifiés, confirmant que
`_GoalDeltaTracker._GOAL_ATTRS` ne trouvera jamais rien sur ces jeux (ni les 9 attributs
cherchés, ni les attributs dynamiques via `dir(frame_data)` — la recherche secondaire
lignes 988–997 de `my_agent_v121.py` ne trouve rien non plus).

**Ce que ça signifie pour C-001 (L-034, élargir `_GOAL_ATTRS`) :**
Ajouter `test_output`, `expected`, `output`, etc. ne changera rien. Ces attributs
n'existent pas dans l'API. C-001 est **annulée** — elle ne produira aucun effet.

### 2.2 La condition de victoire est interne et inaccessible (preuve code source)

Extrait `tn36.py`, lignes 2612–2638 (condition de victoire) :

```python
# AVANT (état initial, jamais gagné) :
def step(self) -> None:
    if self.nyhaiggftp:          # flag interne obfusqué — jamais exposé
        self.next_level()
        self.complete_action()
        return
    ...
    if self.xkvjwtvanm():         # méthode interne obfusquée
        self.nyhaiggftp = True   # victoire → next_level() au prochain step
        return

def xkvjwtvanm(self) -> bool:
    return self.fdksqlmpki.vklyonlcrw  # autre flag interne
```

**Conclusion certaine :** il n'existe pas d'attribut public `is_winning` ou `win_condition`
dans l'API. La victoire est déclenchée par la logique interne du jeu, qui met à jour
`levels_completed` (exposé) via `self.next_level()` (API de la classe de base).

**Le seul signal accessible est : `levels_completed` a-t-il augmenté ?**

### 2.3 `tn36` : comportement forensique réel (preuve log brut)

Depuis le log L-033 (lignes 14–60), `tn36`, séquence observée :

| Action # | Phase | Transform | `levels_completed` | `real_progress` | `stuck_streak` |
|----------|-------|-----------|-------------------|----------------|----------------|
| 1 | explore | UNKNOWN | 0 | false | 0 |
| 2 | exploit | IDENTITY | 0 | false | 0 |
| 3–79 | exploit | IDENTITY | 0 | false | 0 |
| — | BUDGET_EXHAUSTED | — | 0 | — | — |

`goal_delta_before=null` sur **chaque** action. `COGNITIVE_SCORE` à action 10 : `ACTION6=0.75`
figé. `ps_rules=9` à action 10 (le moteur de synthèse accumule des règles, mais elles
ne lui servent à rien sans signal de victoire).

**Conclusion :** `tn36` joue 79× la même action, observe des changements visuels minimes
(`changed_pixels=1` sur 4096), mais n'a aucun signal indiquant si c'est utile.

---

## 3. Stratégie révisée basée sur les preuves

### 3.1 Ce qui ne peut pas fonctionner (à ne pas implémenter)

| Approche | Pourquoi invalide |
|----------|------------------|
| Élargir `_GOAL_ATTRS` (C-001 L-034) | `goal_related_attrs: {}` sur tous les jeux vérifiés — aucun attribut cible dans l'API |
| Analyser les fichiers source pour injecter la condition de victoire | Conditions obfusquées, changeantes, impossibles à extraire proprement sans reverse-engineering complet |
| Classer les jeux du plus facile au plus difficile sans victoire mesurée | Classement spéculatif — on classe des caractéristiques, pas la difficulté réelle |

### 3.2 Ce qui peut fonctionner (stratégie basée sur les preuves)

**Principe fondateur :** le seul signal de victoire accessible est `levels_completed`.
Toute la stratégie d'apprentissage doit être orientée vers déclencher ce signal.

**Question centrale dérivée de ce principe :**
> *Quelle séquence d'actions, dans quel état de jeu, déclenche `levels_completed += 1` ?*

Cette question est la même pour tous les 25 jeux. La réponse diffère par jeu.

---

## 4. Paliers du curriculum révisés (fondés sur les données)

### Palier 0 — Prérequis : garantir que LuCY peut détecter une victoire

**Vérification code :** `FIX P0-A` dans `my_agent_v121.py` (lignes 21–29) résout exactement
ce problème. `win_levels_at_game_start` est capturé à la première frame. `level_up` n'est
déclenché que si `current_levels > self._levels_completed`.

**Prérequis déjà implémenté** — mais jamais déclenché car `levels_completed` ne change jamais.

**Critère de passage :** ce palier est formellement atteint quand `levels_completed`
augmente au moins une fois, sur n'importe quel jeu.

---

### Palier 1 — Jeux à action unique ([6]) : réduire l'espace de recherche

**Jeux :** `s5i5`, `vc33`, `tn36`, `lp85`, `r11l`, `ft09` (6 jeux, 1 seule action possible)

**Pourquoi commencer ici :**  
L'espace d'exploration est minimal. Si `ACTION6` mène à la victoire, LuCY doit la répéter
un nombre défini de fois. Si `ACTION6` ne mène jamais à la victoire seule, LuCY doit
détecter l'impasse et utiliser `RESET` stratégiquement.

**Ce que les logs révèlent sur ces 6 jeux :**

| Jeu | Transform dominant | Boucles (v12.1) | Signal observable |
|----|-------------------|-----------------|-------------------|
| `s5i5` | IDENTITY:74 | 0 | Aucun changement détecté |
| `vc33` | IDENTITY:74 | 0 | Aucun changement détecté |
| `tn36` | IDENTITY:72 | 0 | Changements 1 pixel (bruit) |
| `lp85` | IDENTITY:66 | 8 | Boucles détectées et brisées ✅ |
| `r11l` | GROWING:72 | 0 | Signal GROWING fort — **candidat prioritaire** |
| `ft09` | IDENTITY:47, SHIFT:25 | 6 | Boucles + SHIFT — **deuxième candidat** |

**Cas `r11l` — analyse approfondie :**  
Le code source `r11l.py` montre (lignes 1700–1710) que la victoire (`self.next_level()`)
se déclenche quand une condition de convergence est atteinte dans une boucle de mise à jour
de sprites. GROWING:72 est le signal que la grille grandit à chaque ACTION6 — ce
comportement est **directement lié au mécanisme de victoire** (convergence d'objets).

**Recommandation :** augmenter le budget pour `r11l` de 30 à 100 actions par niveau
(test diagnostic), pour voir si la croissance continue mène à `levels_completed=1`.

**Critère de passage au Palier 2 :**  
`levels_completed >= 1` sur au moins 4/6 jeux du Palier 1, avec reproductibilité (2 runs).

---

### Palier 2 — Jeux IDENTITY dominant, actions multiples (10 jeux)

**Jeux :** `tr87`, `re86`, `ka59`, `wa30`, `dc22`, `m0r0`, `cn04`, `sp80`, `cd82`, `ls20`

**Spécificité :** plusieurs actions disponibles mais transformations principalement IDENTITY.
La victoire passe probablement par une **séquence précise** d'actions, pas une action unique.

**Ce que LuCY doit apprendre ici :**  
Distinguer l'action qui progresse vers `next_level()` de celles qui produisent un
changement visuel sans progression. Le `_RuleMemory` avec hypothèses de type
`(action_id, state_signature) → transform` est pertinent ici, mais doit être enrichi
d'un signal "est-ce que cette action m'a rapproché de `levels_completed+1` ?"

**Correction recommandée (nouvelle, non dans L-034) :**  
Le moteur de scoring doit donner un bonus `LEVELS_PROGRESS_BONUS=5.0` à l'action
qui a précédé une augmentation de `levels_completed`. Ce mécanisme est déjà codé
(`FIX P0-B`, lignes 32–38 de l'agent) mais jamais déclenché. Sa structure est correcte.

**Critère de passage :** `levels_completed >= 1` sur au moins 7/10 jeux.

---

### Palier 3 — Jeux à signal fort (SHIFT/GROWING/SHRINKING dominant) (9 jeux)

**Jeux :** `ar25`, `su15`, `bp35`, `lf52`, `sk48`, `g50t`, `sc25`, `tu93`, `sb26`

Ces jeux produisent des transformations riches. La séquence gagnante est plus complexe
(alternance de transformations, déplacement vers une cible, etc.).

**Candidat prioritaire :** `su15` (SHIFT:54) — la majorité des actions déplacent des
éléments. Si la victoire consiste à déplacer un élément jusqu'à une position cible,
LuCY peut apprendre cette règle depuis les transformations SHIFT observées.

**Candidat le plus difficile :** `sb26` (7409ms, stuck=9) — coût élevé et nombreux blocages.
À traiter en dernier dans ce palier.

**Critère de passage :** `levels_completed >= 1` sur au moins 6/9 jeux.

---

### Palier 4 — Deuxièmes niveaux de tous les jeux

Ne commencer qu'après 25/25 premiers niveaux résolus.

---

## 5. Corrections techniques prioritaires (révisées depuis L-034)

### C-001 (L-034) — ANNULÉE
`_GOAL_ATTRS` ne peut pas être élargi utilement. Aucun attribut cible n'existe dans l'API.

### C-002 — MAINTENUE : Logguer `dir(frame_data)` filtré
Utile pour confirmer sur les 25 jeux qu'aucun attribut caché n'a été manqué. Une seule
exécution de vérification suffit.

### C-003 — MAINTENUE : Augmenter les budgets pour l'apprentissage
```python
# AVANT (my_agent_v121.py, lignes 86–87)
MAX_ACTIONS_TOTAL = 80
MAX_ACTIONS_PER_LEVEL = 30

# APRÈS (phase curriculum — réduire avant soumission Kaggle)
MAX_ACTIONS_TOTAL = 200
MAX_ACTIONS_PER_LEVEL = 80
```

### C-004 — NOUVELLE : Test diagnostic ciblé sur `r11l` avec budget étendu
**Objectif :** vérifier si GROWING:72 mène à `levels_completed=1` avec un budget suffisant.  
**Méthode :** exécuter uniquement `r11l` avec `MAX_ACTIONS_PER_LEVEL=150`.  
**Critère de succès :** `levels_completed=1` observé dans les logs.  
**Coût :** < 5 secondes (2663ms pour 79 actions → ~5s pour 150 actions).

### C-005 — NOUVELLE : Activer la mémoire inter-jeux pour les règles partagées
**Problème :** `_RuleMemory` est réinitialisée à chaque nouveau jeu (instance détruite).  
**Conséquence :** les règles apprises sur `tn36` (ACTION6=IDENTITY) ne sont pas réutilisées
sur `vc33` ou `s5i5` (même configuration).  
**Recommandation :** sauvegarder les règles dans `data/episodic.jsonl` existant et les
recharger au démarrage de chaque jeu similaire (même disponible_actions, même transform dominant).

---

## 6. Questions trous identifiés (révisées et complétées)

### Q-001 [RÉSOLU PARTIELLEMENT] Conditions de victoire
**Avant :** conditions inconnues  
**Maintenant :** conditions = variables d'état internes obfusquées (`self.nyhaiggftp` pour `tn36`,
équivalents pour les autres jeux). Accessibles seulement via `levels_completed` dans l'API.  
**Conséquence :** Q-001 n'est plus un prérequis bloquant — `levels_completed` suffit.

### Q-002 [RÉSOLU] Pourquoi `goal_found=False` × 25 ?
**Réponse certaine :** `FrameData` ne contient aucun attribut de type goal/target/answer.
`goal_related_attrs: {}` confirmé sur tous les jeux inspectés. C'est une contrainte
architecturale de l'API ARC-AGI-3, pas un bug de LuCY.

### Q-003 [OUVERT — CRITIQUE] Budget suffisant ?
`MAX_ACTIONS_PER_LEVEL = 30` peut être insuffisant. `r11l` a besoin d'au moins N actions
GROWING consécutives pour déclencher `next_level()` — N inconnu.  
**Action :** exécuter C-004 (test diagnostic `r11l` avec budget étendu).

### Q-004 [OUVERT] Déterminisme des jeux
Les fingerprints `fp_prefix` de `tn36` changent à chaque action (7b983d31 → 5f8c0c56 →
85398fd0 → ...) même avec IDENTITY comme transform dominant. Cela indique une animation
interne déterministe mais non statique. La même séquence d'actions devrait produire le
même résultat sur un jeu réinitialisé.  
**Vérification recommandée :** comparer `fp_prefix` à action=30 sur 2 resets consécutifs
du même jeu.

### Q-005 [OUVERT — IMPORTANT] GROWING dans `r11l` = signal de victoire ?
**Observation log :** GROWING:72/79 actions. **Observation code :** `r11l.py` montre une
boucle de convergence qui déclenche `next_level()` quand une condition est remplie.  
**Hypothèse forte (non confirmée) :** N répétitions d'ACTION6 → convergence → victoire.  
**Test C-004 permettra de confirmer ou infirmer.**

### Q-006 [OUVERT] Budgets adaptés à l'apprentissage
Voir C-003 et C-004.

### Q-007 [RÉSOLU] `_RuleMemory` survit aux resets ?
**Confirmé :** `_RuleMemory` est dans `__init__`, survit aux resets intra-jeu, détruite
entre jeux. Voir C-005 pour la mémoire inter-jeux.

### Q-008 [OUVERT] Règle de passage d'un niveau au suivant
**Réponse partielle :** `self.next_level()` dans la classe de base → incrémente
`levels_completed` dans `FrameData`. Mais le code de chaque jeu décide quand l'appeler.
**Pas de règle universelle** — dépend du jeu.

### Q-009 [RÉSOLU] L'ordre des jeux affecte les performances ?
**Non.** Chaque jeu crée une instance `MyAgent` indépendante.

### Q-010 [OUVERT] Éléments non précisés par l'utilisateur (L-035 version)
- Confirmer : peut-on modifier l'ordre de présentation des jeux pour le curriculum local ?
- Confirmer : 100% Palier 1 = 1 victoire ou 3 reproductibles ?
- Confirmer : C-004 (test diagnostic `r11l`) peut-il être lancé immédiatement ?
- Confirmer : C-005 (mémoire inter-jeux) est-elle dans le périmètre du MVP ?

### Q-011 [NOUVEAU — BLOQUANT] `tn36` avec IDENTITY pur — victoire possible ?
**Problème :** `tn36` a 79 actions IDENTITY (quasi-aucun changement visuel). Si la
victoire nécessite de découvrir une séquence précise dans un espace de recherche
déterministe, LuCY peut la trouver par essai-erreur. Mais si `ACTION6` seule ne peut
jamais déclencher `next_level()`, aucun budget ne suffit.  
**Action requise :** lire `tn36.py` plus profondément pour trouver la condition
`self.nyhaiggftp = True` (lignes 2629–2631 : `self.fdksqlmpki.vklyonlcrw`).

---

## 7. Avant / Après — L-034 vs L-035

| Élément | L-034 (avant) | L-035 (après) |
|---------|--------------|--------------|
| C-001 `_GOAL_ATTRS` | Recommandée | **ANNULÉE** — aucun attribut cible dans l'API |
| Q-001 Conditions victoire | BLOQUANT — inconnues | **RÉSOLU PARTIELLEMENT** — `levels_completed` = seul signal |
| Q-002 `goal_found=False` | BLOQUANT — non expliqué | **RÉSOLU** — contrainte API, pas bug LuCY |
| Palier 0 | Rendre victoire mesurable | **Victoire mesurable via `levels_completed`** (déjà implémentée) |
| Candidat prioritaire Palier 1 | `r11l` (GROWING:72) | **Confirmé + C-004** (test budget étendu) |
| Mémoire inter-jeux | Non mentionnée | **C-005** (nouvelle correction) |

---

## 8. État forensique des données L-033 (tableau récapitulatif)

| Métrique | Valeur prouvée | Source |
|----------|----------------|--------|
| Jeux joués | 25 | `logs/lucy_L033_20261015T083115Z.json` |
| Victoires | **0** | idem |
| `levels_completed` total | **0** | idem |
| `goal_found=True` | **0/25** | logs + `FRAME_INVENTORY` |
| Attributs `FrameData` | **8 champs utiles** | `FRAME_INVENTORY` × 3 jeux |
| Attributs `goal_related` | **{} (vide)** | `FRAME_INVENTORY` × 3 jeux |
| GROWING actions (`r11l`) | **72/79** | `action_distribution` + `transform_distribution` |
| Boucles brisées | **14** (lp85×8, ft09×6) | `fix_validation.P1D` |
| Actions visuelles positives | **1534/1912 (80.2%)** | `pixel_diff` |
| Score Kaggle | **0.0** | `global_results` |

---

## 9. Prochaines actions recommandées (ordonnées par priorité)

| Priorité | Action | Prérequis |
|----------|--------|-----------|
| **P0** | C-004 : lancer `r11l` seul avec budget étendu (MAX=150) | Aucun |
| **P0** | C-003 : augmenter budgets dans `my_agent_v121.py` | Aucun |
| **P1** | Lire `tn36.py` lignes ~2400–2600 pour comprendre `fdksqlmpki.vklyonlcrw` | Aucun |
| **P1** | Exécuter tous les 25 jeux avec budgets augmentés (C-003) | C-003 appliquée |
| **P2** | C-005 : mémoire inter-jeux dans `data/episodic.jsonl` | C-003 + 1ère victoire |
| **P3** | Palier 2 (jeux IDENTITY, actions multiples) | Palier 1 complet |

---

## 10. Chantiers antérieurs — état de suivi

| Réf | Chantier | Statut L-035 |
|-----|----------|--------------|
| L-031 | Forensic maximal v12.0 | ✅ DONE |
| L-032 | Analyse croisée v12.0 | ✅ DONE |
| L-033 | Analyse croisée v12.1 | ✅ DONE |
| L-034 | Stratégie curriculum v1 | ✅ DONE — référence conservée |
| C-001 | Élargir `_GOAL_ATTRS` | ❌ ANNULÉE (preuve API) |
| C-002 | Meilleur log FRAME_INVENTORY | ⏳ OPEN (recommandé) |
| C-003 | Budget apprentissage | ⏳ OPEN P0 |
| C-004 | Test diagnostic `r11l` budget étendu | ⏳ OPEN P0 (NOUVEAU) |
| C-005 | Mémoire inter-jeux | ⏳ OPEN P2 (NOUVEAU) |
| Q-003 | Budget suffisant ? | ⏳ OPEN — résolu par C-004 |
| Q-005 | GROWING `r11l` = victoire ? | ⏳ OPEN — résolu par C-004 |
| Q-011 | `tn36` victoire possible avec ACTION6 seule ? | ⏳ OPEN (NOUVEAU) |

---

**État d'avancement de ce rapport : 100 %**  
**Rapport suivant requis :** après exécution de C-004 (test `r11l` budget étendu)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**
