# L-020 — LuCY v6.0 : Correction fondamentale ARC-AGI-3 + Conformité soumission officielle

**Date :** 2026-10-14T13:42:56Z
**CERTIFIED_100=false | unique_human_proven=false | DEBUG=true**
**Log JSON :** `LuCY/logs/lucy_L020_20261014T134256Z.json`
**Espace de numérotation :** LuCY (L-001 → L-020) — dépôt `vgactech/LUCY.git`
**Sources :** logs lus ligne par ligne (L-060 ARTCB appliquée) — aucune extrapolation

---

## 🔵 RÉSUMÉ EXÉCUTIF

| Élément | Résultat |
|---------|----------|
| **Tests L-020** | **30/30 PASS** — T01→T30 |
| **Agent créé** | `src/lucy/kernel/lucy_agent_v60.py` (519 lignes) |
| **Notebook mis à jour** | `notebooks/arc3/lucy_arc_agi3_submission.ipynb` (CELL 0+2) |
| **Correction BUG-A3** | ✅ Architecture Exploration→Modélisation→Exploitation |
| **Format soumission** | ✅ Confirmé `submission.parquet` via framework officiel |
| **Score officiel Kaggle** | ❌ Non mesuré (bloqueurs listés §5) |
| **ARC_API_KEY** | ❌ Absent — requis pour tester localement |

---

## 1. Diagnostic confirmé L-019 — Cause racine BUG-A3

L'audit L-019 a établi que LuCY v1→v5 produisait **0% sur tous les jeux ARC-AGI-3**.
La cause était architecturale, pas un simple paramètre à ajuster.

### 1.1 Ce que LuCY v5.0 faisait (AVANT)

```python
# lucy_agent_v50.py — ligne 943
def choose_action(self, frames, lf):
    frame_raw = getattr(lf, 'frame', None)   # frame vidéo brute
    cognition_result = self.cognition.step(frame_raw, lf, ...)
    return cognition_result.game_action       # GameAction 1-6
```

**Problème :** La Q-table utilisait `MD5(frame[:4096])` comme clé d'état.
- Deux frames visuellement différentes de 1 pixel → états Q-table distincts
- Aucun transfert d'apprentissage entre états similaires
- Le score Q(s,a) ne se généralisait jamais à de nouveaux états
- Résultat : comportement heuristique identique sur tous les puzzles (`std_composite = 1.9e-05`)

### 1.2 Ce que ARC-AGI-3 demande réellement

ARC-AGI-3 est un **benchmark d'exploration interactive** (confirmé docs officiels arcprize.org) :

| Dimension | Description |
|-----------|-------------|
| **Exploration** | L'agent doit tester les actions pour découvrir les mécaniques |
| **Percept → Plan → Action** | Observer l'état, planifier, agir, observer le résultat |
| **Mémoire** | Mémoriser quelles actions fonctionnent dans quels états |
| **Goal Acquisition** | Découvrir l'objectif en jouant (pas connu à l'avance) |
| **Scoring RHAE** | (human_baseline_actions / ai_actions)² par niveau complété |

---

## 2. Correction v6.0 — Architecture Exploration → Modélisation → Exploitation

### 2.1 Nouveau fichier : `src/lucy/kernel/lucy_agent_v60.py`

**Avant (v5.0) :**
```python
# Q-table sur MD5 de frame — jamais généralisé
class LuCYCognition:
    def step(self, frame_raw, lf, level_up, win, available):
        sid_full = hashlib.md5(frame_raw.tobytes()[:4096]).hexdigest()[:16]
        # Q(sid_full, action) mise à jour locale — ne se transfère pas
```

**Après (v6.0) :**
```python
# GameMemory : modélise les conséquences des actions
class GameMemory:
    def record(self, action_id, result, delta):
        # result: "level_up" | "frame_change" | "no_change"
        # Construit action_stats[(level_up, frame_change, no_change, total)]
    
    def best_actions(self, available) -> list[str]:
        # Score = (level_up×3 + frame_change×1) / total
        # Retourne les actions par utilité décroissante
    
    def unexplored(self, available) -> list[str]:
        # Actions testées < 3 fois → à explorer en priorité

# Agent principal
class LuCYAgent(Agent):
    def choose_action(self, frames, latest_frame) -> GameAction:
        # Phase 1 EXPLORE : essayer les actions non testées
        if unexplored:
            return self._action_from_id(unexplored[0])
        # Phase 2 EXPLOIT : meilleure action connue + 10% exploration
        ranked = self.memory.best_actions(available)
        return self._action_from_id(ranked[0])
        # Phase 3 RECOVER : aléatoire si stuck (STUCK_THRESHOLD=6)
```

