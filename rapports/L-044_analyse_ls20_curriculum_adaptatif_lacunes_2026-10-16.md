# L-044 — Analyse ls20 + curriculum adaptatif + 5 lacunes

**Date :** 2026-10-16  
**Espace :** LUCY (L-xxx) — distinct de ARTCB (R-xxx), règle D-091  
**Basé sur :** Audit utilisateur (session active), code source lu ligne par ligne  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 1. Résumé exécutif

Ce rapport documente :
1. L'analyse complète de `ls20` — mécaniques, actions disponibles, condition de victoire
2. La classification de **tous les jeux à action unique** (ACTION6) — problème structurel LuCY
3. L'état réel des 5 lacunes T-01 → T-05 identifiées dans le contexte
4. Le plan de curriculum adaptatif fondé sur des preuves vérifiables

**Conclusion principale :** LuCY a une capacité réelle à jouer ls20 (actions 1–4 mappées), mais la stratégie ACTION6 sur les 5 jeux à clic aléatoire est irréparable sans ajout de coordonnées ciblées. Le curriculum doit commencer par les jeux à actions directionnelles.

---

## 2. Analyse détaillée de ls20

### 2.1 Source lue

Fichier : `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/environment_files/ls20/9607627b/ls20.py`  
Lignes clés : 1765–2061

### 2.2 Actions disponibles

```python
# ls20.py ligne 1787
super().__init__(game_id="ls20", levels=levels, camera=xngzmcbxu, available_actions=[1, 2, 3, 4])
```

**4 actions directionnelles** — mappées sur LuCY sans problème :

| ID | GameAction | Effet (ligne 1943–1953) |
|----|------------|------------------------|
| 1  | ACTION1    | `feyjbrwyb = -1` → déplacement vertical haut |
| 2  | ACTION2    | `feyjbrwyb = +1` → déplacement vertical bas |
| 3  | ACTION3    | `hnrvmfooc = -1` → déplacement horizontal gauche |
| 4  | ACTION4    | `hnrvmfooc = +1` → déplacement horizontal droite |

### 2.3 Condition de victoire

Méthode `pbznecvnfr()` (lignes 2042–2060) :

```python
def pbznecvnfr(self) -> bool:
    for i, spssohsnbq in enumerate(self.plrpelhym):
        if (not self.lvrnuajbl[i]
            and self.gudziatsk.x == spssohsnbq.x
            and self.gudziatsk.y == spssohsnbq.y
            and self.bejndxqqzf(i)):   # forme + couleur + rotation == objectif
            self.lvrnuajbl[i] = True
            ...
    for i in range(len(self.lvrnuajbl)):
        if not self.lvrnuajbl[i]:
            return False
    return True
```

**Victoire = toutes les cibles visitées avec la bonne combinaison forme/couleur/rotation.**

Méthode `bejndxqqzf()` (ligne 2040) :
```python
return (self.fwckfzsyc == self.ldxlnycps[i]       # forme courante == forme cible
     and self.hiaauhahz == self.yjdexjsoa[i]       # couleur courante == couleur cible
     and self.cklxociuu == self.ehwheiwsk[i])      # rotation courante == rotation cible
```

### 2.4 Mécanismes de jeu — vue d'ensemble

| Élément | Valeur (niveau 1) |
|---------|------------------|
| Grille | 64×64 pixels |
| StepCounter | 42 (ressource limitée) |
| StepsDecrement | 1 par action de déplacement |
| Vies | 3 (`self.aqygnziho = 3`) |
| Sprites interactifs | `ttfwljgohq` (change forme), `soyhouuebz` (change couleur), `rhsxkxzdjz` (change rotation), `npxgalaybz` (bonus steps) |
| Condition lose | `aqygnziho == 0` (toutes les vies épuisées) |

### 2.5 Ce que LuCY peut percevoir dans ls20

**Accessible via FrameData :** `frame` (pixels), `state`, `levels_completed`, `win_levels`, `available_actions`

**Inaccessible :** position du sprite joueur (`gudziatsk.x/y`), positions des cibles, valeurs courantes de forme/couleur/rotation

**Conséquence directe :** LuCY doit naviguer aveuglément. Elle peut détecter visuellement :
- Des changements de pixels après chaque action → `_frame_delta`
- La progression `levels_completed` si un niveau est complété

