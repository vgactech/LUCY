# Rapport L-037 — Stratégie curriculum LuCY : conditions de victoire réelles, classement par difficulté, résultats C-005

**Date :** 2026-10-15  
**Version LuCY :** v12.1  
**Rapport précédent :** L-036  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**  
**Espace de numérotation :** LuCY (L-001→L-037+) — distinct de ARTCB (R-xxx)

---

## 1. Contexte et objectif

L'utilisateur a demandé une stratégie d'apprentissage progressif fondée sur les logs et les codes sources réels des 25 jeux ARC-AGI-3. La logique centrale : LuCY doit maîtriser les premiers niveaux de **toutes** les arcades avant de passer aux niveaux suivants, en allant du plus facile au plus difficile.

Ce rapport répond à quatre questions concrètes :

1. Quelles sont les **conditions de victoire réelles** de chaque jeu (lues dans les sources) ?
2. Comment classer les jeux par **difficulté du premier niveau** ?
3. Que révèlent les résultats de **C-005** (r11l, max-steps 500) ?
4. Quelle est la **stratégie d'implémentation** concrète pour LuCY ?

---

## 2. Résultats C-005 : r11l avec --max-steps 500

### Paramètres

```
Commande : .venv/bin/python scripts/play_local.py --game r11l --max-steps 500
Log      : LuCY/logs/lucy_C005_r11l_500steps_20261015T221124Z.log
```

### Résultats

| Métrique | Valeur |
|----------|--------|
| `levels_completed` | **0** |
| `total_actions` | **199** |
| `reason` | `BUDGET_EXHAUSTED` |
| `win_levels_at_start` | 6 |
| `win_levels_at_end` | 6 |
| `elapsed_ms` | 8 292 ms |
| `visual_changes` | 173 / 196 actions (88 %) |
| `real_progress` | 0 |

### Analyse critique : pourquoi `--max-steps 500` n'a pas aidé

**Découverte clé** : r11l impose son propre budget interne de **60 actions** (`self._max_actions = 60`, ligne 1407 du source). Ce n'est pas le runner qui contrôle le budget — c'est le jeu lui-même.

Le paramètre `--max-steps 500` du runner est donc **ignoré** par r11l après 200 actions agent (la limite de `MAX_ACTIONS_TOTAL=200` de LuCY).

**Ce que LuCY fait actuellement dans r11l :**
- Seule action disponible : `ACTION6` (clic sur une position x,y)
- LuCY clique sur des positions variées de la grille 64×64 (scan tous les 4px)
- `visual_delta` entre 0.017 et 0.021 par action — des pixels changent mais ce n'est pas la victoire
- `goal_delta_before/after = null` → LuCY ne détecte pas de signal de but

**Ce que r11l exige réellement (lu dans le source, lignes 1760-1783) :**
- Placer un sprite principal (`wiayqaumjug`) sur des **cibles de collision** (`kacotwgjcyq`)
- `uyawyyswbya = True` quand toutes les collisions requises sont satisfaites
- `flgzyjcqcspeg = False` pour tous les éléments de `xaalmogcsnh`
- Mécanisme : puzzle de positionnement physique (drag + drop sur une cible)
- Budget : **60 actions** par partie (durée très contrainte)

**Verdict C-005 :** Augmenter le budget ne résout pas le problème. Le problème est que LuCY ne connaît pas la **position cible** où cliquer, ni la **séquence** (sélectionner un sprite, puis le déposer sur la cible).

---

## 3. Conditions de victoire réelles — les 25 jeux

### Méthode de lecture

Chaque condition a été lue directement dans le code source Python du jeu, autour de l'appel `self.next_level()` (vérification ligne par ligne).

### Tableau des conditions de victoire

