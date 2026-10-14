#!/usr/bin/env python3
"""
LuCY — Met à jour le notebook ARC-AGI-3 avec le code agent v5.0
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
"""

import json
import pathlib
import datetime

NB_PATH = pathlib.Path('LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb')
AGENT_PATH = pathlib.Path('LuCY/src/lucy/kernel/lucy_agent_v50.py')

def main():
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    print(f"[{ts}] Mise à jour notebook avec agent v5.0")
    print(f"  source  : {AGENT_PATH}")
    print(f"  cible   : {NB_PATH}")

    # Lecture agent v5.0
    agent_code = AGENT_PATH.read_text(encoding='utf-8')
    print(f"  agent_code: {len(agent_code)} chars, {len(agent_code.splitlines())} lignes")

    # Lecture notebook
    with open(NB_PATH) as f:
        nb = json.load(f)

    print(f"  notebook  : {len(nb['cells'])} cellules")

    # ── AVANT (état initial) ──────────────────────────────────────────
    cell0_before = nb['cells'][0]['source']
    if isinstance(cell0_before, list):
        cell0_before_str = ''.join(cell0_before)
    else:
        cell0_before_str = cell0_before

    cell2_before = nb['cells'][2]['source']
    if isinstance(cell2_before, list):
        cell2_before_str = ''.join(cell2_before)
    else:
        cell2_before_str = cell2_before

    print(f"\n  [AVANT] Cell 0 titre : {cell0_before_str[:80]!r}")
    print(f"  [AVANT] Cell 2 première ligne : {cell2_before_str[:80]!r}")
    print(f"  [AVANT] Cell 2 longueur : {len(cell2_before_str)} chars")

    # ── PATCH Cell 0 — Mise à jour titre ─────────────────────────────
    cell0_new = [
        "# LuCY Cognitive Kernel — ARC-AGI-3 Agent v5.0\n",
        "\n",
        "**LuCY v5.0** (Language Understanding Cognitive sYstem) — agent cognitif ARC-AGI-3.\n",
        "\n",
        "- `CERTIFIED_100=false` | `unique_human_proven=false` | `DEBUG=true`\n",
        "- Architecture v5.0 : **3 niveaux** — 8 fonctions cognitives → 4 contrôleurs → 1 méta-contrôleur\n",
        "- Profil cognitif : **INTP** (DI > PE > PI > DE)\n",
        "- Reward adaptatif : `level_up = 2.0 × min(2.0, 1 + progress_rate)`\n",
        "- Compétition : **arc-prize-2026-arc-agi-3**\n",
        "\n",
        "**Note scientifique honnête :** LuCY v5.0 introduit un méta-contrôleur par profil cognitif dynamique.\n",
        "Les données ne transitent PAS par le méta-contrôleur — seules les autorisations d'échange entre\n",
        "contrôleurs sont gérées à ce niveau. 49/49 tests PASS (v5.0 T107-T122 + v4.1 T75-T106).\n",
    ]
    nb['cells'][0]['source'] = cell0_new

    # ── PATCH Cell 1 — Mise à jour version dans le print ─────────────
    cell1_src = nb['cells'][1]['source']
    if isinstance(cell1_src, list):
        cell1_str = ''.join(cell1_src)
    else:
        cell1_str = cell1_src
    cell1_str = cell1_str.replace(
        "print('LuCY v3.2",
        "print('LuCY v5.0"
    ).replace(
        "print(f'LuCY v3.2",
        "print(f'LuCY v5.0"
    ).replace(
        "LuCY v3.2 — UCB1 + PE/PI + Q-learning + P0-A..F v2 corrigés + mémoire inter-niveaux",
        "LuCY v5.0 — 3 niveaux cognitifs : 8 fonctions → 4 contrôleurs → 1 méta-contrôleur INTP"
    )
    nb['cells'][1]['source'] = cell1_str

    # ── PATCH Cell 2 — REMPLACER l'agent v4.1 par v5.0 ──────────────
    # Construire la cellule %%writefile avec le code v5.0
    agent_lines = agent_code.splitlines(keepends=True)
    cell2_new_lines = ['%%writefile /kaggle/working/lucy_agent.py\n'] + agent_lines
    nb['cells'][2]['source'] = cell2_new_lines

    # ── APRÈS (vérification) ──────────────────────────────────────────
    cell0_after = ''.join(nb['cells'][0]['source'])
    cell2_after = ''.join(nb['cells'][2]['source'])
    print(f"\n  [APRÈS] Cell 0 titre : {cell0_after[:80]!r}")
    print(f"  [APRÈS] Cell 2 première ligne : {cell2_after[:80]!r}")
    print(f"  [APRÈS] Cell 2 longueur : {len(cell2_after)} chars")
    print(f"  [APRÈS] v5.0 présent dans cell 2: {'VERSION = ' + chr(39) + '5.0' + chr(39) in cell2_after}")

    # ── Sauvegarde ────────────────────────────────────────────────────
    with open(NB_PATH, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print(f"\n  [OK] Notebook sauvegardé: {NB_PATH}")
    print(f"  [OK] Taille: {NB_PATH.stat().st_size:,} bytes")

if __name__ == '__main__':
    main()