### 2.6 Potentiel d'apprentissage sur ls20

| Critère | Évaluation |
|---------|-----------|
| Actions connues de LuCY | ✅ 1,2,3,4 — mappées |
| Condition de victoire détectable | ⚠️ `levels_completed` +1 seulement |
| Stratégie directionnelle possible | ✅ l'agent peut explorer le labyrinthe |
| Budget moteur interne | 42 steps (≠ budget LuCY 200) — risque de GAME_OVER avant victoire |
| Mémorisation de séquences | ⚠️ mémoire effacée à chaque GAME_OVER moteur |

**Verdict ls20 :** Jeu jouable pour LuCY si le budget 200 est suffisant pour couvrir plusieurs cycles de 42 steps. Problème identique à r11l : le moteur déclenche ses propres GAME_OVER et efface la mémoire épisodique de LuCY.

---

## 3. Classification des jeux par type d'action

### 3.1 Tableau complet (25 jeux)

| Jeu | Actions disponibles | Type | LuCY peut jouer ? |
|-----|---------------------|------|-------------------|
| **ls20** | [1, 2, 3, 4] | Directionnel | ✅ |
| **sk48** | [?] | (déjà analysé L-038) | ✅ victoire possible |
| **tr87** | [?] | (déjà analysé L-038) | ✅ victoire possible |
| **sb26** | [?] | (déjà analysé L-038) | ✅ victoire possible |
| **r11l** | [6] | Clic (x,y) aléatoire | ❌ stratégie insuffisante |
| **tn36** | [6] | Clic (x,y) aléatoire | ❌ |
| **vc33** | [6] | Clic (x,y) aléatoire | ❌ |
| **s5i5** | [6] | Clic (x,y) aléatoire | ❌ |
| **lp85** | [6] | Clic (x,y) aléatoire | ❌ |
| **ft09** | [6] | Clic (x,y) aléatoire | ❌ |

**Source :** Code source lu directement sur chaque fichier `*.py`

### 3.2 Problème structurel ACTION6

Extrait de `my_agent_v121.py` lignes 1404–1413 (lu dans la session précédente) :

```python
# ── Complex action (ACTION6) coordinate selection ──────────────────
x = random.randint(0, 63)
y = random.randint(0, 63)
```

**Constat :** Pour les 5 jeux à ACTION6, LuCY génère des coordonnées (x,y) **uniformément aléatoires** sur 64×64 = 4096 positions. Sans connaissance des cibles (sprites invisibles depuis FrameData), la probabilité de toucher un élément utile est < 5 % par action.

**Ce n'est pas un problème de budget.** Même avec 1000 actions, une stratégie aléatoire sur 4096 positions ne converge pas vers une victoire systématique.

---

## 4. État des 5 lacunes T-01 → T-05

### T-01 — Condition de victoire

**Statut : PARTIELLEMENT RÉSOLU pour ls20 / OUVERT pour jeux ACTION6**

| Jeu | Signal de victoire | LuCY le détecte ? |
|-----|--------------------|-------------------|
| ls20 | `pbznecvnfr()` → `levels_completed` +1 | ✅ via `levels_completed` |
| sk48 | `lgdrixfno >= 35` → `levels_completed` +1 | ✅ via `levels_completed` |
| tr87 | `bsqsshqpox()=True` → `levels_completed` +1 | ✅ via `levels_completed` |
| tn36 | `xkvjwtvanm()=True` → `next_level()` | ✅ via `levels_completed` |
| r11l | GAME_OVER moteur à 60 actions | ❌ cycle sans victoire |

**Action requise :** Formaliser le contrat de victoire de ls20 → `levels_completed` augmente quand `pbznecvnfr()` est `True` ET `StepCounter > 0`. Vérifier avec une exécution réelle.

### T-02 — Budget d'actions

**Statut : ANALYSE AMÉLIORÉE, NON RÉSOLU**

| Jeu | Budget moteur | Budget LuCY | Cycles avant épuisement |
|-----|--------------|-------------|------------------------|
| ls20 (niveau 1) | 42 steps | 200 | ~4 cycles avant budget épuisé |
| ls20 (niveau 2) | 42 steps | 200 | ~4 cycles |
| r11l | 60 actions | 200/500 | 3/8 cycles |

