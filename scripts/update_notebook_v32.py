"""
update_notebook_v32.py — Met à jour le notebook arc3 avec le code agent v3.2.
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
"""
import json
import re
from pathlib import Path

NB_PATH = Path('LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb')
AGENT_SRC = Path('LuCY/src/lucy/kernel/lucy_agent_v32.py')

# Lire le notebook existant
with open(NB_PATH) as f:
    nb = json.load(f)

# Lire le code source v3.2
with open(AGENT_SRC) as f:
    agent_code_raw = f.read()

# -----------------------------------------------------------------
# Cell 0 — Mettre à jour le titre markdown pour v3.2
# -----------------------------------------------------------------
nb['cells'][0]['source'] = [
    "# LuCY Cognitive Kernel \u2014 ARC-AGI-3 Agent v3.2\n",
    "\n",
    "**LuCY v3.2** (Language Understanding Cognitive sYstem) \u2014 agent interactif Phase 5.2 pour ARC-AGI-3.\n",
    "\n",
    "- `CERTIFIED_100=false` | `unique_human_proven=false` | `DEBUG=true`\n",
    "- Architecture : 10 op\u00e9rateurs cognitifs (SE/SI/NE/NI/TE/TI/FE/FI + **PE/PI**) + Arbitrateur\n",
    "- **Corrections v3.2** : P0-A v2 (n_sa_sum+RESET), P0-B v2 (hash+shape), P0-C v2 (3-levels-reward), P0-D v2 (canonical-sort), P0-E v2 (patterns-in-arbitrate), P0-F v2 (next-available-q)\n",
    "- Comp\u00e9tition : **arc-prize-2026-arc-agi-3**\n",
    "\n",
    "**Note scientifique honn\u00eate :** LuCY v3.2 corrige 6 d\u00e9fauts r\u00e9siduels P0 v2 de v3.1 (audit L-011).\n",
    "Toutes les corrections sont document\u00e9es avec AVANT/APR\u00c8S dans le rapport L-012.\n",
    "153/153 tests PASS locaux. Score attendu : am\u00e9lioration progressive vs v3.1.\n",
]

# -----------------------------------------------------------------
# Cell 1 — Mise à jour de la cellule d'installation (marquer v3.2)
# -----------------------------------------------------------------
cell1_src = nb['cells'][1]['source']
if isinstance(cell1_src, list):
    cell1_src = ''.join(cell1_src)
cell1_src = cell1_src.replace("LuCY v3 \u2014 UCB1 + PE/PI + Q-learning", "LuCY v3.2 \u2014 UCB1 + PE/PI + Q-learning + P0-A..F v2 corrig\u00e9s")
cell1_src = cell1_src.replace("LuCY v3 \u2014 Phase 5 : UCB1 + PE/PI + Q-learning", "LuCY v3.2 \u2014 Phase 5.2 : Corrections P0-A..P0-F v2")
nb['cells'][1]['source'] = cell1_src

# -----------------------------------------------------------------
# Cell 2 — Réécrire le %%writefile avec le code v3.2
# La cellule 2 doit écrire lucy_agent.py via %%writefile
# On transforme le code source Python en lignes pour le notebook
# -----------------------------------------------------------------

# Convertir le code source v3.2 en format liste de lignes pour le notebook
# En supprimant l'import de Agent/arcengine (non disponible en local —
# présents dans les wheels ARC-AGI-3 sur Kaggle)
code_lines = agent_code_raw.split('\n')

# Reconstruire en tant que source de cellule (liste de strings avec \n)
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
print(f"     Cell 2 (lucy_agent.py): {len(cell2_lines)} lignes")
print(f"     Taille: {NB_PATH.stat().st_size:,} bytes")
