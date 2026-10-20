# L-061 — Déploiement v14.0 : notebook régénéré, kernel-metadata mis à jour

**Date :** 2026-10-20T18:49:36Z  
**Version agent :** 14.0  
**Rapport précédent :** L-060 (bilan Phases 1–5 CDC académique)  
**Action :** Diagnostic architecture notebook + déploiement v14.0 + régénération notebook  
**CERTIFIED_100=false | unique_human_proven=false | DEBUG=true**

---

## 1. Diagnostic de la session (cause racine du score 0,00)

### 1.1 Lecture intégrale de `my_agent_v140.py`

La classe `MyAgent(Agent)` est **architecturalement correcte** :
- `choose_action()` et `is_done()` correctement implémentés
- Détection `KAGGLE_IS_COMPETITION_RERUN` : **inexistante dans l'agent** (c'est dans le notebook — comportement normal)
- Les 4 HOT fixes (F-021/F-022/F-011/F-019) sont bien présents et fonctionnels
- Logger forensic `/tmp/lucy_forensic.jsonl` actif (F-019 ✅)

### 1.2 Audit architecture notebooks

| Notebook | Format | Compétition | Usage |
|----------|--------|-------------|-------|
| `notebooks/lucy_arc_agi_submission.ipynb` | Statique JSON | arc-agi-2 | ❌ Mauvaise compétition |
| `notebooks/arc3/lucy_arc_agi3_submission.ipynb` | v6.0 obsolète | arc-agi-3 | ❌ Version ancienne |
| `vendor/.../notebooks/submission.ipynb` | Game loop arcengine | arc-agi-3 | ✅ **SEUL notebook valide** |

### 1.3 Cause racine confirmée (reprise L-057)

Le notebook `vendor/.../notebooks/submission.ipynb` avait été généré via `build_notebook.py` **pour v13.5** et **n'avait jamais été régénéré** après la création de v14.0. L'agent `vendor/.../agent/my_agent.py` était encore en v13.5.

**Schéma du problème :**
```
my_agent_v140.py  créé  ✅
vendor/agent/my_agent.py  ← TOUJOURS v13.5  ❌ (non mis à jour)
notebooks/submission.ipynb  ← TOUJOURS v13.5  ❌ (non régénéré)
kaggle kernels push → soumet v13.5, pas v14.0
```

### 1.4 Note sur le score 0,14 vs 0,00

| Version | Mode push | Score | Explication |
|---------|-----------|-------|-------------|
| v7.0 | `Submit to Competition` (UI Kaggle) | **0,14** | Competition rerun déclenché par l'UI → gateway → jeu réel |
| v13.5 | `kaggle kernels push` seulement | **0,00** | Commit mode → dummy parquet → aucun jeu |
| v14.0 | `kaggle kernels push` seulement | **À TESTER** | Même problème potentiel si l'utilisateur ne clique pas "Submit" |

**Règle absolue :** `kaggle kernels push` = commit mode = dummy parquet = score 0,00.  
Pour un score réel, **l'utilisateur doit cliquer "Submit to Competition"** sur l'interface Kaggle après le push.

---

## 2. Actions effectuées

### 2.1 Copie de l'agent v14.0

**AVANT :**  
Fichier : `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
Ligne 164 : `VERSION = "13.5"`

**APRÈS :**  
Fichier : `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
Ligne 164 : `VERSION = "14.0"`  
Source : copie exacte de `LuCY/agent/my_agent_v140.py` (2600 lignes)

```bash
cp LuCY/agent/my_agent_v140.py LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py
# Résultat : 2600 lignes copiées
```

### 2.2 Mise à jour kernel-metadata.json

**AVANT :**  
Fichier : `vendor/ARC-AGI-3-Kaggle-Starter/notebooks/kernel-metadata.json`  
`"id": "ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place"`  
`"title": "LuCY v13.5 ARC-AGI-3 BFS Guards FSM SELECT PLACE"`

**APRÈS :**  
`"id": "ndarray2000/lucy-v14-0-arc-agi-3-hot-fixes-deterministic"`  
`"title": "LuCY v14.0 ARC-AGI-3 HOT F021 F022 F011 F019 Deterministic"`

### 2.3 Régénération du notebook