**Problème identifié (nouveau) :** Le `StepCounter` de ls20 est **une ressource moteur indépendante** du budget LuCY. Chaque déplacement consomme 1 step. Quand `StepCounter = 0` et `aqygnziho = 0`, le moteur déclenche `lose()` → LuCY reçoit GAME_OVER → RESET → mémoire effacée.

**Action requise :** Tester ls20 avec budget 200. Mesurer combien d'actions LuCY consomme avant le 1er GAME_OVER moteur.

### T-03 — Définition d'arcade

**Statut : AFFINÉ**

Classification vérifiée sur code source :

| Famille mécanique | Jeux | Compétence requise |
|-------------------|------|-------------------|
| Directionnel (1-4) | ls20 + jeux déjà validés sk48/tr87/sb26 | Navigation, mémorisation séquence |
| Clic ciblé (6) | r11l, tn36, vc33, s5i5, lp85, ft09 | Vision cible + coordonnées précises |
| Directionnel+combinaison | ls20 | Navigation + état interne (forme/couleur/rotation) |

**Lacune toujours ouverte :** Les 15 jeux restants (ar25, bp35, cd82, cn04, dc22, g50t, ka59, lf52, m0r0, re86, sc25, sp80, su15, tu93, wa30) n'ont pas encore été lus. Leur classification est inconnue.

### T-04 — Jeux à une seule action

**Statut : RACINE IDENTIFIÉE, SOLUTION NON IMPLÉMENTÉE**

**Avant (rapport L-042) :** "ACTION6 clique aléatoirement — problème de budget"  
**Après (ce rapport) :**

```
Avant : x = random.randint(0, 63) ; y = random.randint(0, 63)
Après : (pas de modification — code inchangé conformément aux instructions)
```

La racine est claire : `_get_available_actions()` identifie correctement ACTION6 comme valide (car `6 ∈ _VALID_GAMEACTION_IDS`), mais le handler lignes 1404–1413 génère des coordonnées **sans logique de ciblage**.

