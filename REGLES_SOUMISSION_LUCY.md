# RÈGLES DE SOUMISSION LUCY — ARC-AGI-3 Kaggle

**Fichier permanent — APPEND ONLY — ne jamais supprimer une règle existante.**  
**Chaque règle est horodatée et identifiée. Les violations réelles sont documentées.**  
**CERTIFIED_100=false | unique_human_proven=false | DEBUG=true**

---

## RÈGLE R-001 — Deux modes Kaggle distincts (2026-10-16)

**Source :** L-056 + L-057  
**Violation déclenchante :** v13.5 soumise via `kaggle kernels push` seul → score 0.00.

| Mode | Déclencheur | Variable | Comportement notebook |
|------|-------------|----------|----------------------|
| **Commit** | `kaggle kernels push` | `KAGGLE_IS_COMPETITION_RERUN` absent | Cellule 5 → dummy parquet → **SCORE 0** |
| **Competition Rerun** | "Submit to Competition" (UI Kaggle) | `KAGGLE_IS_COMPETITION_RERUN = 1` | Gateway → agent joue → score réel |

**RÈGLE ABSOLUE :** `kaggle kernels push` seul = score 0.00 GARANTI.  
Pour un score réel, l'utilisateur DOIT cliquer "Submit to Competition" sur l'interface Kaggle APRÈS le push.

---

## RÈGLE R-002 — Pipeline de déploiement v1 → v2 (2026-10-20)

**Source :** L-061  
**Violation déclenchante :** `my_agent_v140.py` créé localement mais le notebook Kaggle contenait encore v13.5.

Le chemin de mise à jour est :
```
LuCY/agent/my_agent_vXX.py
    → cp → LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py
    → python3 scripts/build_notebook.py   (régénère submission.ipynb)
    → modifier kernel-metadata.json (id + title)
    → kaggle kernels push -p notebooks/
    → [UTILISATEUR] cliquer "Submit to Competition" sur Kaggle UI
```

**JAMAIS** modifier directement le notebook `submission.ipynb` — il est généré automatiquement.  
**TOUJOURS** vérifier `VERSION = "XX.Y"` dans `vendor/.../agent/my_agent.py` APRÈS la copie.  
**TOUJOURS** vérifier que le notebook contient la bonne version via `grep -o '"XX.Y"' submission.ipynb`.

---

## RÈGLE R-003 — Tester localement avant push (2026-10-21)

**Source :** L-062 (F-023 NameError détecté uniquement par test local)  
**Violation déclenchante :** v14.0 pushée sans tester localement → NameError crash au 1er `choose_action()`.

**AVANT chaque push Kaggle, exécuter obligatoirement :**
```bash
cd LuCY/vendor/ARC-AGI-3-Kaggle-Starter
.venv/bin/python3 scripts/play_local.py --game ls20 --max-steps 15 2>&1 | grep -E "LuCY v|ERROR|Traceback|NameError|GAME_DONE"
```
Si la sortie contient `ERROR`, `Traceback`, `NameError`, ou n'affiche pas `LuCY vXX.Y` → **NE PAS POUSSER**.

---

## RÈGLE R-004 — Vérification des noms de fonctions après refactoring (2026-10-21)

**Source :** L-062 (F-023)  
**Violation déclenchante :** `_validate_transposition()` renommée en `_validate_transposition_regression()` en v13.1,
mais l'appel ligne 2279 n'avait pas été mis à jour → NameError.

**APRÈS tout renommage de fonction :**
```bash
grep -n "OLD_NAME" LuCY/agent/my_agent_vXX.py
```
Si des résultats apparaissent en dehors de la définition et des commentaires `AVANT/APRÈS` → **BUG À CORRIGER AVANT PUSH**.

---

## RÈGLE R-005 — Chaque nouvelle version = nouveau kernel-metadata.json (2026-10-21)

**Source :** L-062  
Un kernel Kaggle avec le même `id` ne peut pas être soumis deux fois à une même compétition pour des scores distincts.  
**À chaque version :** changer `id` ET `title` dans `kernel-metadata.json`.

Format recommandé :
```json
"id": "ndarray2000/lucy-vXX-Y-arc-agi-3-description-courte",
"title": "LuCY vXX.Y ARC-AGI-3 Description"
```

---

## RÈGLE R-006 — Scores de référence à battre (2026-10-21)

**Source :** L-008 / L-023 / L-056

| Agent | Score | Priorité |
|-------|-------|----------|
| Random Agent | 0.18 | **Seuil minimum absolu** |
| Just Explore | 0.19 | Objectif court terme |
| Stochastic Goose | 0.25 | Objectif moyen terme |
| LuCY v7.0 | 0.14 | Score personnel référence |

**Un agent qui crashe (NameError, Exception non attrapée) = score 0.00 — pire que Random.**  
La priorité absolue est : **le code ne doit jamais crasher** avant d'optimiser les stratégies.

---

## RÈGLE R-007 — Logs forensic Kaggle : où les trouver (2026-10-21)

**Source :** L-056 + L-062  
En competition rerun, l'agent écrit dans `/tmp/lucy_forensic.jsonl` (FIX-F019).  
Ces logs sont accessibles via :
```bash
kaggle kernels output ndarray2000/lucy-vXX-Y-description -p /tmp/lucy_output_vXX/
```
Les logs stdout de l'agent sont dans les logs du kernel (Kaggle UI → kernel → Logs tab).  
**ATTENTION :** `kaggle kernels output` récupère les outputs du dernier **commit run**, PAS du competition rerun.

---

## RÈGLE R-008 — is_done() doit inclure WIN explicitement (2026-10-21)

**Source :** agent.py référence (random_agent.py)  
L'agent de base Kaggle utilise :
```python
def is_done(self, frames, latest_frame):
    return any([latest_frame.state is GameState.WIN])
```
Notre agent v14.x gère WIN + BUDGET_EXHAUSTED. **Ne jamais supprimer la détection WIN.**

---

## RÈGLE R-009 — Graine déterministe (2026-10-21)

**Source :** FIX-HOT-F011  
`random.seed(hash(str(self.game_id)))` — déterministe par game_id.  
**Ne jamais revenir** à `random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))` — viole P5 CDC (reproductibilité).

---

## Historique des violations

| Date | Version | Violation | Impact | Correction |
|------|---------|-----------|--------|-----------|
| 2026-10-16 | v13.5 | Push sans "Submit to Competition" | Score 0.00 | R-001 |
| 2026-10-20 | v14.0 | notebook non régénéré après création agent | Score v13.5 au lieu de v14.0 | R-002 |
| 2026-10-21 | v14.0 | `_validate_transposition()` NameError non testé | Score 0.00 (crash au 1er step) | R-003 + R-004 |