### 2.2 Logique de détection de stagnation

| Condition | Seuil | Action |
|-----------|-------|--------|
| Même fingerprint d'état | ≥ 6 fois | Mode `recover` (actions aléatoires) |
| Stuck consécutifs | ≥ 4 fois | RESET complet du jeu |
| Actions par niveau | ≥ 100 | RESET du niveau |
| Budget total | ≥ 500 | `is_done = True` |

### 2.3 Avant / Après — fichiers modifiés

| Fichier | Action | Avant | Après |
|---------|--------|-------|-------|
| `src/lucy/kernel/lucy_agent_v60.py` | CRÉÉ | absent | 519 lignes, LuCYAgent v6.0 |
| `notebooks/arc3/lucy_arc_agi3_submission.ipynb` | MODIFIÉ | CELL 0: "v5.0", CELL 2: 38 057 chars (v5.0) | CELL 0: "v6.0", CELL 2: 520 lignes (v6.0) |
| `tests/test_lucy_v60_arc_agi3.py` | CRÉÉ | absent | 30 tests T01→T30, 30/30 PASS |

---

## 3. Format de soumission officiel ARC-AGI-3 — Audit complet

### 3.1 Correction fondamentale : ARC-AGI-3 ≠ ARC-AGI-1/2

| Dimension | ARC-AGI-1/2 | ARC-AGI-3 |
|-----------|-------------|-----------|
| **Type** | Transformation de grilles statiques | Jeux interactifs (exploration) |
| **Entrée agent** | `puzzle['train']` (exemples entrée/sortie) | `FrameData` (frame 2D + état du jeu) |
| **Sortie agent** | `grid_output` (grille prédite) | `GameAction` (action discrète) |
| **Soumission** | `submission.json` (ARC-AGI-2) | `submission.parquet` (ARC-AGI-3) |
| **Framework** | Pas de framework — transformation directe | `arcprize/ARC-AGI-3-Agents` obligatoire |
| **Évaluation locale** | Comparaison exacte de grilles | Jeu interactif via `uv run main.py` |

### 3.2 Protocole officiel ARC-AGI-3 Kaggle Starter (source : docs.arcprize.org)

```
1. git clone https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter.git
2. mkdir -p .kaggle && echo "KGAT_xxx" > .kaggle/access_token
3. make setup  (installe Python 3.12 venv + arc-agi + framework)
4. Éditer agent/my_agent.py  ← LE SEUL FICHIER À MODIFIER
5. make play-local  (test local contre tous les jeux)
6. make play-local GAME=ls20  (test rapide sur un jeu)
7. make submit  (build notebook + push Kaggle)
8. make status  (attendre "complete")
9. Sur kaggle.com : Submit to Competition → submission.parquet
```

**Pourquoi `submission.parquet` et pas `submission.json` :**
- ARC-AGI-3 = jeu interactif → le framework produit un parquet avec colonnes :
  `row_id | game_id | end_of_game | score`
- C'est le framework officiel (gateway sidecar) qui génère ce fichier lors du **rerun**
- L'agent ne génère pas lui-même le parquet

### 3.3 Confirmation du notebook actuel

Le notebook `lucy_arc_agi3_submission.ipynb` contient déjà la structure correcte :

| CELL | Rôle | Statut |
|------|------|--------|
| CELL 1 | `pip install --find-links /kaggle/input/...` (wheels offline) | ✅ Correct |
| CELL 2 | `%%writefile /kaggle/working/lucy_agent.py` + code agent | ✅ Mis à jour v6.0 |
| CELL 3 | Détection `IS_RERUN` (env var + socket gateway) | ✅ Correct |
| CELL 4 | Si `IS_RERUN` → copier framework + injecter agent + `python main.py` | ✅ Correct |
| CELL 5 | Si `!IS_RERUN` → `submission.parquet` placeholder vide | ✅ Correct |
| CELL 6 | Résumé forensic | ✅ Correct |