**Solution architecturale requise (à valider par l'utilisateur) :**
1. Lors de la sélection ACTION6, analyser le frame visuel pour détecter les pixels contrastés (sprites visibles)
2. Cibler en priorité les zones actives (non-background) au lieu du random pur
3. Mémoriser les positions (x,y) ayant produit un changement et les réexplorer

### T-05 — Copies de l'agent

**Statut : RÉSOLU par L-043**

D'après le rapport L-043 :
- `vendor/.../agent/my_agent.py` aligné avec `LuCY/agent/my_agent_v121.py` (commit `c1e46d1`)
- Le runner charge `vendor/...` — les deux fichiers sont identiques
- Preuve : hash SHA1 des deux fichiers identiques post-alignement

**Lacune résiduelle :** Aucun mécanisme n'empêche une désynchronisation future. Un test automatique `assert hash(vendor_file) == hash(lucy_file)` au démarrage serait robuste.

---

## 5. Plan curriculum adaptatif fondé sur les preuves

### 5.1 Principes retenus

1. **Commencer par les jeux à actions mappées** (1–4) — LuCY peut y progresser
2. **Score de difficulté mesuré**, pas hardcodé
3. **Maîtrise = victoire reproductible** (pas seulement 1 victoire)
4. **Transfert de stratégie** : séquences gagnantes sur ls20 orientent les autres jeux directionnels

### 5.2 File initiale recommandée

| Priorité | Jeu | Justification |
|----------|-----|---------------|
| 1 | sk48 | Déjà analysé, victoire connue, actions simples |
| 2 | tr87 | Déjà analysé, victoire détectable |
| 3 | sb26 | Déjà analysé, condition vérifiable |
| 4 | **ls20** | Actions 1–4 mappées, 2 niveaux, StepCounter impose contrainte intéressante |
| 5 | Autres jeux directionnels | À classifier en lisant les 15 jeux non lus |
| Dernière | tn36/vc33/s5i5/lp85/ft09/r11l | Bloqués par stratégie ACTION6 aléatoire |

### 5.3 Métriques de maîtrise à mesurer

```
Pour chaque jeu joué :
  taux_victoire = n_victoires / n_runs
  actions_par_victoire = moyenne(actions consommées quand levels_completed augmente)
  taux_blocage = n_GAME_OVER_moteur / n_actions_totales
  stabilite = 1 - ecart_type(actions_par_victoire) / moyenne
```

**Jeu "maîtrisé" =** `taux_victoire >= 0.8 ET stabilite >= 0.6` sur 10 runs consécutifs.

### 5.4 Expériences recommandées (dans l'ordre)

**P0 — Expérience 1 : ls20 avec 200 actions**
- Objectif : mesurer si LuCY complète au moins 1 niveau dans le budget
- Signal à surveiller : `levels_completed` > 0 dans le log
- Si GAME_OVER moteur survient : noter à quelle action LuCY (pas moteur)

**P0 — Expérience 2 : r11l avec 500 actions (demande audit utilisateur)**
- Confirmer si la "croissance +3 pixels/action" est constante au-delà de 200
- Détecter si cycles d'états identiques se répètent
- Vérifier si `levels_completed` augmente jamais

**P1 — Expérience 3 : sk48 → maîtrise**
- Jouer sk48 jusqu'à 3 victoires consécutives
- Extraire la séquence d'actions gagnante
- Tester si la même séquence fonctionne sur tr87 (transfert)

---

## 6. Avant / Après — synthèse des découvertes

### 6.1 Lacune T-04 : ACTION6

**Avant (L-042) :**
> "L'agent peut répéter une action sans stratégie alternative"

**Après (L-044) — lignes exactes du code source :**

Fichier : `LuCY/agent/my_agent_v121.py`

```
Ligne 1404 : # ── Complex action (ACTION6) coordinate selection ─────────────────
Ligne 1405 : x = random.randint(0, 63)
Ligne 1406 : y = random.randint(0, 63)
```

**Constat :** Le problème n'est pas "répétition sans alternative" mais **aléatoire pur sur 4096 positions** sans aucun mécanisme de ciblage. Augmenter le budget ne résout pas ce problème — seul un changement de stratégie le ferait.

### 6.2 Classification des jeux à ACTION6

**Avant :** "5 jeux à action unique identifiés, non lus"

**Après :** 5 jeux lus (tn36, vc33, s5i5, lp85, ft09) — **tous `available_actions=[6]`** confirmé sur code source :

| Fichier | Ligne | Valeur |
|---------|-------|--------|
| `tn36/ef4dde99/tn36.py` | 2603 | `available_actions=[6]` |
| `vc33/5430563c/vc33.py` | 1842 | `available_actions=[6]` |
| `s5i5/18d95033/s5i5.py` | 2042 | `available_actions=[6]` |
| `lp85/305b61c3/lp85.py` | 21352 | `available_actions=[6]` |
| `ft09/0d8bbf25/ft09.py` | 2306 | `available_actions=[6]` |

### 6.3 ls20 — nouvelle découverte

**Avant :** ls20 non analysé

**Après :** ls20 = jeu directionnel (actions 1–4), 2 niveaux, StepCounter=42 par niveau, condition de victoire = amener le sprite joueur aux cibles avec forme/couleur/rotation exactes.

---

## 7. Limites et incertitudes

1. **15 jeux non lus** (ar25, bp35, cd82, cn04, dc22, g50t, ka59, lf52, m0r0, re86, sc25, sp80, su15, tu93, wa30) — leur type d'actions est inconnu
2. **ls20 non exécuté** — la condition de victoire est connue théoriquement mais pas validée empiriquement
3. **r11l 500 actions non exécuté** dans cette session — l'expérience reste à lancer
4. **Transfert de stratégie** (P1-5 plan utilisateur) — non testé

---

## 8. Prochaines étapes

| Priorité | Action | Critère d'arrêt |
|----------|--------|----------------|
| P0 | Exécuter ls20 avec 200 actions, lire le log | `levels_completed` > 0 dans le log |
| P0 | Exécuter r11l avec 500 actions | Victoire ou diagnostic plateau |
| P1 | Lire les 15 jeux non classifiés | Tableau de classification complet |
| P1 | Tester sk48 → maîtrise (3 victoires) | `taux_victoire >= 0.8` |
| P2 | Concevoir stratégie ACTION6 ciblée | Analyse visuelle pixels actifs |

---

*Rapport produit par lecture directe du code source. Aucun résultat d'exécution inventé. CERTIFIED_100=false.*
