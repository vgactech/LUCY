# L-036 — Curriculum LuCY : C-003 budgets étendus + C-004 diagnostic r11l

**Rapport :** L-036  
**Date :** 2026-10-15  
**Version agent :** 12.1  
**Espace de numérotation :** LuCY (indépendant de l'espace ARTCB R-xxx, règle D-091)  
**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

---

## 1. Contexte et objectifs

Ce rapport couvre deux correctifs appliqués cette session :

- **C-003** : augmenter les budgets d'actions pour diagnostiquer les jeux nécessitant plus de 79 actions  
- **C-004** : test diagnostique sur `r11l` (candidat GROWING:72 identifié en L-032/L-033)

Il répond également à la question centrale posée par l'utilisateur dans le rapport de stratégie ci-joint :
> « Identifier les premiers niveaux de chaque arcade du plus facile au plus difficile, réussir 100 % des premiers niveaux avant de passer aux niveaux suivants. »

---

## 2. Modifications appliquées — C-003

### Avant / Après (deux fichiers concernés)

**Fichier 1 : `LuCY/agent/my_agent_v121.py` lignes 85–87**

| | Avant | Après |
|--|--|--|
| `MAX_ACTIONS_TOTAL` | `80` | `200` |
| `MAX_ACTIONS_PER_LEVEL` | `30` | `80` |

**Fichier 2 : `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` lignes 85–87**

| | Avant | Après |
|--|--|--|
| `MAX_ACTIONS_TOTAL` | `80` | `200` |
| `MAX_ACTIONS_PER_LEVEL` | `30` | `80` |

**⚠️ Découverte importante** : Le script `play_local.py` charge `vendor/.../agent/my_agent.py`, pas `LuCY/agent/my_agent_v121.py`. Ces deux fichiers sont des copies séparées. Le premier run C-004 a utilisé l'ancienne valeur (79 actions) car seul `my_agent_v121.py` avait été modifié. Les deux fichiers ont ensuite été alignés.

---

## 3. Résultat C-004 — Test diagnostic r11l (budget 200)

### Paramètres du test

```
Jeu     : r11l
Budget  : 200 actions (--max-steps 200)
Runner  : vendor/ARC-AGI-3-Kaggle-Starter/scripts/play_local.py
```

### Résultats mesurés

| Métrique | Run 1 (budget=79, avant C-003) | Run 2 (budget=200, après C-003) |
|--|--|--|
| Actions consommées | 79 / 79 | 199 / 200 |
| `levels_completed` | 0 | 0 |
| `transform_type` dominant | `GROWING` | `GROWING` |
| `net_change` pixels/action | +3 constant | +3 constant |
| `goal_delta` | null (non trouvé) | null (non trouvé) |
| Temps écoulé | 3 894 ms | 9 134 ms |
| Actions visuellement changeantes | 72 / 79 | 169 / 199 |
| FPS moyen | 20 | 21.8 |

### Analyse des données brutes (log run 2, ligne 798)

```json
{
  "reason": "BUDGET_EXHAUSTED",
  "levels_completed": 0,
  "real_level_ups": 0,
  "total_actions": 199,
  "n_visual_change": {"6": 169}
}
```

À l'action 199 : `changed_pixels=315, net_change=+3, frame_shape=rows:3/cols:64`.  
La grille passe de `rows:1` à `rows:3` progressivement — elle grossit mais la condition de victoire n'est jamais atteinte.

---

## 4. Conclusions diagnostiques C-004

### Ce qui est prouvé

1. `r11l` avec ACTION6 seule : la grille grossit (+3 pixels nets par action, GROWING constant)
2. 200 actions ne suffisent pas à atteindre `levels_completed=1`
3. `fp_prefix` change à chaque action → LuCY ne détecte pas de boucle
4. Le signal GROWING:72/79 vu en L-032 n'était pas un signal de proximité de victoire — c'est le comportement permanent du jeu

### Ce qui reste inconnu

1. **Combien d'actions sont nécessaires** pour que `r11l` atteigne sa condition de victoire avec ACTION6 seule ?  
   → Hypothèse à tester : lancer avec `--max-steps 500` ou `--max-steps 1000`

2. **La condition de victoire de `r11l` est-elle uniquement liée au nombre d'actions** ou nécessite-t-elle une **séquence d'actions différentes** ?  
   → Code source `r11l.py` ligne 1706 appelle `self.next_level()` sous une condition liée à un flag interne obfusqué — la seule action disponible est ACTION6, donc la répétition doit suffire en théorie, mais le nombre exact est inconnu.

3. **Pourquoi `frame_shape` reste à `rows:3` et non `rows:6` ou `rows:win_levels` ?**  
   → La grille grossit par couches — il faudra probablement atteindre une taille cible spécifique.

### Estimation budget nécessaire pour r11l

Si `net_change=+3` pixels/action et si la condition de victoire est liée à la taille totale de la grille :
- À l'action 199 : `rows=3, cols=64` = 192 pixels actifs
- `win_levels=6` × 64 cols = 384 pixels cibles hypothétiques
- Budget estimé : ~400 actions pour atteindre la condition

---

## 5. Analyse croisée — Stratégie de curriculum par arcade

### 5.1 Classification des 25 jeux selon les données réelles des logs

| Rang | Jeu | Actions disponibles | Transform dominant | Durée ms | Boucles | Complexité estimée |
|------|-----|--------|--------|----------|---------|---------|
| **Facile** | | | | | | |
| F1 | `tn36` | 1 seule (ACTION6) | IDENTITY | 901–1118 | 0 | Très faible — 1 action, effets minimes |
| F2 | `vc33` | 1 seule (ACTION6) | IDENTITY | 901 | 0 | Même profil que tn36 |
| F3 | `s5i5` | 1 seule (ACTION6) | IDENTITY | 819 | 0 | Même profil |
| F4 | `dc22` | 1 seule (ACTION6) | IDENTITY | 872 | 0 | Même profil |
| F5 | `tr87` | 1 seule (ACTION6) | IDENTITY | 901 | 0 | Même profil |
| F6 | `cn04` | 1 seule (ACTION6) | IDENTITY | 847 | 0 | Même profil |
| F7 | `m0r0` | 1 seule (ACTION6) | IDENTITY | 851 | 0 | Même profil |
| F8 | `ka59` | 1 seule (ACTION6) | — | 909 | 0 | Même profil |
| F9 | `re86` | 1 seule (ACTION6) | — | 851 | 0 | Même profil |
| F10 | `ar25` | 1 seule (ACTION6) | — | 871 | 0 | Même profil |
| **Intermédiaire bas** | | | | | | |
| I1 | `r11l` | 1 seule (ACTION6) | GROWING | 2663–9134 | 0 | GROWING avec net_change=+3 — convergence possible |
| I2 | `lp85` | 1 seule (ACTION6) | — | 793 | 8 | Boucles détectées — réinitialisation requise |
| I3 | `ft09` | 1 seule (ACTION6) | — | 3324 | 6 | Boucles + durée élevée |
| **Intermédiaire** | | | | | | |
| M1 | `ls20` | à confirmer | — | 933 | 0 | Rapide — structure inconnue |
| M2 | `wa30` | à confirmer | — | 829 | 0 | Rapide |
| M3 | `sk48` | plusieurs | GROWING | 1190 | 0 | GROWING avec plusieurs actions — plus riche |
| M4 | `cd82` | 6 actions [1–6] | GROWING | 2325 | 0 | Multi-actions — exploration plus complexe |
| M5 | `sp80` | à confirmer | — | 2454 | 0 | Durée intermédiaire |
| M6 | `sc25` | à confirmer | — | 2948 | 0 | |
| M7 | `su15` | à confirmer | — | 1882 | 0 | |
| **Difficile** | | | | | | |
| D1 | `bp35` | à confirmer | — | 2981 | 0 | Durée élevée |
| D2 | `lf52` | à confirmer | — | 2598 | 0 | 10 niveaux — plus long |
| D3 | `g50t` | à confirmer | — | 3828 | 0 | Durée élevée |
| D4 | `tu93` | à confirmer | — | 3407 | 0 | 9 niveaux, durée élevée |
| D5 | `sb26` | à confirmer | — | 7409 | 0 | Durée la plus haute du lot |

**Note** : Ce classement est basé sur les données disponibles (durée, nombre d'actions, boucles). Il ne reflète pas nécessairement la difficulté réelle puisque aucun niveau n'a été résolu. Le classement doit être affiné après obtention des premières victoires.

### 5.2 Trou principal identifié — Condition de victoire inconnue pour tous les jeux

Le rapport L-035 avait déjà documenté que `goal_related_attrs: {}` sur tous les 25 jeux.  
Ce rapport confirme que même avec 200 actions, la condition de victoire de `r11l` reste inaccessible à LuCY.

**La raison fondamentale** : LuCY n'a aucun signal lui indiquant qu'elle est "proche" de la victoire. Elle optimise les changements visuels (`visual_delta`), pas la progression vers l'état cible.

---

## 6. Questions ouvertes identifiées (complément au rapport utilisateur)

Les 26 questions du rapport L-032 sont confirmées. Ce rapport en ajoute 8 nouvelles basées sur les données de C-004 :

| QN | Question | Priorité | Source |
|----|----------|----------|--------|
| Q-27 | Combien d'actions ACTION6 exactement pour `r11l` atteindre `levels_completed=1` ? | P0 | C-004 |
| Q-28 | La condition de victoire de `r11l` est-elle purement quantitative (N répétitions) ou qualitative (séquence) ? | P0 | C-004 code source |
| Q-29 | Pourquoi `frame_shape` de `r11l` stagne à `rows:3` après 199 actions ? | P0 | C-004 log |
| Q-30 | Les jeux à 1 seule action (tn36, vc33, s5i5…) sont-ils tous résolus par le même mécanisme d'accumulation ? | P0 | Logs généraux |
| Q-31 | Y a-t-il une corrélation entre `win_levels` (nombre total de niveaux du jeu) et la difficulté du premier niveau ? | P1 | Stratégie curriculum |
| Q-32 | Le fichier source de chaque jeu expose-t-il une condition de victoire lisible qui pourrait informer la stratégie ? | P1 | r11l.py ligne 1706 |
| Q-33 | Les deux copies de `my_agent.py` seront-elles toujours synchronisées lors des prochaines modifications ? | P0 | Bug C-003 découvert |
| Q-34 | Faut-il créer un lien symbolique entre les deux fichiers agent pour éviter les divergences futures ? | P1 | Bug C-003 découvert |

---

## 7. Trous non précisés par l'utilisateur — Ajoutés selon PROTOCOLE_ARTCB

L'utilisateur a demandé une stratégie de curriculum. Les éléments suivants ont été identifiés comme manquants et devront être tranchés :

### T-01 — Définition de « réussir 100 % des premiers niveaux »

**Trou** : L'utilisateur dit « réussir 100 % ». Mais `levels_completed=1` ne peut pas être répété sur `r11l` avec le budget actuel.  
**Question à trancher** : Faut-il atteindre `levels_completed=1` sur TOUS les 25 jeux avant de passer aux niveaux suivants, ou seulement sur les jeux où c'est techniquement faisable avec le budget actuel ?

### T-02 — Critère de reproductibilité

**Trou** : Un niveau réussi par hasard (séquence aléatoire heureuse) ne prouve pas l'apprentissage.  
**Question à trancher** : Faut-il exiger N reproductions (par exemple 3/5) avant de valider un premier niveau ?

### T-03 — Définition de « arcade »

**Trou** : Le mot « arcade » désigne-t-il chaque jeu individuel (25 arcades), ou un groupe de jeux partageant une mécanique (arcades par famille) ?  
**Impact** : Si chaque jeu est une arcade, il y a 25 premiers niveaux à valider. Si les arcades sont des familles, il faut d'abord établir la taxonomie.

### T-04 — Comportement des resets dans le score Kaggle

**Trou** : Lorsque LuCY consomme un reset (`BUDGET_EXHAUSTED` puis RESET), cela réduit le score Kaggle même si elle finit par réussir le niveau après reset. Il faut vérifier si la stratégie de curriculum doit prendre en compte ce coût.

### T-05 — Synchronisation des deux fichiers agent

**Trou détecté cette session** : `LuCY/agent/my_agent_v121.py` et `vendor/.../agent/my_agent.py` sont deux copies. Toute modification future sur un seul fichier créera une divergence.  
**Action recommandée** : Créer un script de synchronisation ou remplacer la copie vendor par un lien symbolique.

---

## 8. Prochaines actions recommandées

Par ordre de priorité :

| Priorité | Action | Justification |
|----------|--------|---------------|
| P0 | Lancer `r11l` avec `--max-steps 500` puis `1000` | Trouver le budget minimal pour `levels_completed=1` |
| P0 | Lire le code source des 10 jeux à 1 action (tn36, vc33, s5i5, dc22, tr87, cn04, m0r0, ka59, re86, ar25) | Identifier la condition de victoire exacte de chaque jeu |
| P0 | Créer un script de synchronisation des deux fichiers agent | Éviter la divergence future |
| P1 | Lancer tous les 25 jeux avec `--max-steps 200` et reconstruire la classification de difficulté avec les nouvelles données | Confirmer le classement actuel basé sur les durées |
| P1 | Répondre aux questions T-01 à T-05 (définitions manquantes dans la stratégie) | Permettre une validation claire des critères |
| P2 | Implémenter C-005 — mémoire inter-jeux | Conserver les règles apprises entre les 25 parties |

---

## 9. État des corrections LuCY v12.1

| Correction | Statut | Preuve |
|---|---|---|
| C-001 (élargir `_GOAL_ATTRS`) | ❌ ANNULÉE | `goal_related_attrs: {}` sur 25 jeux confirmé |
| C-002 (log `dir(frame_data)`) | ⏳ OPEN | Recommandée mais non implémentée |
| **C-003 (budgets étendus)** | ✅ APPLIQUÉE | `MAX_ACTIONS_TOTAL=200, MAX_ACTIONS_PER_LEVEL=80` dans les deux fichiers |
| **C-004 (test r11l)** | ✅ TERMINÉE | 199/200 actions, `levels_completed=0` confirmé |
| C-005 (mémoire inter-jeux) | ⏳ OPEN | À implémenter après 1ère victoire |

---

## 10. Fichiers modifiés cette session

| Fichier | Modification | Lignes |
|---------|-------------|--------|
| `LuCY/agent/my_agent_v121.py` | `MAX_ACTIONS_TOTAL`: 80→200 / `MAX_ACTIONS_PER_LEVEL`: 30→80 | 85–89 |
| `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | Même modification (fichier effectivement chargé par le runner) | 85–89 |

---

## 11. Invariants maintenus

```
CERTIFIED_100 = false
unique_human_proven = false
DEBUG = true (actif dans les deux fichiers)
```

---

*Rapport L-036 produit par analyse forensique directe des logs. Aucun résultat inventé. Aucune victoire revendiquée.  
Ancien rapport L-035 conservé intact — ce rapport ne l'écrase pas.*