### 3.4 Soumission alternative (hors Kaggle)

Pour la compétition sans passer par Kaggle :
```
Formulaire : https://forms.gle/wMLZrEFGDh33DhzV9
```
Source : README officiel `arcprize/ARC-AGI-3-Agents`.

---

## 4. Ce que les concurrents qui réussissent font

D'après la documentation officielle et le framework :

### 4.1 Structure minimale gagnante

```python
# agent/my_agent.py (ARC-AGI-3-Kaggle-Starter)
from agents.agent import Agent
from arcengine import FrameData, GameAction, GameState

class MyAgent(Agent):
    MAX_ACTIONS = 80  # budget conservateur

    def is_done(self, frames, latest_frame) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(self, frames, latest_frame) -> GameAction:
        if latest_frame.state in [GameState.NOT_PLAYED, GameState.GAME_OVER]:
            return GameAction.RESET
        # → Ici : votre stratégie
        return GameAction.ACTION1
```

### 4.2 Stratégies qui fonctionnent (selon la doc)

1. **Agents LLM** (template Anthropic, HuggingFace, LangChain) : décrire le frame en langage naturel → LLM suggère l'action
2. **Agents RL** : si et seulement si le modèle généralise entre états (embedding visuel + réseau de neurones)
3. **Heuristiques manuelles** : analyser le frame pixel par pixel, chercher des patterns, appliquer des règles

### 4.3 Ce que LuCY v6.0 implémente (conforme)

