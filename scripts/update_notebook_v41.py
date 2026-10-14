"""
update_notebook_v41.py — Met à jour le notebook arc3 avec le code agent v4.1.
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Corrections appliquées vs v4.0 :
  FIX-1 (P0-G) : attribution temporelle corrigée — pi.update(prev_sid_colors)
  FIX-2 (P0-J) : persistance cognitive COMPLÈTE (q_table + n_sa + n_s + color_action_rewards)
"""
import json
from pathlib import Path

NB_PATH = Path('LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb')
AGENT_SRC = Path('LuCY/src/lucy/kernel/lucy_agent_v41.py')

# Lire le notebook existant
with open(NB_PATH) as f:
    nb = json.load(f)

# Lire le code source v4.1
with open(AGENT_SRC) as f:
    agent_code_raw = f.read()

# -----------------------------------------------------------------
# Cell 0 — Titre markdown v4.1
# -----------------------------------------------------------------
nb['cells'][0]['source'] = [
    "# LuCY Cognitive Kernel — ARC-AGI-3 Agent v4.1\n",
    "\n",
    "**LuCY v4.1** (Language Understanding Cognitive sYstem) — agent cognitif ARC-AGI-3.\n",
    "\n",
    "- `CERTIFIED_100=false` | `unique_human_proven=false` | `DEBUG=true`\n",
    "- Architecture : 10 opérateurs cognitifs (SE/SI/NE/NI/TE/TI/FE/FI + PE/PI) + Arbitrateur\n",
    "- **FIX-1 (P0-G)** : attribution temporelle corrigée — `pi.update(prev_sid_colors)` au lieu de `curr_sid_colors`\n",
    "- **FIX-2 (P0-J)** : persistance cognitive COMPLÈTE — `q_table + n_sa + n_s + color_action_rewards`\n",
    "- Héritage v4.0 : P0-H (click centroïde), P0-I (stuck reset complet)\n",
    "- Héritage v3.2 : P0-A..P0-F v2 (UCB1, hash, reward, tri, patterns, Q-learning)\n",
    "- Compétition : **arc-prize-2026-arc-agi-3**\n",
    "\n",
    "**Note scientifique honnête :** LuCY v4.1 corrige 2 défauts résiduels de v4.0.\n",
    "FIX-1 : la mémoire couleur P0-G était associée à l'état RÉSULTANT (incohérent) — corrigée vers l'état SOURCE.\n",
    "FIX-2 : seul game_patterns était persisté entre runs — désormais snapshot cognitif complet.\n",
    "16 tests T91-T106 PASS + 16 tests T75-T90 non-régression.\n",
]

# -----------------------------------------------------------------
# Cell 2 — Réécrire avec le code v4.1 via %%writefile
# -----------------------------------------------------------------
code_lines = agent_code_raw.split('\n')
cell2_lines = ['%%writefile /kaggle/working/lucy_agent.py\n']
for line in code_lines:
    cell2_lines.append(line + '\n')

nb['cells'][2]['source'] = cell2_lines
nb['cells'][2]['cell_type'] = 'code'
nb['cells'][2]['execution_count'] = None
nb['cells'][2]['metadata'] = {}
nb['cells'][2]['outputs'] = []

# -----------------------------------------------------------------
# Écrire le notebook mis à jour
# -----------------------------------------------------------------
with open(NB_PATH, 'w') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"[OK] Notebook mis à jour: {NB_PATH}")
print(f"     Cells: {len(nb['cells'])}")
print(f"     Cell 2 (lucy_agent.py v4.1): {len(cell2_lines)} lignes")
print(f"     Taille: {NB_PATH.stat().st_size:,} bytes")
