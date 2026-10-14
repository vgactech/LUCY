# L-030 — LuCY v11.0 : Program Synthesis — Run local 25 jeux

**Date :** 2026-10-15T00:00:00Z  
**Version agent :** v11.0  
**Source :** `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
**Archive :** `LuCY/agent/my_agent_v110.py`  
**Log JSON :** `LuCY/logs/lucy_L030_20261015T000000Z.json`  
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**  
**Espace rapports :** LuCY (L-001→L-030) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Contexte

Le rapport L-029 a confirmé que `levels_completed=0` n'est pas un bug algorithmique mais
un manque de **compréhension sémantique** des règles de puzzle.
V11.0 implémente un moteur de **program synthesis** natif (D-LUCY-001 : sans LLM externe).

---

## 2. Modules implémentés — avant/après v10.0

### Avant (v10.0)

| Module | Description |
|--------|-------------|
| `_GridPerceptor` | Features grille (symétrie, couleurs, complexité) |
| `_EpisodicMemory` | Score par état de grille |
| `_CognitiveEngine` (4 signaux) | mem + prog + div + hint |
| `_KaggleForensicLogger` | Log NS stdout |

### Après (v11.0) — nouveaux modules

| Module | Fichier ligne | Description |
|--------|---------------|-------------|
| `_TransformDetector` | `my_agent.py` ~483 | Détecte ce qui change entre deux frames : fill_delta, colour_shift, mass_bucket, h/v_sym_change, changed_frac → signature compacte |
| `_RuleHypothesizer` | `my_agent.py` ~584 | Accumule (action → sig_key) et calcule la confidence. Confirme une règle quand p≥0.70 ET n≥3 obs |
| `_CrossGameMemory` | `my_agent.py` ~663 | Persiste les règles dans `/tmp/lucy_v11_cross_game.json` — fallback mémoire si /tmp non accessible |
| `_CognitiveEngine` (5 signaux) | `my_agent.py` ~714 | +W_RULE=4.0 × rule_score (signal dominant) |
| Phase `synth` | `my_agent.py` ~1130 | Phase dédiée exploitation des règles confirmées |

### Changements dans `choose_action()`

| Ligne (approx.) | Avant v10.0 | Après v11.0 |
|----------------|-------------|-------------|
| ~1095 | Absent | `_transform_detector.detect()` après chaque action |
| ~1100 | Absent | `_hypothesizer.record(prev_action, sig_key)` |
| ~1107 | Absent | `RULE_CONFIRMED` émis quand p≥0.70 |
| ~1115 | Absent | `_prev_features = features` (stockage pour prochain tour) |
| ~1130 | Absent | Upgrade vers phase `synth` si règles confirmées |
| ~1150 | 3 phases | 4 phases : explore / synth / exploit / recover |

---

## 3. Bug supplémentaire corrigé vs v10.0

### BUG-E1 — `getattr` fallback fantôme sur `on_state_change`

**Contexte :** Dans `choose_action()` v10.0, au traitement de l'état NOT_PLAYED/GAME_OVER :

**Avant (v10.0, ligne ~716) :**
```python
# my_agent.py v10.0 ligne ~716
self._forensic.on_state_change = getattr(
    self._forensic, "on_state_change",
    lambda *a, **kw: None
)
```

**Après (v11.0) :**
```python
# my_agent.py v11.0 — supprimé
# on_state_change n'existe pas dans _KaggleForensicLogger
# Ce getattr ne faisait qu'assigner None à un attribut inutile
```

---

## 4. Résultats du run local (25 jeux)

| Métrique | v10.0 | v11.0 | Δ |
|----------|-------|-------|---|
| Jeux joués | 25/25 | 25/25 | = |
| Erreurs d'exécution | 0 | 0 | = |
| `levels_completed` | 0 | **0** | = |
| Actions/jeu | 79 | 79 | = |
| `cognitive_engine=true` | ✅ | ✅ | = |
| `external_llm=false` | ✅ | ✅ | = |
| Events forensic/jeu | 244 | **320** | +31 % |
| `RULE_CONFIRMED` émis | N/A | **✅ oui** | NOUVEAU |
| `phase=synth` activé | N/A | **✅ oui** | NOUVEAU |
| `TRANSFORM_DETECTED` | N/A | **✅ oui** | NOUVEAU |

### Exemple de règle confirmée (tn36)

```json
{
  "event": "RULE_CONFIRMED",
  "game_id": "tn36",
  "action": "ACTION6",
  "confidence": 0.71,
  "dominant_sig": "fd0.00cs0mb4hssvsscf0.00"
}
```

```
[LuCY] n=10 action=ACTION6 phase=synth levels=0 stuck=0 confirmed_rules=1 avail=['ACTION6']
```

---

## 5. Analyse critique (lecture brute des logs — L-060)

### Ce qui fonctionne

- `TRANSFORM_DETECTED` s'émet correctement à chaque action où `delta > 0`
- `RULE_CONFIRMED` s'émet (confidence 0.71) — le moteur de règles hypothèse fonctionne
- La phase `synth` est activée sur au minimum le jeu `tn36`
- `_CrossGameMemory` sauvegarde dans `/tmp/lucy_v11_cross_game.json` (pas de crash)
- 0 erreur sur 25/25 jeux

### Problème P0 — signature de transformation dégénérée

**Observation brute :** La signature `fd0.00cs0mb4hssvsscf0.00` (fill_delta=0, colour_shift=0,
mass_bucket=4 [neutre], h_sym stable, v_sym stable, changed_frac=0.00) est
**la même pour toutes les actions** dans la quasi-totalité des jeux.

**Conséquence :** Toutes les actions « confirment » la même règle de non-transformation.
Lorsque la phase `synth` s'active et répète l'action confirmée (ex: ACTION6 sur tn36),
cela ne complète pas de niveau car cette action ne fait rien de spécial.

**Cause profonde :** Les puzzles ARC-AGI-3 dans le runner local produisent des changements
de frame très faibles (`changed_frac ≈ 0.00 - 0.005`), en deçà de la résolution
du détecteur de transformations.

### Problème P1 — absence d'accès à l'état objectif

**Root cause finale :** Pour résoudre un puzzle ARC-AGI-3, il faut comparer
l'état courant à l'**état objectif** montré dans les exemples d'entrée/sortie du puzzle.
La structure `FrameData` contient potentiellement des attributs `goal`, `target` ou
des paires d'exemples — **non explorés jusqu'ici**.

---

## 6. Comparaison architecturale v1.0 → v11.0

| Version | Approche | Résultat |
|---------|----------|---------|
| v1.0 – v6.0 | Actions aléatoires, heuristiques basiques | 0/25 |
| v7.0 – v8.0 | UCB1 simple | 0/25 |
| v9.0 | UCB1 amélioré + fingerprint | 0/25 |
| v10.0 | Noyau cognitif (perception + mémoire) | 0/25 |
| **v11.0** | **Program synthesis + règles** | **0/25** |
| **v12.0** | **FrameData goal inspection + goal_delta** | **→ PROCHAINE** |

---

## 7. Prochaine étape recommandée (v12.0)

**Objectif :** Inspecter la structure réelle de `FrameData` pour trouver l'état objectif.

```python
# À investiguer dans v12.0
goal = getattr(latest_frame, "goal", None)
target = getattr(latest_frame, "target", None)
examples = getattr(latest_frame, "examples", None)
puzzle = getattr(latest_frame, "puzzle", None)

# Si un état objectif existe :
goal_delta = _frame_delta(latest_frame.frame, goal_frame)
# Sélectionner l'action qui MINIMISE goal_delta au tour suivant
```

**Logique :** si `goal_delta` passe de 0.8 → 0.5 après action A, alors A est dans la bonne direction.
Répéter l'action qui produit la plus grande réduction de `goal_delta`.

---

## 8. Commits

| Fichier | Action |
|---------|--------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | MODIFIÉ → v11.0 |
| `agent/my_agent_v110.py` | CRÉÉ (archive) |
| `logs/lucy_L030_20261015T000000Z.json` | CRÉÉ |
| `rapports/L-030_lucy_v110_program_synthesis_run_2026-10-15.md` | CRÉÉ (ce fichier) |

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**
