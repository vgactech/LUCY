# L-042 — Audit critique LuCY : r11l, budget, stratégie et 5 lacunes

**Date :** 2026-10-16  
**Auteur :** Agent LuCY (Bob IDE — session post-L-036)  
**Basé sur :** rapport L-036 (utilisateur), logs `lucy_C005_r11l_500steps_20261015T221124Z.log`, code source `r11l.py` (lignes 1404–1840), `my_agent_v121.py` (lignes 86–1124)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**  
**Espace de numérotation :** L-xxx (LuCY — distinct de l'espace ARTCB R-xxx, règle D-091)**

---

## Résumé exécutif

Ce rapport répond à l'audit critique fourni par l'utilisateur après L-036. Il couvre :

1. **Découverte P0 : budget r11l = 200, pas 500** — le nom du log était trompeur
2. **Architecture r11l** — seule ACTION6 disponible structurellement (hardcodé ligne 1440)
3. **Mécanisme de victoire r11l** — basé sur des collisions de sprites, pas sur un pixel count
4. **FIX P1-D** dans v12.1 — détection de boucle ACTION unique (présent dans le code)
5. **État des 5 lacunes T-01→T-05** après lecture du code source réel
6. **Plan d'action P0/P1** mis à jour

---

## 1. Découverte critique P0 — Budget réel = 200 (pas 500)

### Avant (intention dans le nom du fichier log)

```
Nom du fichier : lucy_C005_r11l_500steps_20261015T221124Z.log
Intention annoncée dans le rapport L-036 : "tester r11l avec 500 actions"
```

### Après (valeur lue dans le log + code source)

```python
# my_agent_v121.py — ligne 88 (lu directement)
MAX_ACTIONS_TOTAL = 200   # AVANT: 80 — commentaire ligne 86
MAX_ACTIONS_PER_LEVEL = 80  # AVANT: 30 — commentaire ligne 87
```

```
GAME_INIT dans le log (ligne 15) :
  "max_actions_total": 200
  "max_actions_per_level": 80

GAME_DONE (fin du log) :
  reason=BUDGET_EXHAUSTED
  total_actions=199
  levels_completed=0
```

**Conclusion :** Le fichier de configuration n'a **pas** été modifié pour atteindre 500 actions. `MAX_ACTIONS_TOTAL=200` était la valeur déployée. Le test a donc consommé 199/200 actions, non 500. L'intention déclarée dans le nom du log n'a **pas** été appliquée au code.

**Impact :** Le test "500 steps" n'a pas eu lieu. La lacune T-02 (budget) n'est pas résolue pour r11l.

---

## 2. Architecture de r11l — ACTION6 structurellement unique

### Source : `r11l.py` ligne 1440 (lu intégralement)

```python
# r11l.py — ligne 1440
super().__init__(
    game_id="r11l",
    levels=levels,
    camera=qkepbeghtwx,
    available_actions=[6]   # ← seule ACTION6 déclarée, hardcodée
)
```

### Source : lignes 1416–1419

```python
# Création de la liste d'inputs : grille 64×64 par pas de 4
for lugjhyvbpda in range(0, 64, 4):
    for fcuuuylahgr in range(0, 64, 4):
        rgktpamtctw = ActionInput(
            id=GameAction.ACTION6.value,
            data={"x": fcuuuylahgr, "y": lugjhyvbpda}
        )
        self.jtqexauuzid.append(rgktpamtctw)
```

**Signification :** ACTION6 dans r11l est un **clic coordonné** (x, y) dans une grille 64×64 (pas de 4px = 256 positions possibles). Ce n'est **pas** une action sans information : chaque appel à ACTION6 spécifie une position différente dans l'espace.

**Conséquence critique :** LuCY répétait ACTION6 sans varier les coordonnées (x, y). Le `raw_available_ids=[6]` est correct — il n'y a qu'une action — mais le contenu réel de l'action (les coordonnées) **varie**. LuCY ne sait pas quelle position (x, y) choisir.

### Mécanisme de victoire r11l (lignes 1758–1785)

```python
# r11l.py — lignes 1758–1785 (simplifié)
# Victoire : TOUS les sprites "roefwu-*" doivent collisionner avec leur cible
if qupcqlrzmz:   # True seulement si toutes les paires sprite↔cible collisionnent
    self.uyawyyswbya = True   # → next_level() → levels_completed++
```

Le jeu est un **puzzle de placement** : l'agent doit cliquer aux bonnes positions pour que des sprites mobiles atteignent leurs cibles. La victoire = toutes les paires collisionnent. Ce n'est **pas** un simple compteur de pixels — c'est une condition discrète par niveau.

**Implication pour la stratégie :** Répéter ACTION6 au hasard produit des changements visuels (+3 pixels/action observés) mais ne fait **jamais** converger vers la condition de victoire de façon systématique. L'agent a besoin de savoir **quelles coordonnées** rapprochent un sprite de sa cible.

---

## 3. FIX P1-D dans v12.1 — Présent mais insuffisant pour r11l

### Source : `my_agent_v121.py` lignes 51–53 + 96

```python
# Déclaration — ligne 96
SINGLE_ACTION_LOOP_THRESHOLD = 8  # consecutive same-fp with 1 candidate → RESET

# Commentaire d'implémentation (lignes 51–53) :
# APRÈS: same_state_streak counter: si fp unchanged pour SINGLE_ACTION_LOOP_THRESHOLD
#        consecutive steps ET only 1 candidate action, force RESET to break
#        the loop early and reallocate budget.
```

**Ce que FIX P1-D fait :** Si l'empreinte visuelle (`fp`) ne change pas pendant 8 actions consécutives **ET** qu'il n'y a qu'un candidat, LuCY force un `RESET`.

**Ce que FIX P1-D ne fait pas :** Dans r11l, ACTION6 **change toujours** l'état visuel (+3 pixels/action). La `fp` évolue à chaque appel → `same_state_streak` ne monte jamais à 8 → FIX P1-D ne se déclenche **jamais** pour r11l.

**Preuve dans le log :** `n_visual_change={"6": 165}` — 165 changements visuels sur 199 actions. L'empreinte changeait constamment, neutralisant le détecteur de boucle.

---

## 4. État des 5 lacunes après lecture du code source

| ID | Lacune | Statut post-L-042 | Source de vérification |
|----|--------|-------------------|------------------------|
| **T-01** | Condition de victoire | ⚠️ PARTIEL — sk48/tr87/sb26 formalisés (L-040) ; r11l = collision sprites (découvert L-042) ; 22 autres jeux INCONNUS | `r11l.py` lignes 1758–1785 |
| **T-02** | Budget d'actions | ❌ OUVERT — log "500steps" = réellement 200. MAX=200 confirmé dans le code. Test à 500 jamais effectué | `my_agent_v121.py` ligne 88 |
| **T-03** | Classification arcade | ❌ OUVERT — aucune classification par famille de mécaniques | — |
| **T-04** | Jeux à action unique | ⚠️ AVANCÉ — ACTION6 = clic coordonné (x,y), pas une action sans dimension. FIX P1-D inefficace pour r11l (fp change toujours). Stratégie de ciblage manquante | `r11l.py` lignes 1416–1419 |
| **T-05** | Copies de l'agent | ✅ FERMÉ (L-040) — `vendor/agent/my_agent.py` aligné sur `agent/my_agent_v121.py` | — |

---

## 5. Analyse de C-003 et C-004 (réponse à l'audit utilisateur)

### C-003 — Augmentation du budget (80 → 200)

**Avant :** `MAX_ACTIONS_TOTAL=80, MAX_ACTIONS_PER_LEVEL=30` (ligne 86, commentaire)  
**Après :** `MAX_ACTIONS_TOTAL=200, MAX_ACTIONS_PER_LEVEL=80` (ligne 88, valeur active)

**Verdict confirmé :** Modification réelle dans le code. Utile pour les jeux multi-niveaux. Non suffisante pour r11l car la stratégie de ciblage (x, y) est absente.

**Problème structurel :** `is_done()` (ligne 1117) déclenche `BUDGET_EXHAUSTED` à `action_count >= 199`. Pour tester avec 500 actions, il faudrait changer `MAX_ACTIONS_TOTAL = 500` **dans le code** avant lancement.

### C-004 — Diagnostic r11l : "3 pixels/action × 400 actions = victoire"

**Verdict :** Estimation invalide. La victoire dans r11l n'est **pas** liée au nombre de pixels modifiés — elle requiert que des sprites spécifiques atteignent des zones cibles précises. Le calcul "400 actions" repose sur une hypothèse incorrecte de progression linéaire via pixels.

**Réalité :** `qupcqlrzmz = True` (condition de victoire) exige que **toutes** les paires sprite↔cible soient simultanément en collision. C'est discret, non continu.

---

## 6. Avant / Après — Résumé des lignes clés modifiées ou analysées

| Fichier | Ligne | Avant | Après / Découverte |
|---------|-------|-------|--------------------|
| `my_agent_v121.py` | 86–87 | commentaire : MAX=80, PER_LEVEL=30 | valeurs historiques (archivées) |
| `my_agent_v121.py` | 88 | — | `MAX_ACTIONS_TOTAL = 200` (actif) |
| `my_agent_v121.py` | 89 | — | `MAX_ACTIONS_PER_LEVEL = 80` (actif) |
| `my_agent_v121.py` | 96 | — | `SINGLE_ACTION_LOOP_THRESHOLD = 8` (FIX P1-D) |
| `my_agent_v121.py` | 1117 | `>= MAX - 1` | `BUDGET_EXHAUSTED` à 199/200 ✅ cohérent |
| `r11l.py` | 1440 | — | `available_actions=[6]` — hardcodé, seule ACTION6 |
| `r11l.py` | 1416–1419 | — | ACTION6 = clic (x,y) dans grille 64×64 par pas de 4 |
| `r11l.py` | 1782–1785 | — | Victoire = `qupcqlrzmz=True` = toutes collisions sprites↔cibles |
| `r11l.py` | 1805–1811 | — | `step()` : game own budget `_max_actions=60` indépendant du budget LuCY |

**Note importante :** r11l a son propre `_max_actions = 60` (ligne 1407). Ce budget interne est **distinct** de `MAX_ACTIONS_TOTAL=200` de LuCY. Le budget jeu = 60 actions moteur internes ; le budget LuCY = 200 appels agent. Les deux s'appliquent indépendamment.

---

## 7. Plan d'action mis à jour

### P0 — Immédiat

**P0-1 : Tester r11l avec MAX_ACTIONS_TOTAL = 500**

```python
# Modification requise dans my_agent_v121.py — ligne 88
# AVANT :
MAX_ACTIONS_TOTAL = 200
# APRÈS :
MAX_ACTIONS_TOTAL = 500
```

Puis lancer le runner et vérifier dans le log :
- `"max_actions_total": 500` dans `GAME_INIT`
- Si `BUDGET_EXHAUSTED` à 499 → la stratégie est le problème, pas le budget
- Si `WIN` → noter l'action exacte qui déclenche la victoire

**P0-2 : Implémenter une stratégie de ciblage pour ACTION6**

r11l nécessite que LuCY choisisse les bonnes coordonnées (x, y). Les 256 positions possibles (grille 64×64 par pas de 4) doivent être explorées stratégiquement, pas au hasard. Stratégie minimale : balayage systématique de la grille 16×16 plutôt que répétition de la même position.

**P0-3 : Lire les positions des sprites dans le FrameData r11l**

Vérifier si le FrameData expose les positions des sprites mobiles (`bbijaigbknc`) et des cibles (`kacotwgjcyq`). Si oui, LuCY peut calculer la distance et choisir la position (x, y) qui rapproche le sprite de sa cible.

### P1 — Secondaire

**P1-1 : Fixer FIX P1-D pour les jeux où fp change toujours**

Ajouter une détection de "progression stagnante" : si `levels_completed` n'augmente pas après N actions malgré des changements visuels, déclencher un RESET ou une stratégie de diversification des coordonnées.

**P1-2 : Construire le contrat de victoire pour les 22 jeux restants**

Lire le code source de chaque jeu pour identifier la condition `win` (equivalents de `qupcqlrzmz`, `lgdrixfno>=35`, etc.). Sans ce contrat, LuCY ne peut pas mesurer sa progression réelle.

**P1-3 : Vérifier l'apprentissage transférable**

Après une première victoire sur r11l, réexécuter sur une variante pour tester si la stratégie de ciblage (x, y) est généralisée ou mémorisée.

---

## 8. Ce qui n'est PAS résolu dans ce rapport

- Le test à 500 actions n'a **pas** été lancé (hors scope de ce rapport — analyse seule)
- Les sources des jeux `tn36`, `vc33`, `s5i5`, `lp85`, `ft09` n'ont **pas** été lues
- La classification T-03 des familles de mécaniques reste entièrement ouverte
- Les 22 conditions de victoire restantes sont inconnues
- Aucune modification du code n'a été effectuée (conforme à la consigne de l'audit)

---

## 9. Conclusion

LuCY v12.1 ne résout pas r11l pour deux raisons structurelles indépendantes du budget :

1. **Absence de stratégie de ciblage** : ACTION6 exige des coordonnées (x, y) précises. LuCY choisit les coordonnées sans connaissance de la position des sprites ni de leurs cibles.

2. **FIX P1-D inefficace pour r11l** : le détecteur de boucle ne se déclenche pas car l'empreinte visuelle change constamment (+3 pixels/action), masquant l'absence de progression vers la victoire.

Augmenter le budget à 500 est nécessaire pour valider si la victoire est seulement une question d'exploration temporelle, mais n'est pas suffisant sans une stratégie de ciblage. La priorité P0 doit donc combiner les deux : MAX_ACTIONS=500 **ET** exploration systématique des positions (x, y).

---

*Rapport L-042 produit dans `LuCY/rapports/` — conforme PROTOCOLE ARTCB*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