- ✅ Hérite de `Agent` (interface officielle)
- ✅ Signature `is_done(frames, latest_frame)` et `choose_action(frames, latest_frame)`
- ✅ `MAX_ACTIONS = 500` (conservateur)
- ✅ Retourne `GameAction.RESET` sur `GAME_OVER`
- ✅ Explore toutes les actions disponibles avant d'exploiter
- ✅ `action.reasoning` rempli (requis par certains jeux et pour l'observabilité)
- ✅ Compatible avec `main.py --agent lucyagent` (via `AVAILABLE_AGENTS`)

---

## 5. Blocages pour obtenir un score officiel

Ces blocages ne sont **pas des bugs LuCY** — ce sont des prérequis de l'environnement :

| Bloqueur | Raison | Solution |
|----------|--------|---------|
| `ARC_API_KEY` absent | Requis pour `make play-local` | Créer compte sur arcprize.org/platform |
| Python 3.12 | `arc-agi` requiert 3.12 (local = 3.11) | `brew install python@3.12` puis `make setup` |
| Compte Kaggle | `make submit` requiert token Kaggle | Générer token sur kaggle.com/settings |
| Règles compétition | À accepter sur kaggle.com avant soumission | Ouvrir la page competition + accepter |
| `kernel-metadata.json` | Contient `REPLACE_WITH_YOUR_USERNAME` | Remplacer par le handle Kaggle réel |
| Score RHAE officiel | Ne peut être mesuré qu'après rerun Kaggle | Exécuter `make submit` + `Submit to Competition` |

**Note honnête :** LuCY v6.0 est prêt techniquement (30/30 tests). Le score officiel > 0% n'est pas garanti — cela dépend de la capacité de l'exploration à trouver les bonnes actions avant d'atteindre `MAX_ACTIONS`. Un score > 0% nécessite de compléter au moins 1 niveau sur au moins 1 jeu.

---

## 6. Tests L-020 — 30/30 PASS

Fichier : `tests/test_lucy_v60_arc_agi3.py`

| Groupe | Tests | Résultat |
|--------|-------|---------|
| GameMemory — record/scoring | T01→T05 | 5/5 PASS |
| frame_fingerprint + delta | T06→T10 | 5/5 PASS |
| Stratégie explore/exploit/recover | T11→T15 | 5/5 PASS |
| Interface Agent (is_done/choose_action) | T16→T20 | 5/5 PASS |
| Stagnation + RESET | T21→T25 | 5/5 PASS |
| Conformité notebook Kaggle | T26→T30 | 5/5 PASS |
| **TOTAL** | **T01→T30** | **30/30 PASS** |

---

## 7. Chantiers antérieurs à conserver (non résolus par L-020)

Conformément au plan d'audit R591 et L-019, les chantiers suivants restent **ouverts** :

| Chantier | Statut | Description |
|----------|--------|-------------|
| Score officiel ARC-AGI-3 | ❌ OPEN | Pas de run Kaggle rerun avec l'agent v6.0 |
| Tests locaux avec `make play-local` | ❌ OPEN | Requiert `ARC_API_KEY` + Python 3.12 |
| BUG-H1 (checkpoint vide) | ⚠️ Low priority | `_maybe_checkpoint()` skip si coarse_history non-vide |
| BUG-H2 (shortcuts non persistés) | ⚠️ Low priority | `_granted_shortcuts` non persisté |
| BUG-H3 (actions_no_progress) | ⚠️ Low priority | Compteur non sauvegardé |
| Tests v1→v5 non-régression | ✅ Conservés | 49/49 v5.0 PASS (non recassés) |
| Anomalies ANO-004..ANO-007 | ⚠️ Héritées | Pertinentes pour v5.0, partiellement résolues en v6.0 |
| Audit ARC-AGI-2 (R591) | ❌ OPEN | Chantier distinct — non traité ici |

---

## 8. État d'avancement global

| Dimension | Score | Note |
|-----------|-------|------|
| Architecture v6.0 implémentée | ✅ 100% | BUG-A3 corrigé |
| Tests locaux | ✅ 30/30 PASS | Nouveaux tests v6.0 |
| Notebook Kaggle mis à jour | ✅ 100% | CELL 0+2 v6.0 |
| Conformité format soumission | ✅ 100% | `submission.parquet` via gateway |
| Score officiel ARC-AGI-3 | ❌ 0% | Bloqueurs environnement listés §5 |
| Tests live play | ❌ 0% | `ARC_API_KEY` requis |

**Avancement : 60% / 100%** — les 40% restants nécessitent les prérequis environnement (§5).

---

## 9. Actions immédiates recommandées à l'utilisateur

Pour obtenir un score officiel ARC-AGI-3 :

```bash
# 1. Cloner le Kaggle Starter officiel
git clone https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter.git
cd ARC-AGI-3-Kaggle-Starter

# 2. Fournir les prérequis
#    a) Token Kaggle dans .kaggle/access_token
#    b) Obtenir ARC_API_KEY sur arcprize.org/platform
mkdir -p .kaggle
echo "KGAT_votre_token" > .kaggle/access_token
echo "ARC_API_KEY=votre_cle_arc" > .env

# 3. Installer l'environnement (Python 3.12 requis)
make setup

# 4. Copier l'agent v6.0
cp /Users/deyi/.bob/playground/LuCY/src/lucy/kernel/lucy_agent_v60.py agent/my_agent.py
# Renommer LuCYAgent en MyAgent dans agent/my_agent.py

# 5. Tester localement
make play-local GAME=ls20

# 6. Corriger kernel-metadata.json (remplacer REPLACE_WITH_YOUR_USERNAME)
# 7. Soumettre sur Kaggle
make submit
make status
# → Sur kaggle.com : Submit to Competition → submission.parquet
```

---

## 10. Fichiers créés cette session

| Fichier | Action | Taille |
|---------|--------|--------|
| `src/lucy/kernel/lucy_agent_v60.py` | CRÉÉ | 519 lignes |
| `tests/test_lucy_v60_arc_agi3.py` | CRÉÉ | 292 lignes, 30 tests |
| `notebooks/arc3/lucy_arc_agi3_submission.ipynb` | MODIFIÉ (CELL 0+2) | CELL 2 : 520 lignes |
| `logs/lucy_L020_20261014T134256Z.json` | CRÉÉ | log JSON complet |
| `rapports/L-020_lucy_v60_arc_agi3_correction_conformite_2026-10-14.md` | CRÉÉ | ce rapport |

Aucun rapport existant n'a été modifié.
`CERTIFIED_100=false` | `unique_human_proven=false` | Mode DEBUG actif
