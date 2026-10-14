# L-021 — LuCY v7.0 : Corrections P0 + Format Soumission ARC-AGI-3

**Date :** 2026-10-14  
**Agent :** LuCY v7.0  
**Rapport précédent :** L-020  
**CERTIFIED_100 :** false | **unique_human_proven :** false | **Mode DEBUG :** actif  

---

## 1. Résumé exécutif

Ce rapport documente les corrections apportées dans LuCY v7.0, les tests locaux effectués, et l'état de préparation pour la soumission officielle à la compétition ARC-AGI-3 Kaggle (`arc-prize-2026-arc-agi-3`).

---

## 2. Bugs corrigés (avant / après)

### BUG-A4 — `available_actions` ignoré (v6.0)

**Fichier :** `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`

**Avant (v6.0, lignes 58-61) :**
```python
SIMPLE_ACTIONS: list[GameAction] = [
    a for a in GameAction
    if a not in (GameAction.RESET,) and not a.is_complex()
]
```
L'agent utilisait toutes les actions simples globales, ignorant `latest_frame.available_actions`.

**Après (v7.0, `_get_available_actions()`) :**
```python
avail = getattr(latest_frame, "available_actions", None)
if avail:
    result = []
    for a in avail:
        if isinstance(a, GameAction):
            if a is not GameAction.RESET:
                result.append(a)
        elif isinstance(a, int):
            try:
                ga = GameAction.from_id(a)
                if ga is not GameAction.RESET:
                    result.append(ga)
            except ValueError:
                pass
    if result:
        return result
```

---

### BUG-A5 — `available_actions` retourne des `int` pas des `GameAction`

**Découverte :** En déboguant, `available_actions = [1, 2, 3, 4]` — des entiers bruts.  
**Correction :** Conversion explicite `int → GameAction.from_id(a)` dans `_get_available_actions()`.

---

### BUG-A6 — Fingerprint frame identique malgré actions (stuck en boucle)

**Cause :** Le frame est une liste de listes Python (`[arr.tolist() for arr in raw.frame]`, shape `(1, 64, 64)`). La version précédente extrayait `flat[:512]` — qui correspond toujours aux pixels statiques du coin supérieur gauche.

**Avant (v6.0) :**
```python
key = str(flat[:64])
return hashlib.md5(key.encode()).hexdigest()[:12]
```

**Après (v7.0) :**
```python
return hashlib.sha1(str(flat).encode()).hexdigest()[:16]
```
SHA1 sur l'intégralité du frame aplati → toute modification de pixel est détectée.

**Résultat mesuré :**
- v6.0 : `stuck_streak` montait à 9+ → RESET permanent, `score=0.0`
- v7.0 : `stuck_streak=0` tout au long, agent explore vraiment le jeu

---

### BUG-A3 (corrigé en v6.0, conservé en v7.0)

Q-table indexée par MD5(frame[:4096]) → jamais généralisable. Remplacé par UCB1 sur actions (pas sur états).

---

## 3. Architecture v7.0

| Module | Description |
|--------|-------------|
| `_get_available_actions()` | Extrait les actions légales du frame (int ou GameAction) |
| `_frame_fingerprint()` | SHA1 full-frame — détecte tout changement |
| `_frame_delta()` | Fraction de pixels différents entre deux frames |
| `_ActionModel` | Statistiques UCB1 par action (n_level_up, n_progress, n_total) |
| `MyAgent.choose_action()` | 3 phases : EXPLORE → EXPLOIT (UCB1) → RECOVER |

**Paramètres clés :**
- `UCB1_C = 1.4` (exploration standard)
- `MAX_ACTIONS_TOTAL = 500`
- `MAX_ACTIONS_PER_LEVEL = 120`
- `STUCK_THRESHOLD = 5`
- `RESET_AFTER_STUCK = 5`

---

## 4. Tests locaux

### Environnement
- Python 3.13, `arc-agi 0.9.9`, `ARC-AGI-3-Agents` cloné
- Clé API : `539087b5-32bb-4a4a-8689-ad4be99fe3f0`

### Résultats `play_local.py --game ls20 --max-steps 200`

| Métrique | v6.0 | v7.0 |
|----------|------|------|
| `stuck_streak` max | 9+ | **0** |
| Phase dominante | recover (boucle) | **exploit** |
| `levels_completed` | 0 | 0 |
| `score_local` | 0.0 | 0.0 |

Le score local reste 0.0 car LS20 est un jeu de labyrinthe complexe nécessitant une stratégie directionnelle précise. L'agent navigue sans se bloquer — c'est le prérequis pour pouvoir apprendre.

**Important :** Score local 0 ≠ score officiel Kaggle nul. La compétition utilise 25 jeux différents, et le score RHAE est calculé sur les niveaux complétés.

---

## 5. Format de soumission officiel (concurrents)

### Protocole Kaggle ARC-AGI-3
1. **Seul fichier à modifier :** `agent/my_agent.py` — classe `MyAgent(Agent)`
2. **Build :** `make submit` → `scripts/build_notebook.py` → `notebooks/submission.ipynb`
3. **Push :** `kaggle kernels push -p notebooks/`
4. **Rerun** sur Kaggle → "Submit to Competition"
5. **Artefact final :** `submission.parquet` généré par le framework

### Kernel ID actuel
```json
{"id": "ndarray2000/lucy-arc-agi3-v60", "competition": "arc-prize-2026-arc-agi-3"}
```

### Différence ARC-AGI-2 vs ARC-AGI-3

| | ARC-AGI-1/2 | ARC-AGI-3 |
|---|---|---|
| Type | Grilles statiques | Environnement interactif |
| Input | Exemples entrée/sortie | Observations successives |
| Output | Grille de sortie | Actions séquentielles |
| Soumission | JSON | notebook Kaggle + parquet |

---

## 6. État des blocages

| Item | Statut |
|------|--------|
| `vendor/ARC-AGI-3-Agents/` | ✅ Cloné |
| `slim_framework.py` | ✅ Exécuté |
| Agent v7.0 opérationnel | ✅ stuck=0, explore correctement |
| Score local > 0 | ❌ LS20 non résolu (jeu difficile) |
| `make submit` | ⏳ À exécuter |
| Score officiel Kaggle | ⏳ Après submit |

---

## 7. Prochaine action

```bash
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter
make submit
make status
```

Puis vérifier le run Kaggle et soumettre à la compétition.

---

*Rapport L-021 — Log : `logs/lucy_L021_20261014T152242Z.json`*  
*CERTIFIED_100=false | unique_human_proven=false*
