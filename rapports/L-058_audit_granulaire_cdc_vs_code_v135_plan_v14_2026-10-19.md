# L-058 — Audit Granulaire : CDC Lucy §1–§21 vs Code v13.5 + Plan v14.x

**Date :** 2026-10-19  
**Auteur :** Agent Bob IDE (mode DEBUG actif)  
**Version code analysé :** LuCY v13.5 — `my_agent_v135.py` (2616 lignes)  
**Commit analysé :** `0baaa84` (HEAD au moment de l'audit)  
**Score Kaggle de référence :** 0.14 (v7.0) | Score v13.5 : 0.00 (mode commit, dummy)  
**Soumission en cours :** competition rerun v13.5 (~1h, en attente de résultats)  
**CDC de référence :** Cahier des charges Lucy (79 pages, octobre 2026, @Donnet)  
**Espace de numérotation :** LUCY (`LuCY/rapports/L-NNN_*`) — NE PAS croiser avec ARTCB  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## Sommaire

1. [Méthode d'audit](#1-méthode)
2. [État de la soumission Kaggle v13.5](#2-état-kaggle)
3. [Divergences CDC §1–§21 vs code actuel](#3-divergences-cdc)
4. [Failles code exhaustives (F-001→F-022)](#4-failles-code)
5. [Analyse comparative des forces](#5-forces)
6. [Plan de correction v14.x priorisé](#6-plan-v14)
7. [Tableau de synthèse avant/après](#7-avant-après)
8. [Éléments oubliés à préciser](#8-oublis-à-préciser)

---

## 1. Méthode

**Sources exploitées :**
- `LuCY/agent/my_agent_v135.py` — lu intégralement, ligne 1 à 2616
- `LuCY/rapports/L-056` à `L-057` — lus intégralement
- `LuCY/logs/kaggle_v135_raw.log` — 51 lignes, analysées
- `LuCY/logs/lucy_L054_v135_*.json`, `L055_*.json`, `L056_*.json`, `L057_*.json` — lus
- Cahier des charges Lucy (79 pages) — fourni dans le prompt, analysé section par section (§1–§21)
- URL Kaggle v13.5 `scriptVersionId=360153422` — HTML récupéré non exploitable directement ; informations obtenues depuis les logs L-055/L-057 qui contiennent le kernel_id et les métadonnées de soumission

**Périmètre :** Audit de conformité CDC↔code + identification de toutes les failles techniques.  
**Ce rapport ne modifie aucun code.** Il produit uniquement le plan.

---

## 2. État de la soumission Kaggle v13.5

| Indicateur | Valeur |
|---|---|
| Kernel ID | `ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place` |
| Version notebook soumis | 13.5 (cellule writefile vérifiée) |
| Score public v13.5 | **0.00** (mode commit = dummy parquet 1 ligne) |
| Score public v7.0 (référence) | **0.14** |
| Competition rerun v13.5 | **en cours (~1h, résultats indisponibles au moment de l'audit)** |
| Tests locaux | **355/355 PASS** (commit `0baaa84`) |
| `is_private` | **false** ✅ (corrigé L-057) |
| Notebook soumis correct ? | ✅ `submission.ipynb` — 5 cellules, `%%writefile my_agent.py` + `KAGGLE_IS_COMPETITION_RERUN` gate |
| Diff code local vs Kaggle | **vide** — fichiers identiques ✅ |

**⚠️ NOTE CRITIQUE** : Le score 0.00 de la soumission #57273062 est dû au mode commit Kaggle (dummy parquet), **pas à un bug du code**. Le vrai score sera visible après le competition rerun en cours. Les logs du rerun ne sont **pas encore disponibles** — ce rapport est produit avant leur obtention, conformément à la demande. Lire les logs du rerun et produire L-059 dès leur disponibilité.

---

## 3. Divergences CDC §1–§21 vs code actuel

### §1.1 — Objectif : ARC-AGI-3 comme mesure de référence, 100% cible

**CDC :** *"ARC-AGI-3 est la mesure de référence de Lucy : un modèle abouti doit y atteindre 100%."*

**Code actuel :**
- Architecture orientée ARC-AGI-3 ✅ (game loop, GameAction, FrameData)
- Score actuel = 0.14 (v7.0) — très loin de 100%
- Aucun mécanisme d'apprentissage des poids — la performance ne peut pas croître avec l'expérience

**Statut : DIVERGENCE MAJEURE** — La cible CDC est 100% par apprentissage ; le code actuel est un agent heuristique pur dont la performance est plafonnée par la richesse des règles écrites à la main.

---

### §1.3 — Ce que Lucy ne doit pas devenir

**CDC :** *"Pas un ensemble d'heuristiques codées uniquement pour gagner à un benchmark."*

**Code actuel :**
- `_classify_frame()` : classification par **rareté** des couleurs — heuristique pure, non apprise
- `_pick_cluster_centre()` : centroïde du groupe BFS le plus grand — heuristique géométrique
- `GUARD-DISTINCT`, `GUARD-FLOOR-COVERAGE` : guards manuels ajoutés cas par cas
- `_CognitiveEngine.score_all()` : scoring par compteur d'événements, pas par apprentissage

**Statut : DIVERGENCE PARTIELLE** — L'architecture n'est pas un wrapper LLM (✅) ni un pipeline fixe (✅) mais elle est construite sur des heuristiques manuelles, ce que le CDC interdit explicitement au §1.3 pour un système final. Acceptable pour un MVP de compétition, mais incompatible avec la vision CDC à terme.

---

### §2 — Principes de conception P1–P12

| Principe CDC | Présent ? | Commentaire |
|---|---|---|
| **P1** Modèle global unique | ⚠️ PARTIEL | Un seul fichier Python, mais pas de "state sérialisable global" au sens CDC (pas de poids partagés entre tâches) |
| **P2** Spécialisation effective | ⚠️ PARTIEL | 4 modules distincts mais objectifs non formellement définis ni mesurés |
| **P3** Routage adaptatif | ✅ | Phase explore/exploit/recover avec signaux level_up et stuck_streak |
| **P4** Métacontrôleur route le calcul | ⚠️ APPROXIMÉ | `choose_action()` joue le rôle de métacontrôleur mais lit le contenu des frames directement (violation §7.8) |
| **P5** Déterminisme reproductible | ❌ | `random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))` — graine temporelle non sérialisable, non reproductible bit-à-bit |
| **P6** Mesurabilité | ✅ | `_KaggleForensicLogger` v2 — traces complètes nanoseconde |
| **P7** Budget borné | ✅ | `MAX_ACTIONS_TOTAL=500`, `MAX_ACTIONS_PER_LEVEL=80` |
| **P8** Apprentissage attribuable | ❌ | Pas d'apprentissage de poids — `_n_progress_real` est un compteur d'actions, pas un signal d'apprentissage attribué |
| **P9** Apprentissage relationnel | ❌ | `_RuleMemory` stocke des associations features→action mais sans généralisation relationnelle ni schémas |
| **P10** Multimodalité partagée | N/A | ARC-AGI-3 = grilles uniquement ; architecture prête pour extension |
| **P11** Complexité justifiée | ⚠️ PARTIEL | BFS, centroïde, guards — ajoutés itérativement mais pas systématiquement testés contre baselines simplifiées |
| **P12** Système clos | ✅ | Pas d'appel LLM externe, pas de modèle pré-entraîné |

---

### §3 — Définition du succès : 10 tests reproductibles

**CDC :** Tests reproductibles sur 10 critères (rôles distincts, routage adaptatif vs hasard, hubs sans absorber calcul, budget respecté, connexions utiles, attribution signaux, réutilisation schémas, amélioration vitesse/précision, confiance calibrée, reproductibilité).

**Code actuel :**
- Tests 355/355 PASS ✅ — mais ils testent des propriétés du **code actuel**, pas les 10 critères CDC
- Critère 1 (rôles distincts) : testable mais non testé explicitement
- Critère 2 (routage vs hasard) : **non testé** — pas de baseline aléatoire comparée
- Critère 6 (attribution) : **absent** — pas d'attribution par Shapley ni méthode équivalente
- Critère 7 (réutilisation schémas) : **absent** — `_RuleMemory` ne construit pas de schémas réutilisables au sens CDC
- Critère 9 (confiance calibrée) : **non calibrée** — `confidence = n_changed/9.0` (heuristique non validée Brier/ECE)

**Statut : DIVERGENCE MAJEURE** — 6/10 critères de succès non satisfaits.

---

### §4 — Architecture générale : 3 niveaux, 4 hubs, métacontrôleur

**CDC :** Trois niveaux — niveau fonctionnel (8 fonctions), niveau hubs (4 hubs Pi/Pe/Di/De), niveau métacognitif (métacontrôleur).

**Code actuel :**
- Niveau fonctionnel → partiellement couvert par 4 modules : `_GridPerceptor` (≈Se), `_EpisodicMemory` (≈Si), `_RuleMemory` (≈Ti partiel), `_CognitiveEngine` (≈Te partiel)
- **Absent : Ne (génération), Ni (compression), Fi (contraintes dures), Fe (intention tâche)**
- Niveau hubs → **absent** — aucune structure de hub Pi/Pe/Di/De
- Métacontrôleur → **simulé** par `choose_action()` mais lit le contenu des frames (violation P4/§7.8)

**Cartographie modules → fonctions CDC :**

| Module v13.5 | Fonction(s) CDC couverte(s) | Fonctions CDC absentes |
|---|---|---|
| `_GridPerceptor` | Se (partiel — extraction couleurs) | Se complet (segmentation, objets, prédiction) |
| `_EpisodicMemory` | Si (partiel — compteurs actions) | Si complet (rappel contextuel, épisodes structurés) |
| `_RuleMemory` | Ti (partiel — règles feature→action) | Ni absent, Ti limité |
| `_CognitiveEngine` | Te (scoring actions candidates) | Te complet (planification, coûts) |
| `_GoalDeltaTracker` | Te (signal delta goal) | — |
| `_SelectPlaceFSM` | Te (exécution SELECT→PLACE) | — |
| **ABSENT** | **Ne, Ni, Fi, Fe** | **4 fonctions sur 8 absentes** |

**Statut : DIVERGENCE STRUCTURELLE MAJEURE** — Architecture 3 niveaux CDC non implémentée.

---

### §5 — Les 8 fonctions cognitives

**Se — Perception du présent**
- CDC : segmentation objets, détection changements, prédiction prochaine observation
- Code : `_GridPerceptor.extract()` → compteur couleurs + variance + densité changements
- **FAILLE F-001** : `_GridPerceptor._to_grid()` ne transpose pas le format columnar ARC-AGI-3 (voir §4 — divergence avec `_SelectPlaceFSM._to_int_grid()`)
- **FAILLE F-002** : Aucune segmentation d'objets — perception réduite à distributions de couleurs

**Si — Mémoire épisodique**
- CDC : rappel épisodes pertinents, distinction ressemblances utiles vs surface, épisodes structurés
- Code : `_EpisodicMemory` — dict `{fp: {action: count, level_up: bool, delta: float}}`
- **FAILLE F-003** : Mémoire non persistante entre parties/tâches — tout repart à zéro par jeu

**Ne — Génération de possibilités**
- CDC : hypothèses alternatives, recombinaison, analogies
- Code : **ABSENT**
- **FAILLE F-004** : La phase `explore` = `random.choice(unseen)` — aléatoire pur, pas de génération d'hypothèses

**Ni — Compression relationnelle**
- CDC : schémas abstraits, structures sous-jacentes, évolution modèles
- Code : **ABSENT**
- **FAILLE F-005** : Aucune extraction de schémas ou patterns inter-niveaux

**Ti — Cohérence interne**
- CDC : vérification modèles internes, détection contradictions, règles minimales
- Code : `_RuleMemory._classify()` → classification GROWING/SHRINKING/STABLE
- **FAILLE F-006** : `_RuleMemory._classify()` retourne GROWING si `level_up=True` indépendamment de la structure réelle du changement de frame — classification non structurelle (documentée dans L-054)

**Te — Efficacité externe**
- CDC : planification, sélection actions par conséquences observables, stratégie adaptative
- Code : `_CognitiveEngine.score_all()` + `_SelectPlaceFSM` + `_GoalDeltaTracker`
- Couverture : BONNE — c'est le module le plus développé
- **FAILLE F-007** : `_CognitiveEngine.score_all()` lit directement les features perceptives → violation §7.8 (métacontrôleur ne doit pas lire le contenu des slots)

**Fi — Contraintes invariantes**
- CDC : contraintes dures toujours actives (action valide, pas de répétition stérile, budget, honnêteté, irréversibilité)
- Code : PARTIEL — `Fi contrainte 1 (action valide)` ✅ via `_get_available_actions()` ; `Fi contrainte 3 (budget)` ✅ via `MAX_ACTIONS_TOTAL` ; `Fi contrainte 2 (pas de répétition)` ⚠️ via SINGLE_ACTION_LOOP_THRESHOLD (seuil 8, pas symbolique)
- **FAILLE F-008** : Contraintes Fi 4 (honnêteté), 5 (intégrité mémoire), 6 (irréversibilité) absentes

**Fe — Modélisation intention tâche**
- CDC : interpréter l'intention opérationnelle, critères implicites, ambiguïtés
- Code : **ABSENT**
- **FAILLE F-009** : `_goal_tracker.goal_found=False` sur tous les 25 jeux ARC-AGI-3 locaux (confirmé L-032/L-054) — pas d'interprétation de l'objectif de tâche

---

### §7 — Métacontrôleur

**CDC §7.2 — Signaux [0,1] :** surprise, incertitude, conflit, progrès, coût, budget restant

**Code actuel :**
- `stuck_streak` → approxime la stagnation ✅
- `level_up` → approxime le progrès ✅
- `n_progress_real / n_total` → approxime le taux de succès par action ✅
- `visual_delta` → approxime la surprise ⚠️ (pas normalisé [0,1])
- **Absence totale :** incertitude, conflit, testabilité, nouveauté au sens CDC

**CDC §7.8 — Le métacontrôleur ne juge pas le contenu :**
- **FAILLE F-010** : `_CognitiveEngine.score_all(features=features, ...)` — le "métacontrôleur" reçoit et exploite directement les features perceptives (`n_active`, `unique_colours`, etc.), violant la règle d'entrée bornée sur signaux numériques seulement

**CDC §7.5 — P5 Déterminisme :**
- **FAILLE F-011** : `random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))` — graine temporelle → résultats non reproductibles bit-à-bit entre deux runs identiques

---

### §8 — Espace de travail partagé

**CDC :** Slots avec parties vectorielle + structurée, zones publique/privée/échange, accès par attention.

**Code actuel :**
- Aucun espace de travail à slots — le frame numpy est passé directement entre modules
- `_EpisodicMemory` et `_RuleMemory` sont des dicts Python sans structure slot CDC
- **FAILLE F-012** : Pas de séparation zone publique / privée / échange → tous les modules ont accès direct à tous les états

---

### §9 — Mémoire à long terme et apprentissage relationnel

**CDC :** 4 couches — épisodique, schémas relationnels, procédurale, relations entre concepts. Persistance inter-tâches.

**Code actuel :**
- `_EpisodicMemory` → mémoire épisodique **très partielle** (compteurs par empreinte frame, pas d'épisodes structurés)
- `_RuleMemory` → approximation de la couche procédurale
- **FAILLE F-003 (déjà citée)** : aucune persistance inter-parties
- **FAILLE F-013** : Aucune mémoire relationnelle ni mémoire de schémas au sens CDC

---

### §11 — Attribution du crédit

**CDC §11.3 :** Valeurs de Shapley, rejeu d'épisodes pendant le sommeil, attribution par fonction.

**Code actuel :**
- Aucun mécanisme d'apprentissage de poids
- `_n_progress_real` = compteur d'actions qui ont causé un level_up → proxy rudimentaire d'attribution
- **FAILLE F-014** : Pas d'attribution par Shapley ni équivalent — impossible de déterminer quelle partie du code a contribué à un level_up

---

### §12 — Entraînement (phases 0→E)

**CDC :** 6 phases, poids ne changent que pendant le "sommeil", PyTorch pour les parties apprises.

**Code actuel :**
- **Phase 0 (encodeurs)** : encodeur = extraction couleurs en numpy, non entraîné
- **Phase A–D** : absentes — aucun entraînement de poids
- **FAILLE F-015** : L'agent ne peut pas apprendre entre les parties — ses performances sont plafonnées par les heuristiques initiales

---

### §13 — Sommeil et consolidation

**CDC :** Consolidation hors ligne, recombinaison d'épisodes éloignés, mise à jour des poids.

**Code actuel :**
- **ABSENT** — aucun mécanisme de consolidation hors ligne
- **FAILLE F-016** : Sans sommeil, les schémas appris dans une partie ne peuvent pas être raffinés ni généralisés

---

### §14 — Calibration de confiance

**CDC :** Score de Brier, ECE, confiance calibrée [0,1] mesurée expérimentalement.

**Code actuel :**
- `_is_confirmed_selection()` retourne `(bool, confidence)` où `confidence = n_changed/9.0`
- **FAILLE F-017** : Confiance non calibrée — `n_changed/9.0` est une heuristique sans validation Brier/ECE

---

### §16 — Dimensionnement V1

**CDC :** ~1 milliard de paramètres, 32 Go RAM, SSD 2 To, GPU 24 Go pour entraînement.

**Code actuel :**
- Agent pur Python, aucun paramètre neuronal
- **FAILLE F-018** : Aucune structure de poids — agent non dimensionnable selon le CDC V1

---

### §17 — Traçabilité

**CDC §17.1 :** Journal forensic append-only, chemin `logs/forensic/lucy_forensic.jsonl`.

**Code actuel :**
- `_KaggleForensicLogger` v2 ✅ — traces nanoseconde, GAME_INIT/FRAME_INVENTORY/ACTION_BEFORE/ACTION_AFTER/GAME_DONE
- Chemin : `logs/forensic/` ✅ (répertoire existant dans l'arborescence LuCY)
- **FAILLE F-019** : Le logger Kaggle écrit dans stdout (print) → non persist en compétition rerun ; le fichier `.jsonl` n'est accessible qu'en mode local

**CDC §17.2 — Déterminisme :**
- **FAILLE F-011 (déjà citée)** : graine temporelle

---

### §18 — Évaluation et hypothèses H1–H16

**CDC §18.3 — H1 :** Le routage adaptatif apporte un gain vs routage aléatoire.

**Code actuel :**
- Phases explore/exploit/recover = routage adaptatif ✅
- **FAILLE F-020** : H1 n'a jamais été testée formellement contre une baseline aléatoire (10 graines × jeux d'évaluation, protocole §18.5 non appliqué)

---

### §19 — Ordre d'implémentation (étapes 1–15)

| Étape CDC | Implémenté ? |
|---|---|
| 1. Banc local + baseline aléatoire | ⚠️ PARTIEL — 355 tests mais pas de baseline aléatoire formelle |
| 2. État partagé, encodeur texte, espace travail 3 zones, 4 hubs, 8 fonctions | ❌ Non — 4 modules, pas 8 fonctions ni 4 hubs CDC |
| 3. Métacontrôleur : budget, allocations, entrée bornée | ⚠️ PARTIEL — budget ✅, allocations ⚠️, entrée bornée ❌ |
| 4. Routage adaptatif | ✅ (phases explore/exploit/recover) |
| 5. Connexions inter-hubs | ❌ — aucun hub CDC |
| 6. Répartition récompense par traces | ❌ — `_n_progress_real` est un proxy, pas une attribution |
| 7–15 | ❌ Non |

**Score étapes CDC satisfaites : 2/15** (étape 4 complète, étapes 1+3 partielles)

---

## 4. Failles code exhaustives (F-001 → F-022)

| ID | Fichier | Lignes | Gravité | Description | Avant | Après recommandé |
|---|---|---|---|---|---|---|
| **F-001** | `my_agent_v135.py` | 1859–1877 | **P0** | `_GridPerceptor._to_grid()` — retourne `frame` sans transposition si `isinstance(frame[0], list)` ; `_SelectPlaceFSM._to_int_grid()` transpose correctement (conflit de convention) | `if isinstance(frame[0], list): return frame` | Uniformiser : une seule fonction `_to_int_grid` partagée ou s'assurer que `_GridPerceptor` et `_SelectPlaceFSM` utilisent la même convention |
| **F-002** | `my_agent_v135.py` | ~400-500 | **P0** | Perception = distribution couleurs uniquement — aucune segmentation d'objets au sens CDC §5.2 | `Counter(int(c) for row in g for c in row)` | Implémenter `_ObjectSegmentor` (BFS par couleur + propriétés spatiales) en v14 |
| **F-003** | `my_agent_v135.py` | 2200–2220 | **P1** | Mémoire épisodique non persistante entre parties — `_EpisodicMemory` réinitialisé dans `__init__` à chaque jeu | `self._memory = _EpisodicMemory()` dans `__init__` | Cross-game memory via fichier JSON sérialisé chargé à l'init |
| **F-004** | `my_agent_v135.py` | 2523–2524 | **P0** | Phase explore = `random.choice(unseen)` — aléatoire pur, aucune hypothèse générée | `action = random.choice(unseen)` | Priorité par signal structurel (objet non encore touché en priorité sur action random) |
| **F-005** | `my_agent_v135.py` | — | **P1** | Absence totale de Ni (compression relationnelle) — pas d'extraction de patterns inter-niveaux | Absent | Module `_PatternExtractor` v14 |
| **F-006** | `my_agent_v135.py` | ~660 | **P0** | `_RuleMemory._classify()` retourne GROWING si `level_up=True` quel que soit le changement structurel réel | `if level_up: return _TransformType.GROWING` | Classifier sur le delta structurel du frame (avant/après), level_up comme signal secondaire |
| **F-007** | `my_agent_v135.py` | ~2530 | **P1** | `_CognitiveEngine.score_all(features=features)` — le "métacontrôleur" lit le contenu perceptif directement (violation CDC §7.8) | `scores = engine.score_all(fp, candidates, features, ...)` | Passer uniquement des signaux [0,1] agrégés au moteur de scoring, pas les features brutes |
| **F-008** | `my_agent_v135.py` | — | **P1** | Fi contraintes 4 (honnêteté), 5 (intégrité mémoire journal), 6 (irréversibilité) absentes | Absent | Ajouter vérification journal append-only + assertion confidence ≤ 1.0 |
| **F-009** | `my_agent_v135.py` | 2109–2138 | **P1** | `_GoalDeltaTracker.goal_found=False` sur tous les 25 jeux locaux (confirmé) — aucun mécanisme de fallback d'interprétation de l'objectif | `_GOAL_ATTRS` liste manque les attributs réels ARC-AGI-3 | Inspecter `FrameData` live pour identifier les vrais attributs de récompense ARC-AGI-3 dans les logs rerun |
| **F-010** | `my_agent_v135.py` | ~2530 | **P1** | Violation §7.8 : le score_all reçoit `features` (couleurs, densité, unique_colours) — contenu frame, pas signaux abstraits | `engine.score_all(fp, candidates, features, ...)` | Abstraire les features en vecteur de signaux [0,1] avant passage au moteur |
| **F-011** | `my_agent_v135.py` | 2202 | **P1** | Graine temporelle — non reproductible bit-à-bit : `random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))` | Graine temporelle | `random.seed(hash(str(self.game_id)))` — graine déterministe basée sur game_id uniquement |
| **F-012** | `my_agent_v135.py` | Tout | **P2** | Pas de séparation zone publique/privée/échange — accès direct entre tous les modules | Architecture plate | Architecture slots CDC §8 (v14+ uniquement) |
| **F-013** | `my_agent_v135.py` | Tout | **P2** | Pas de mémoire relationnelle ni de schémas persistants inter-tâches | Absent | Mémoire relationnelle v14 |
| **F-014** | `my_agent_v135.py` | Tout | **P2** | Pas d'attribution Shapley — `_n_progress_real` est un proxy non attribué | Proxy compteur | Attribution formelle v14 |
| **F-015** | `my_agent_v135.py` | Tout | **P2** | Aucun entraînement de poids — performances plafonnées par heuristiques | Agent heuristique pur | Phase A–D d'entraînement v14 (long terme) |
| **F-016** | `my_agent_v135.py` | Tout | **P2** | Pas de sommeil / consolidation hors ligne | Absent | v14 (long terme) |
| **F-017** | `my_agent_v135.py` | ~1400 | **P1** | `confidence = n_changed/9.0` — non calibrée (pas de Brier/ECE) | `confidence = n_changed / 9.0` | Calibration empirique sur jeux locaux, cible ECE < 0.1 |
| **F-018** | `my_agent_v135.py` | Tout | **P2** | Aucune structure de poids — non dimensionnable selon CDC V1 (1B params) | Agent Python pur | Cœur PyTorch v14 (long terme) |
| **F-019** | `my_agent_v135.py` | ~50–120 | **P1** | Logger Kaggle écrit dans stdout uniquement en mode compétition — fichier `.jsonl` persist impossible | `print(json.dumps(...), flush=True)` | Écrire aussi dans `/tmp/lucy_forensic.jsonl` (accessible Kaggle) |
| **F-020** | `tests/` | Tout | **P1** | H1 (routage vs aléatoire) non testée formellement (protocole §18.5 non appliqué) | Test absent | Ajouter `test_h1_routing_vs_random.py` (10 graines, 25 jeux) |
| **F-021** | `my_agent_v135.py` | ~620–650 | **P0** | `_to_int_grid` dupliqué en 3 endroits (`_pick_active_cell` ~l.1360, `_SelectPlaceFSM._to_int_grid` ~l.1100, `_validate_transposition_regression` ~l.530) — source de désynchronisation | 3 copies | Extraire fonction module `_to_int_grid(frame) -> list[list[int]]` utilisée par tous |
| **F-022** | `my_agent_v135.py` | ~1576–1583 | **P0** | `_failed_coords.clear()` appelé AVANT `_failed_coords.add(last_click)` dans le chemin recovery — clear efface le dernier clic qu'on vient d'enregistrer | `self._failed_coords.clear()` puis `self._failed_coords.add(...)` à l'action suivante | Inverser l'ordre : `add()` puis `clear()` au reset suivant, ou utiliser un set temporaire |

---

## 5. Analyse comparative des forces

Les éléments suivants du code v13.5 sont **conformes ou en avance** sur le CDC pour le stade de développement actuel (MVP compétition) :

| Point fort | CDC correspondant | Niveau de conformité |
|---|---|---|
| `_KaggleForensicLogger` v2 nanoseconde | §17.1 journal forensic | ✅ CONFORME |
| Budget borné `MAX_ACTIONS_TOTAL=500` + `MAX_ACTIONS_PER_LEVEL=80` | §7.3 budget borné | ✅ CONFORME |
| Phase explore/exploit/recover | §4.5 boucle adaptative | ✅ BONNE APPROXIMATION |
| `_SelectPlaceFSM` SELECT→PLACE→OBSERVE | §5.7 Te efficacité externe | ✅ BONNE IMPLÉMENTATION |
| BFS 4-connexité pour groupes | §5.2 Se détection groupes | ✅ |
| FIX P0-A/B/C/P1-D niveau_up correct | §5.3 Si mémoire pertinente | ✅ |
| `CERTIFIED_100=false \| unique_human_proven=false` dans les docstrings | Invariants absolus ARTCB | ✅ |
| Notebook `submission.ipynb` avec gate `KAGGLE_IS_COMPETITION_RERUN` | §17 déploiement | ✅ |
| Tests 355/355 PASS | §18 banc de mesure | ✅ PARTIEL |

---

## 6. Plan de correction v14.x priorisé

### P0 — Corrections immédiates (avant analyse du score rerun)

| Ref | Action | Fichier cible | Failles corrigées |
|---|---|---|---|
| **v13.5-HOT-1** | Unifier `_to_int_grid` en une seule fonction partagée | `my_agent_v135.py` | F-021 |
| **v13.5-HOT-2** | Corriger l'ordre `add()`/`clear()` dans recovery | `my_agent_v135.py` | F-022 |
| **v13.5-HOT-3** | Corriger la graine aléatoire : `random.seed(hash(str(self.game_id)))` | `my_agent_v135.py` | F-011 |
| **v13.5-HOT-4** | Ajouter écriture forensic dans `/tmp/lucy_forensic.jsonl` en complément de stdout | `my_agent_v135.py` | F-019 |

### P0 — À faire après réception des logs du rerun en cours

| Ref | Action | Fichier cible | Failles corrigées |
|---|---|---|---|
| **v14.0-A** | Lire les logs forensic Kaggle du rerun → Identifier `FSM_CLASSIFY` / `FSM_TRANSITION` / `GAME_DONE` → Mesurer le taux de classification correcte | Audit seulement | F-002, F-006 |
| **v14.0-B** | Si score rerun < 0.14 : corriger `_RuleMemory._classify()` → classifier sur delta structurel du frame | `my_agent_v135.py` | F-006 |
| **v14.0-C** | Inspecter les vrais attributs `FrameData` dans les logs rerun pour identifier l'attribut de goal/reward ARC-AGI-3 | `my_agent_v135.py` `_GoalDeltaTracker._GOAL_ATTRS` | F-009 |

### P1 — v14.1 : Perception structurelle (si rerun < 0.14 ou pour améliorer)

| Ref | Action | Fichier cible | Failles corrigées |
|---|---|---|---|
| **v14.1-A** | Implémenter `_ObjectSegmentor` : BFS par couleur → liste d'objets (couleur, taille, bbox, centroïde, forme) | `my_agent_v140.py` | F-002 |
| **v14.1-B** | Remplacer `_classify_frame()` par classification basée sur rôles d'objets (pièce = objet mobile, cible = emplacement marqué, fond = reste) | `my_agent_v140.py` | F-002, F-006 |
| **v14.1-C** | Uniformiser la convention frame dans `_GridPerceptor._to_grid()` et `_SelectPlaceFSM._to_int_grid()` | `my_agent_v140.py` | F-001 |
| **v14.1-D** | Ajouter test H1 baseline aléatoire formelle (10 graines, protocole §18.5) | `tests/test_h1_routing_vs_random.py` | F-020 |
| **v14.1-E** | Calibration empirique `confidence` dans `_is_confirmed_selection` sur jeux locaux | `my_agent_v140.py` | F-017 |

### P2 — v14.2 : Signals CDC + persistance (amélioration structurelle)

| Ref | Action | Fichier cible | Failles corrigées |
|---|---|---|---|
| **v14.2-A** | Abstraire les features perceptives en vecteur de signaux [0,1] avant `score_all()` | `my_agent_v140.py` | F-007, F-010 |
| **v14.2-B** | Mémoire inter-parties : sérialiser `_EpisodicMemory` vers `/tmp/lucy_cross_game.json` | `my_agent_v140.py` | F-003 |
| **v14.2-C** | Ébauche `_PatternExtractor` (Ni) : patterns couleur→position récurrents entre niveaux | `my_agent_v140.py` | F-005 |

### P3 — Long terme : architecture CDC complète

Ces éléments ne peuvent être implémentés qu'après validation des P0/P1 et dans un environnement d'entraînement dédié (GPU) :
- Cœur PyTorch + poids appris (F-015, F-018)
- 8 fonctions CDC complètes avec hubs Pi/Pe/Di/De (F-012, §4)
- Sommeil + consolidation (F-016)
- Attribution Shapley (F-014)
- Espace de travail à slots (F-012)

**⚠️ DÉCISION ARCHITECTURALE À VALIDER :**  
Le CDC §1.3 interdit explicitement "un ensemble d'heuristiques codées uniquement pour gagner à un benchmark". Cependant, le cadre de la compétition ARC-AGI-3 impose des contraintes de temps d'exécution et d'absence de modèles pré-entraînés qui rendent l'implémentation complète du CDC impossible à court terme. **L'utilisateur doit confirmer la stratégie :** développer le CDC complet (long terme) en parallèle de l'agent compétition (court terme), ou fusionner les deux trajectoires dès v14.x.

---

## 7. Tableau de synthèse avant/après (extraits critiques)

### F-021 — Unification `_to_int_grid`

**Avant :**
```python
# Fichier : my_agent_v135.py, ligne ~1360 (_pick_active_cell)
def _pick_active_cell(...):
    def _to_int(g):
        ...  # copie locale

# Fichier : my_agent_v135.py, ligne ~1100 (_SelectPlaceFSM)
@staticmethod
def _to_int_grid(frame: Any) -> list[list[int]]:
    ...  # implémentation 1

# Fichier : my_agent_v135.py, ligne ~530 (_validate_transposition_regression)
def _validate_transposition_regression(...):
    def _to_int_g(g):
        ...  # copie 2
```

**Après recommandé (v14.0) :**
```python
# Fichier : my_agent_v140.py, ligne ~50 (module level)
def _to_int_grid(frame: Any) -> list[list[int]]:
    """Canonical frame normalizer — single source of truth.
    Handles both row-major and columnar ARC-AGI-3 formats.
    """
    if not frame:
        return []
    if isinstance(frame[0], list):
        # Already row-major: [[row0_col0, row0_col1, ...], [row1_col0, ...]]
        return [[int(c) for c in row] for row in frame]
    # Columnar: [[col0_row0, col0_row1, ...], [col1_row0, ...]] — transpose
    return [[int(frame[col][row]) for col in range(len(frame))]
            for row in range(len(frame[0]))]
```

---

### F-022 — Ordre add/clear dans recovery

**Avant :**
```python
# Fichier : my_agent_v135.py, lignes ~1576–1583
self._failed_coords.add((lx, ly))   # ← enregistre le dernier clic
...
self._failed_coords.clear()          # ← EFFACE immédiatement, y compris ce qu'on vient d'ajouter
```

**Après recommandé (v14.0) :**
```python
# Pattern correct : clear AVANT add, pas après
self._failed_coords.clear()          # ← efface les anciens échecs
self._failed_coords.add((lx, ly))   # ← enregistre le nouveau (maintenu)
```

---

### F-011 — Graine déterministe

**Avant :**
```python
# Fichier : my_agent_v135.py, ligne 2202
random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))
```

**Après :**
```python
# Fichier : my_agent_v140.py
random.seed(hash(str(self.game_id)))  # déterministe, reproductible bit-à-bit (P5 CDC)
```

---

## 8. Éléments oubliés à préciser

Les points suivants n'étaient pas explicitement demandés mais sont critiques pour la complétion de l'audit :

### 8.1 — Score du rerun en cours non disponible

La soumission competition rerun est **en cours au moment de la rédaction de ce rapport** (~1h estimée). Le score v13.5 réel est **inconnu**. Actions à effectuer dès que le score est disponible :
1. Lire les logs forensic Kaggle (stdout du rerun si accessibles via API ou page Kaggle)
2. Comparer au score v7.0 (0.14 = référence)
3. Si score ≥ 0.14 → corrections P0-HOT seulement (F-021, F-022, F-011)
4. Si score < 0.14 → corrections P0 + v14.1-A/B (perception structurelle) en priorité
5. **Produire rapport L-059 après réception des logs**

### 8.2 — Nouveaux logs Kaggle à analyser

Les logs de soumission précédents (`kaggle_v135_raw.log` — 51 lignes) ne contenaient que le mode commit (dummy). Les logs du rerun contiendront les vrais événements GAME_INIT/FSM/GAME_DONE pour analyser les 25 jeux. **Ces logs doivent être lus et analysés dans L-059.**

### 8.3 — Décision stratégique CDC vs compétition

La question non tranchée : l'architecture CDC complète (8 fonctions, 4 hubs, métacontrôleur, PyTorch, sommeil) est-elle la cible de `LuCY/agent/` pour la compétition ARC-AGI-3, ou bien existe-t-il deux branches distinctes :
- `LuCY/agent/` = agent compétition (heuristique, sans PyTorch)
- `LuCY/src/lucy/` = implémentation CDC académique long terme

La structure de dossier `LuCY/src/lucy/functions/` (Se, Si, Ne, Ni, Ti, Te, Fi, Fe en Python) suggère que la trajectoire CDC est déjà séparée. Cette séparation doit être **documentée explicitement dans `ROADMAP_LuCY`** pour éviter la confusion.

### 8.4 — Tests T-121 à T-135 (v13.5) non analysés en détail

Les 355 tests PASS incluent les tests T-FSM-101 à T-120 (L-054). Les tests T-121 à T-135 ne sont pas documentés dans les logs disponibles. Vérifier qu'ils couvrent les cas d'échec de F-001 (convention frame) avant de les modifier.

### 8.5 — `_validate_transposition_regression` résultats non lus

La fonction `_validate_transposition_regression()` est appelée au premier frame et ses résultats sont loggés (`TRANSPOSITION_VALIDATION: passed=X/5 failed=Y`). Ces résultats ne sont pas dans les logs disponibles (mode commit, pas de game loop). À vérifier dans les logs du rerun.

---

## Synthèse finale

| Dimension | État |
|---|---|
| **Score compétition** | 0.14 (v7.0) ; v13.5 rerun en cours |
| **Tests locaux** | 355/355 PASS ✅ |
| **Conformité CDC §1–§21** | **2/15 étapes satisfaites** |
| **Failles critiques (P0)** | **F-001, F-002, F-004, F-006, F-021, F-022** = 6 P0 |
| **Failles importantes (P1)** | F-003, F-007–F-011, F-017, F-019, F-020 = 9 P1 |
| **Failles structurelles (P2)** | F-012–F-016, F-018 = 6 P2 |
| **Plan v14.x** | v13.5-HOT (4 corrections immédiates) → v14.0 (après rerun) → v14.1 (perception structurelle) |
| **CERTIFIED_100** | false |
| **unique_human_proven** | false |

**⚡ Action immédiate requise :** Attendre les logs du competition rerun (en cours ~1h), puis lire et produire L-059 avec le score réel et les logs forensic. Les corrections P0-HOT (F-021, F-022, F-011, F-019) peuvent être appliquées dès validation utilisateur sans attendre le rerun.
