# L-043 — Audit r11l : réponses aux 4 points ouverts (A/B/C/D)

**Date :** 2026-10-16  
**Source audit :** Rapport utilisateur (suite L-036 / L-042)  
**Espace de numérotation :** LuCY (`L-xxx`) — distinct de ARTCB (`R-xxx`)  
**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

---

## 0. Contexte

Ce rapport répond aux quatre questions laissées ouvertes dans l'audit utilisateur
après L-036 :

- **A** — Budget interne 60 actions du moteur r11l et interaction avec le budget LuCY (200)
- **B** — Les 256 coordonnées ACTION6 : balayage efficace ou aléatoire ? Les sprites bougent-ils entre clics ?
- **C** — Que se passe-t-il exactement à la 60e action moteur ?
- **D** — FrameData accessible à LuCY : positions des sprites (`bbijaigbknc`) et cibles (`kacotwgjcyq`) visibles ?

Chaque réponse s'appuie sur la lecture directe du code source et sur les données
réelles du log `lucy_C005_r11l_500steps_20261015T221124Z.log` (199 actions,
3 GAME_OVER observés).

---

## 1. Point A — Budget interne 60 vs budget LuCY 200

### Processus

Le moteur `R11l` maintient son propre compteur indépendant :

```python
# r11l.py ligne 1407
self._max_actions = 60
```

```python
# r11l.py lignes 1807–1812
def step(self) -> None:
    tffqfkxdpf = self._max_actions - self._action_count
    self._step_counter_ui.xfolsippxk(tffqfkxdpf)
    if self._action_count >= self._max_actions:
        self.lose()
        self.complete_action()
        return
```

LuCY maintient son propre compteur global :

```python
# my_agent_v121.py ligne 88
MAX_ACTIONS_TOTAL = 200
```

### Résultat mesuré (log C005)

Les `GAME_OVER` apparaissent aux actions LuCY numéros **61, 122, 183** :

```
RESET reason=state_GAME_OVER action_count=61  budget_remaining=139
RESET reason=state_GAME_OVER action_count=122 budget_remaining=78
RESET reason=state_GAME_OVER action_count=183 budget_remaining=17
```

Soit exactement 3 cycles de 60/61 actions moteur sur 199 actions LuCY totales.

### Conclusion A

Les deux budgets sont **complètement indépendants**. Le moteur r11l réinitialise
le jeu tous les 60 steps moteur, ce qui correspond à ~61 actions LuCY (la
première action initialise le niveau). LuCY ne sait pas que le moteur a un
budget interne : elle voit simplement `state=GAME_OVER` → RESET, puis repart
de zéro. Sur 199 actions totales, le jeu s'est donc répété 3 fois complet +
un fragment d'un 4e cycle.

**Problème identifié** : chaque RESET efface la mémoire `_rule_memory`,
`_memory`, `_prev_fp` etc. (lignes 1151–1165 my_agent_v121.py). LuCY
recommence l'exploration depuis le début à chaque fois — aucun apprentissage
inter-cycles.

---

## 2. Point B — Balayage ACTION6 : aléatoire ou cohérent ?

### Code source (my_agent_v121.py lignes 1405–1413)

```python
# ── Complex action (ACTION6) coordinate selection ─────────────────
if action.is_complex():
    active_ratio = features.get("active_ratio", 0.5)
    if features.get("grid_valid", False) and active_ratio < 0.5:
        x = random.randint(20, 44)
        y = random.randint(20, 44)
    else:
        x = random.randint(0, 63)
        y = random.randint(0, 63)
    action.set_data({"x": x, "y": y})
```

### Analyse

LuCY choisit les coordonnées **aléatoirement** dans l'un de deux sous-espaces :
- Grille partielle (`grid_valid=True` et `active_ratio<0.5`) : zone centrale 20–44 × 20–44
- Sinon : espace complet 0–63 × 0–63

Le moteur r11l construit 256 positions pré-calculées (`jtqexauuzid`) au pas
de 4 (lignes 1416–1419), mais LuCY n'utilise **pas** cette liste. Elle tire
ses coordonnées avec `random.randint`, non aligné sur la grille 4×4.

Concernant les sprites : dans `step()` (ligne 1826–1830), le moteur identifie
si la position cliquée tombe **à l'intérieur** d'un sprite (`bbijaigbknc[i]`).
Si LuCY clique aléatoirement hors de tout sprite, la branche `elif self.wiayqaumjug`
déplace le sprite actuellement sélectionné. Si LuCY clique sur un sprite,
elle le sélectionne.