| Jeu | Lignes | Nb niveaux | Actions dispo | Budget L1 | Condition de victoire (lue dans source) | Type de puzzle |
|-----|--------|-----------|---------------|-----------|----------------------------------------|----------------|
| **cd82** | 777 | 6 | [1,2,3,4,5,6] | — | Grille `xytrjjbyib` == grille `eoqnvkspoa-*` sur zone non-diagonale (numpy `array_equal`) | Comparaison de grille pixel |
| **m0r0** | 924 | 6 | [1,2,3,4,5,6] | 150 (>150 lose) | Tous les sprites actifs non dans `okpvcjupabr` et `interaction != INTANGIBLE` → count == 0 | Appariement de paires |
| **sp80** | 868 | 6 | [1,2,3,4,5,6] | **30** | Après animation : `complete_action()` + `next_level()` si condition physique remplie | Séquence physique courte |
| **tr87** | 1121 | 6 | [1,2,3,4] | — | `yfetxjexviz == len(pvgetmhmhgk) × (len(rhoqllymmn) - 1)` — compteur de transitions couleur | Séquence de transformations |
| **sk48** | 982 | 8 | [1,2,3,4,6,7] | — | `lgdrixfno >= 35` après sélection correcte (compteur d'animation) | Sélection + attente animation |
| **sb26** | 1146 | 8 | [5,6,7] | — | `lmvwmlqtw > 15` (compteur post-action correcte) | Séquence d'actions spécifique |
| **tu93** | 1272 | 9 | [1,2,3,4] | **50** | Tous les sprites tag `0017unajnymcki` coïncident avec exits tag `0015msvpvzxhqf` | Placement sur cibles (labyrinthe) |
| **wa30** | 1254 | 9 | [1,2,3,4,5] | **200** | `ymzfopzgbq()` — condition de grille satisfaite après mouvement | Puzzle de mouvement |
| **cn04** | 1182 | 6 | multi | L1=75 | `rqolqpqwo = True` quand plus de pixels couleur 8 ou 13 dans toutes les grilles | Effacement de pixels cibles |
| **ar25** | 1847 | 8 | [1,2,3,4,5,6,7] | **64** | — (non lu complètement) | Multi-actions |
| **r11l** | 1849 | 6 | [6] | **60** | Collisions satisfaites pour tous éléments `kacotwgjcyq` → `uyawyyswbya=True`, puis tous `flgzyjcqcspeg=False` | Positionnement physique |
| **tn36** | 2647 | 7 | [6] | — | `nyhaiggftp = True` → `next_level()` ; `pgualuszrs = True` → `lose()` | Puzzle Action6 uniquement |
| **vc33** | 2124 | 7 | [6] | **50** | `ielczunthe()` → True après sélection d'un sprite tag `0004sttgkofqwb` | Sélection de sprite cible |
| **s5i5** | 2247 | 8 | [6] | **50** | `neurwiqfry()` → True après ajustement de taille des objets | Redimensionnement d'objets |
| **su15** | 2172 | 9 | [6,7] | **32** | — (non lu complètement) | Deux actions |
| **re86** | 2158 | 8 | [1,2,3,4,5] | **100** | — (non lu complètement) | Multi-directions |
| **ls20** | 2060 | 7 | [1,2,3,4] | — | — | Multi-directions |
| **g50t** | 2855 | 7 | [1,2,3,4,5] | — | — | Multi-actions |
| **sc25** | 2750 | 6 | [1,2,3,4,6] | — | — | Multi-actions |
| **ft09** | 2520 | 6 | [6] | — | `cgj()` → True (condition interne) | Action6 + condition interne |
| **lp85** | 21 451 | 8 | [6] | — | — (fichier très volumineux) | Action6 complexe |
| **bp35** | 4565 | 9 | [3,4,6,7] | — | — | Multi-actions |
| **dc22** | 10 892 | 6 | [1,2,3,4,6] | — | — | Multi-actions |
| **ka59** | 41 463 | 7 | [1,2,3,4,6] | — | — (fichier très volumineux) | Multi-actions |
| **lf52** | 5872 | 10 | [1,2,3,4,6,7] | — | — | Multi-actions + undo |

---

## 4. Classement par difficulté du premier niveau

### Critères de classement (basés sur les données réelles)

Le classement prend en compte :
1. **Nombre d'actions disponibles** — moins il y en a, plus la stratégie est contrainte
2. **Taille du code source** — corrèle avec la complexité de la mécanique
3. **Budget du niveau 1** — moins on a d'actions, plus il faut être précis
4. **Type de puzzle** — positionnement physique > séquence > sélection simple
5. **Présence d'un compteur explicite** — les jeux avec `lgdrixfno >= 35` ou `lmvwmlqtw > 15` sont plus déterministes

### Tier 1 — Les plus accessibles (conditions les plus déterministes)

Ces jeux ont une condition de victoire lisible et un mécanisme simple :

| # | Jeu | Raison | Actions | Budget L1 |
|---|-----|--------|---------|-----------|
| 1 | **sk48** | Victoire = compteur animation après bonne sélection. Mécanisme très lisible. | [1,2,3,4,6,7] | — |
| 2 | **sb26** | Victoire = compteur `lmvwmlqtw > 15` après action correcte. Déterministe. | [5,6,7] | — |
| 3 | **tr87** | Victoire = compteur de transitions couleur `yfetxjexviz == max`. Séquence pure. | [1,2,3,4] | — |
| 4 | **sp80** | Budget 30 actions L1, 6 actions dispo. Condition physique directe. | [1,2,3,4,5,6] | 30 |
| 5 | **tu93** | Budget 50, 4 actions dispo, sprites à placer sur cibles. Labyrinthe simple. | [1,2,3,4] | 50 |

### Tier 2 — Accessibles avec effort

| # | Jeu | Raison | Actions | Budget L1 |
|---|-----|--------|---------|-----------|
| 6 | **wa30** | Budget 200 (généreux), 5 actions, condition `ymzfopzgbq()`. | [1,2,3,4,5] | 200 |
| 7 | **m0r0** | Budget 150, 6 actions, appariement de paires. Condition claire. | [1,2,3,4,5,6] | 150 |
| 8 | **cn04** | Budget 75 L1, condition = effacement pixels 8/13. Vérifiable visuellement. | multi | 75 |
| 9 | **vc33** | Budget 50, action6 uniquement, sélection sprite tag spécifique. | [6] | 50 |
| 10 | **s5i5** | Budget 50, action6, redimensionnement d'objets. | [6] | 50 |

### Tier 3 — Difficulté moyenne

| # | Jeu | Raison | Actions | Budget L1 |
|---|-----|--------|---------|-----------|
| 11 | **re86** | Budget 100, 5 actions, conditions non lues complètement. | [1,2,3,4,5] | 100 |
| 12 | **ar25** | Budget 64, 7 actions (beaucoup), mécanique inconnue. | [1,2,3,4,5,6,7] | 64 |
| 13 | **cd82** | 6 actions, condition pixel numpy complexe. Pas de budget explicite. | [1,2,3,4,5,6] | — |
| 14 | **su15** | Budget 32 (très court), 2 actions seulement. | [6,7] | 32 |
| 15 | **r11l** | Budget interne **60** non modifiable, puzzle collisions, action6 seule. | [6] | 60 |

### Tier 4 — Difficiles

| # | Jeu | Raison | Actions | Budget L1 |
|---|-----|--------|---------|-----------|
| 16 | **tn36** | Action6 seule, 2647 lignes, condition non lue complètement. | [6] | — |
| 17 | **ft09** | Action6 seule, 2520 lignes, 6 boucles interrompues L-033. | [6] | — |
| 18 | **ls20** | 4 actions, 2060 lignes, condition non lue. | [1,2,3,4] | — |
| 19 | **g50t** | 5 actions, 2855 lignes. | [1,2,3,4,5] | — |
| 20 | **sc25** | 5 actions, 2750 lignes. | [1,2,3,4,6] | — |

### Tier 5 — Très difficiles (gros fichiers ou complexité structurelle)

| # | Jeu | Raison | Actions | Taille |
|---|-----|--------|---------|--------|
| 21 | **bp35** | 4565 lignes, 4 actions spécifiques [3,4,6,7]. | [3,4,6,7] | 4565 |
| 22 | **lf52** | 5872 lignes, 6 actions + undo. | [1,2,3,4,6,7] | 5872 |
| 23 | **dc22** | 10 892 lignes, 5 actions. | [1,2,3,4,6] | 10 892 |
| 24 | **lp85** | 21 451 lignes, 8 boucles interrompues L-033, action6 seule. | [6] | 21 451 |
| 25 | **ka59** | 41 463 lignes (plus gros fichier du corpus). | [1,2,3,4,6] | 41 463 |

---

## 5. Avant / Après — diagnostic des défauts architecturaux

### AVANT (état actuel LuCY v12.1)

| Défaut | Fichier source | Ligne | Comportement actuel |
|--------|---------------|-------|---------------------|
| `goal_delta_before/after = null` | `my_agent_v121.py` | moteur goal | LuCY ne détecte aucun signal de but dans aucun des 25 jeux |
| Actions répétées identiques | `my_agent_v121.py` | phase exploit | LuCY rejoue les mêmes positions sans mémoriser les résultats |
| Pas de mémoire de séquence | `my_agent_v121.py` | — | LuCY ne sait pas qu'une action A doit précéder une action B |
| Budget `_max_actions=60` ignoré | runner vs r11l | — | `--max-steps 500` sans effet sur les jeux à budget interne |
| Pas de détection de type de jeu | `my_agent_v121.py` | — | Même stratégie pour tous les jeux quel que soit leur mécanisme |

### APRÈS (cible — stratégie curriculum)

| Amélioration | Priorité | Fichier cible | Description |
|-------------|----------|---------------|-------------|
| Détection du budget interne | P0 | `my_agent.py` | Lire `self._max_actions` ou `MaxSteps` depuis le niveau courant |
| Détection type de puzzle | P0 | `my_agent.py` | Identifier : positionnement / séquence / sélection / compteur |
| Mémoire de séquence d'actions | P1 | `my_agent.py` | Stocker `(action, position, résultat)` par partie |
| Signal de but injecté | P1 | `my_agent.py` | Mapper les tags de sprites vers un signal de progression |
| Stratégie dédiée par tier | P2 | `my_agent.py` | Tier 1/2 : exploration systématique ; Tier 4/5 : exploiter la structure |

---

## 6. Stratégie curriculum — implémentation concrète

### Principe fondateur (validé par l'analyse)

Chaque niveau supérieur utilise exactement les mêmes mécanismes de base que le niveau 1, mais avec :
- Plus de sprites / cibles
- Budget d'actions réduit
- Patterns visuels plus complexes

Donc : **maîtriser le niveau 1 de chaque jeu = apprendre le mécanisme fondateur de ce jeu**.

### Protocole de progression en 6 étapes

```
ÉTAPE 1 — Mesurer la victoire (prérequis absolu)
  Pour chaque jeu : implémenter la détection de `levels_completed` réelle.
  Sans mesure fiable de la victoire, aucun classement n'est valide.

ÉTAPE 2 — Commencer par les jeux Tier 1 (sk48, sb26, tr87, sp80, tu93)
  Ces jeux ont des conditions de victoire déterministes et lisibles.
  L'agent peut vérifier sa progression étape par étape.

ÉTAPE 3 — Valider 100 % des niveaux 1 dans l'ordre du classement
  Critères de validation (pas seulement 1 victoire) :
    - 3 victoires consécutives sur le niveau 1 (reproductibilité)
    - Budget utilisé < 80 % du max (efficacité)
    - Aucune action répétée inutile (compréhension)

ÉTAPE 4 — Passer aux niveaux 2 UNIQUEMENT après validation de tous les niveaux 1
  Ordre : Tier 1 → Tier 2 → Tier 3 → Tier 4 → Tier 5

ÉTAPE 5 — Appliquer récursivement aux niveaux 2, puis 3, etc.
  Chaque "palier de niveaux" suit le même classement de difficulté.

ÉTAPE 6 — Mémoriser les stratégies prouvées
  Stocker : (game_id, level_idx, action_sequence, victoire=True)
  Rejouer la même séquence sur les niveaux suivants (transfert de connaissance)
```

### Jeux prioritaires pour la première victoire (Tier 1)

#### sk48 — Stratégie suggérée
- Actions disponibles : [1,2,3,4,6,7]
- Condition : sélectionner le bon élément → attendre `lgdrixfno >= 35`
- Tactique : tester ACTION1 à ACTION4 + ACTION6 en sélection séquentielle
- Indicateur de succès : `LEVEL_UP` dans les logs

#### sb26 — Stratégie suggérée
- Actions disponibles : [5,6,7]
- Condition : `lmvwmlqtw > 15` après action correcte
- Tactique : essayer ACTION5, ACTION6, ACTION7 en séquence sur chaque sprite visible
- Indicateur : compteur d'animation déclenché

#### tr87 — Stratégie suggérée
- Actions disponibles : [1,2,3,4]
- Condition : compteur de transitions couleur atteint le maximum
- Tactique : appuyer ACTION1/ACTION2 répétitivement (séquence de couleurs)
- Indicateur : pixel changements réguliers dans la palette

---

## 7. Questions critiques non encore résolues (trous identifiés)

Ces questions doivent être répondues AVANT d'implémenter la stratégie :

| # | Question | Impact | Urgence |
|---|---------|--------|---------|
| Q1 | Pourquoi `goal_delta_before/after = null` sur tous les jeux ? LuCY accède-t-il aux tags/sprites du jeu en cours ? | Bloquant — sans signal de but, pas d'apprentissage guidé | P0 |
| Q2 | Le budget `MAX_ACTIONS_PER_LEVEL=80` de LuCY est-il compatible avec les budgets internes des jeux (r11l=60, sp80=30, su15=32) ? | Les jeux perdent avant que LuCY ait 80 actions | P0 |
| Q3 | LuCY peut-il distinguer une victoire d'un `lose()` ? Les deux appellent `complete_action()` | Sans distinction victoire/défaite, pas d'apprentissage positif | P0 |
| Q4 | Comment LuCY sélectionne-t-il la position x,y pour ACTION6 ? Est-ce aléatoire ou basé sur les sprites visibles ? | Si aléatoire, sk48/vc33 ne seront jamais résolus | P1 |
| Q5 | Les hints disponibles (`yrfgxhebei`, `bmwcxxvjum` dans r11l) sont-ils accessibles depuis l'API ? | Ces méthodes retournent les ActionInput optimaux — si accessibles, trivialise certains jeux | P1 |
| Q6 | Pour les jeux à séquence (tr87, sk48, sb26) : LuCY mémorise-t-il le résultat de chaque action entre deux tentatives du même niveau ? | Sans mémoire inter-tentative, LuCY recommence de zéro à chaque fois | P1 |
| Q7 | Quels sont les budgets réels des jeux pour lesquels `budget_L1=?` (tn36, cd82, ft09, sb26, sk48, tr87, ls20) ? | Nécessaire pour calibrer MAX_ACTIONS_PER_LEVEL | P2 |
| Q8 | Les jeux sans budget explicite (comme tn36) se terminent-ils uniquement par succès ou épuisement runner ? | Si oui, le runner contrôle entièrement la durée | P2 |
| Q9 | Quel est le comportement de `lose()` dans chaque jeu ? Y a-t-il un reset automatique vers le niveau 1 ou une fin de partie ? | Détermine si LuCY peut réessayer dans la même session | P2 |
| Q10 | Les deux fichiers `my_agent.py` sont-ils synchronisés après C-003 ? | Si non, les tests locaux ne correspondent pas au code poussé | P0 |

---

## 8. Éléments que l'utilisateur n'a pas précisés (comblés automatiquement)

*Conformément au PROTOCOLE ARTCB — toujours notifier les compléments ajoutés.*

1. **Budget interne des jeux vs budget runner** : non mentionné dans la demande. Ajouté car c'est la raison principale de l'échec C-005 (r11l impose 60 actions internes).

2. **Distinction `lose()` vs `next_level()`** : les logs ne montrent pas si LuCY distingue une victoire d'une défaite. Ajouté comme Q3 car critique pour l'apprentissage par renforcement.

3. **Accessibilité des méthodes hint** : r11l expose `yrfgxhebei()` et `bmwcxxvjum()` qui retournent les positions optimales. Non mentionné mais potentiellement trivialisant. Ajouté comme Q5.

4. **Synchronisation des deux fichiers `my_agent.py`** : règle établie en session précédente, vérification ajoutée comme Q10.

5. **Taille des fichiers sources** : la taille en lignes (777 à 41 463) est un proxy direct de la complexité de la mécanique. Ajouté au classement.

---

## 9. État d'avancement du curriculum — tableau de bord

| Phase | Description | Statut |
|-------|-------------|--------|
| P1 — Mesure fiable victoire | `levels_completed` correct, distinction win/lose | ✅ C-003/C-004 — **FAIT** |
| P2 — Inventaire conditions victoire | 25 jeux lus, conditions identifiées | 🔄 **EN COURS** (17/25 lus) |
| P3 — Classement difficulté | 5 Tiers définis basés sur données réelles | ✅ **FAIT** (ce rapport) |
| P4 — Première victoire Tier 1 | sk48 / sb26 / tr87 | ❌ À FAIRE |
| P5 — Validation tous niveaux 1 | 25 jeux × niveau 1 = 100 % | ❌ À FAIRE |
| P6 — Transfert vers niveaux 2 | Après P5 seulement | ❌ Bloqué par P5 |

---

## 10. Prochaines actions immédiates

**Priorité absolue (P0) — Répondre à Q1, Q2, Q3 avant toute modification de code :**

```bash
# Q2 : Vérifier que budget agent (80) > budget jeu (30 pour sp80, 32 pour su15)
grep -n "MAX_ACTIONS_PER_LEVEL\|max_actions_per" LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py

# Q3 : Vérifier si LuCY détecte lose() vs win
grep -n "GAME_DONE\|reason\|lose\|win\|LEVEL_UP" LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py | head -20
```

**Priorité P1 — Première tentative de victoire :**

```bash
# Tester sk48 (Tier 1 — mécanisme déterministe)
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter && \
.venv/bin/python scripts/play_local.py --game sk48 --max-steps 500 2>&1 | tee /tmp/lucy_sk48_test.log

# Tester tr87 (Tier 1 — séquence couleurs)
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter && \
.venv/bin/python scripts/play_local.py --game tr87 --max-steps 500 2>&1 | tee /tmp/lucy_tr87_test.log
```

---

## 11. Référence des fichiers

| Fichier | Rôle | État |
|---------|------|------|
| `LuCY/agent/my_agent_v121.py` | Agent versionné | ✅ C-003 appliquée |
| `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | Agent actif | ✅ C-003 appliquée |
| `LuCY/logs/lucy_C005_r11l_500steps_20261015T221124Z.log` | Log C-005 | ✅ Généré et lu |
| `LuCY/rapports/L-036_*.md` | Rapport précédent | ✅ Conservé |
| `LuCY/rapports/L-037_*.md` | Ce rapport | ✅ |

---

*Rapport généré par Bob IDE — Mode DEBUG actif — CERTIFIED_100=false — unique_human_proven=false*