```bash
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter && python3 scripts/build_notebook.py
# [build_notebook] Wrote notebooks/submission.ipynb  (accelerator: t4)
```

**Vérification notebook régénéré :**

| Paramètre | Valeur | Statut |
|-----------|--------|--------|
| Cellules | 5 | ✅ |
| VERSION dans cell 2 | `"14.0"` | ✅ |
| `%%writefile /tmp/my_agent.py` | Présent | ✅ |
| `KAGGLE_IS_COMPETITION_RERUN` dans cell 3 | Présent | ✅ |
| gateway sidecar dans cell 3 | Présent | ✅ |
| Dummy parquet dans cell 4 | Présent | ✅ |
| Taille cell 2 (agent) | 114 067 octets | ✅ |

---

## 3. État après déploiement

### Fichiers modifiés (avant/après)

| Fichier | Avant | Après |
|---------|-------|-------|
| `vendor/.../agent/my_agent.py` | VERSION = "13.5", 2616 lignes | VERSION = "14.0", 2600 lignes |
| `vendor/.../notebooks/kernel-metadata.json` | id = lucy-v13-5-... | id = lucy-v14-0-... |
| `vendor/.../notebooks/submission.ipynb` | Agent v13.5 embarqué | Agent v14.0 embarqué |

### Corrections v14.0 présentes dans le notebook

| Fix | Description | Vérification |
|-----|-------------|--------------|
| F-021 | `_to_int_grid_canonical()` source unique | ✅ présent |
| F-022 | Ordre `clear()` avant `add()` dans recovery | ✅ présent |
| F-011 | Graine `random.seed(hash(str(self.game_id)))` | ✅ présent |
| F-019 | Forensic `/tmp/lucy_forensic.jsonl` | ✅ présent |

---

## 4. Prochaines étapes — Instructions utilisateur

### 4.1 Push Kaggle (à exécuter dans `vendor/ARC-AGI-3-Kaggle-Starter/`)

```bash
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter
kaggle kernels push -p notebooks/
```

**URL résultante :** `https://www.kaggle.com/code/ndarray2000/lucy-v14-0-arc-agi-3-hot-fixes-deterministic`

### 4.2 Déclencher le score réel (OBLIGATOIRE)

> ⚠️ **`kaggle kernels push` seul = score 0,00** (commit mode → dummy parquet)
>
> Pour obtenir un score réel, l'utilisateur **doit** :
> 1. Attendre la fin du commit (status COMPLETE, ~5-10 min)
> 2. Aller sur https://www.kaggle.com/code/ndarray2000/lucy-v14-0-arc-agi-3-hot-fixes-deterministic
> 3. Cliquer **"Submit to Competition"** (bouton bleu en haut à droite)
> 4. Attendre ~1h pour le competition rerun
> 5. Le score apparaît dans : https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/submissions

### 4.3 Récupérer les logs forensic après competition rerun

Les logs forensic sont dans `/tmp/lucy_forensic.jsonl` (F-019) — accessibles via Kaggle output après le rerun.

```bash
kaggle kernels output ndarray2000/lucy-v14-0-arc-agi-3-hot-fixes-deterministic -p /tmp/lucy_output_v140/
```

### 4.4 Push git LuCY

```bash
cd LuCY
git add vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py \
        vendor/ARC-AGI-3-Kaggle-Starter/notebooks/submission.ipynb \
        vendor/ARC-AGI-3-Kaggle-Starter/notebooks/kernel-metadata.json \
        rapports/L-061_deploy_v140_notebook_regenere_kaggle_2026-10-20.md \
        logs/
git commit -m "Deploy v14.0: HOT fixes F021/F022/F011/F019 + notebook regenerated (L-061)"
git push origin main
```

---

## 5. Résumé

**État avant cette session :** `my_agent_v140.py` existait localement avec 4 HOT fixes, mais le notebook Kaggle contenait encore v13.5 → aucun score amélioré possible.

**État après cette session :** Notebook régénéré avec v14.0, kernel-metadata mis à jour. Prêt pour `kaggle kernels push` + "Submit to Competition".

**Prochaine session (L-062) :** Lire les logs forensic du rerun v14.0 pour diagnostiquer l'état de la FSM SELECT→PLACE et préparer v14.1.

**CERTIFIED_100=false | unique_human_proven=false | DEBUG=true**