**Les sprites bougent-ils entre clics ?** Oui — `hcpsunmfnx()` déplace
le sprite sélectionné vers la position cliquée. C'est une animation multi-step
(`yfbjozweime=True`, lignes 1814–1818) qui consomme plusieurs `step()` sans
incrémenter `_action_count` côté LuCY.

### Mesure des changements visuels (log C005)

Sur 590 événements ACTION6 enregistrés :
- Frames comparables : **194**
- Avec changement visuel : **194** (100 % des frames comparables)
- `net_change=+3` : **121 fois** (sprite en mouvement, +3 pixels nets)
- `net_change<0` : **6 fois** (shrink ou déplacement partiel)
- `net_change` moyen : **+1.64 pixels**

Note : 590 events ≠ 199 actions LuCY car certaines actions déclenchent plusieurs
frames de rendu (animation en cours, `yfbjozweime=True`).

### Conclusion B

LuCY clique **aléatoirement** dans l'espace 64×64 — pas de balayage systématique,
pas de ciblage des sprites. La probabilité de cliquer sur un sprite dépend
de la surface occupée par les sprites dans la grille (typiquement < 5 %
de la surface totale). La très grande majorité des clics sélectionne un
mouvement du sprite actif vers une position aléatoire, sans jamais le diriger
vers sa cible.

---

## 3. Point C — Comportement exact à la 60e action moteur

### Code source

```python
# arcengine/base_game.py lignes 301–304
def lose(self) -> None:
    """Call this when the player has losses the game."""
    self._state = GameState.GAME_OVER

# r11l.py lignes 1809–1812
if self._action_count >= self._max_actions:
    self.lose()
    self.complete_action()
    return
```

### Chaîne complète

1. À la 60e action moteur : `self.lose()` → `_state = GAME_OVER`
2. `self.complete_action()` → `_action_complete = True` (signal au runner)
3. Le runner lit le `FrameData` avec `state = GAME_OVER`
4. LuCY reçoit ce `FrameData` dans `choose_action()` ligne 1151 :
   ```python
   if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
       ...
       return GameAction.RESET
   ```
5. LuCY retourne `GameAction.RESET` → le moteur appelle `handle_reset()` →
   `level_reset()` → le niveau est restauré proprement.

### Ce qui n'est PAS un game over définitif

`lose()` ne bloque pas le jeu définitivement. `handle_reset()` détecte
`_state != WIN` et `_action_count != 0` → `level_reset()`. Les sprites,
positions et progression sont réinitialisés. C'est une pénalité de temps,
pas une élimination.

### Conclusion C

À la 60e action moteur, le jeu déclenche un `GAME_OVER` temporaire qui force
LuCY à RESET. **Cela réinitialise toute la mémoire de LuCY** pour ce cycle.
LuCY repart depuis l'action 1 du niveau sans conserver les coordonnées testées,
les règles apprises ou les associations sprite→victoire.

---

## 4. Point D — FrameData : positions des sprites visibles par LuCY ?

### Définition officielle de FrameData

```python
# arcengine/enums.py lignes 131–141
class FrameData(BaseModel):
    game_id: str = ""
    frame: list[list[list[int]]] = []      # pixels rendu (SEULE INFO VISUELLE)
    state: GameState = GameState.NOT_PLAYED
    levels_completed: int = Field(0, ge=0, le=254)
    win_levels: int = Field(0, ge=0, le=254)
    action_input: ActionInput = Field(...)
    guid: Optional[str] = None
    full_reset: bool = False
    available_actions: list[int] = []
```

### Ce que r11l expose vs ce qu'il garde interne

Les attributs du moteur `R11l` :
- `bbijaigbknc: list[Sprite]` — positions des sprites mobiles → **INTERNE**
- `kacotwgjcyq: dict[str, ...]` — dictionnaire sprite/cible → **INTERNE**
- `wiayqaumjug: Sprite | None` — sprite actuellement sélectionné → **INTERNE**

Ces attributs ne sont **jamais** inclus dans `FrameData`. Ils restent dans
l'état privé de l'objet `R11l`.

### Ce que LuCY reçoit réellement

LuCY reçoit uniquement :
1. `frame` — le rendu pixels 3×64×64 (3 canaux RGB ou équivalent)
2. `state` — NOT_PLAYED / NOT_FINISHED / WIN / GAME_OVER
3. `levels_completed` — nombre de niveaux terminés (toujours 0 pour r11l)
4. `win_levels` — nombre total de niveaux du jeu (6)
5. `available_actions` — `[6]` constant

Pour inférer les positions des sprites, LuCY doit les déduire **visuellement**
depuis `frame`. Or `_perceptor.extract()` (ligne 1229) calcule des features
de bas niveau (`active_ratio`, `grid_valid`, etc.) — il ne fait pas de
détection de sprites.

### Implication directe

LuCY clique aléatoirement parce qu'elle **ne peut pas lire** les positions
des sprites. Le seul moyen de cibler un sprite est d'analyser les pixels
(`frame`) pour détecter sa position. Cela n'est pas implémenté.

---

## 5. Synthèse des 4 points

| Point | Question | Réponse |
|-------|----------|---------|
| **A** | Budget moteur 60 vs LuCY 200 | Deux compteurs indépendants. Moteur → GAME_OVER tous les 60 steps. LuCY RESET et efface sa mémoire. 3 cycles complets sur 199 actions. |
| **B** | Balayage des 256 positions ACTION6 | Non — coordonnées tirées aléatoirement dans 0–63. Pas de balayage systématique. Probabilité de toucher un sprite < 5 % par action. Sprites en mouvement ≠ progression vers victoire. |
| **C** | Comportement à la 60e action | `lose()` → GAME_OVER → `complete_action()` → LuCY voit GAME_OVER → RESET → `level_reset()`. Cycle propre, pas de blocage définitif. |
| **D** | Positions sprites dans FrameData | **Absent.** `bbijaigbknc` et `kacotwgjcyq` sont internes au moteur. LuCY ne reçoit que les pixels bruts. Ciblage sprites = inférence visuelle non implémentée. |

---

## 6. Conséquences sur les 5 lacunes

| Lacune | Impact des points A/B/C/D |
|--------|--------------------------|
| **T-01 — Condition de victoire** | Toujours ouverte — la condition nécessite collision simultanée de TOUTES les paires sprite↔cible. LuCY ne peut pas la vérifier sans les positions. |
| **T-02 — Budget d'actions** | Point A confirme : 60 steps moteur par cycle → 3 cycles en 199 actions. 500 actions = ~8 cycles complets, mais sans mémoire inter-cycles. |
| **T-03 — Famille de mécaniques** | r11l = jeu de ciblage par clics successifs sur grille 64×64. Requiert détection visuelle ou liste coordonnées efficace. |
| **T-04 — Action unique** | Point B confirme : ACTION6 avec coordonnées aléatoires ≠ stratégie ciblée. L'agent répète l'action sans progression. |
| **T-05 — Version agent** | Confirmé ligne 1413 : `action.set_data({"x": x, "y": y})` — même comportement dans `vendor/agent/my_agent.py` et `LuCY/agent/my_agent_v121.py`. |

---

## 7. Recommandations priorisées

### P0 — Résoudre le problème fondamental (T-01 + T-04)

**Avant d'augmenter le budget**, résoudre la stratégie :

1. **Inférence visuelle des sprites** : analyser `frame` pour détecter les
   blobs colorés → extraire leur centre → cibler systématiquement.
2. **Balayage systématique** : remplacer `random.randint` par un balayage
   grille 64×64 pas 4 (aligné sur les 256 positions du moteur).
3. **Persistance inter-cycles** : conserver les coordonnées efficaces entre
   les RESET moteur (le GAME_OVER ne doit pas effacer la mémoire de ciblage).

### P1 — Test 500 actions

Pertinent uniquement **après** que la stratégie de ciblage est corrigée.
Sans correction, 500 actions = 8 cycles aléatoires → même résultat que 199.

---

## 8. Avant / Après (traçabilité)

| Fichier | Ligne | Avant (hypothèse L-042) | Après (vérifié L-043) |
|---------|-------|------------------------|----------------------|
| `r11l.py` | 1807–1812 | Budget moteur 60 : détail inconnu | `lose()` → GAME_OVER → `complete_action()` → RESET LuCY → `level_reset()` |
| `arcengine/enums.py` | 131–140 | FrameData : contenu supposé | 8 champs uniquement, **aucune position sprite** |
| `my_agent_v121.py` | 1405–1413 | Ciblage : supposé aléatoire | Confirmé : `random.randint(0,63)` — aucun ciblage sprite |
| Log C005 | ligne GAME_DONE | 165/199 changements (L-042) | 194/194 frames comparables changent. 590 events ≠ 199 actions (animations multi-step) |

---

*Rapport L-043 — Lu intégralement avant rédaction. Aucun rapport précédent modifié.*  
*Prochaine action : commit + push, puis exécuter test 500 actions avec stratégie de ciblage corrigée si GO.*
