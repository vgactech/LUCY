"""
Generate lucy_arc_agi3_submission.ipynb from the ARC-AGI-2 notebook
with competition_sources adapted for arc-prize-2026-arc-agi-3.
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
"""

import json
from pathlib import Path

# Load original ARC-AGI-2 notebook
src = Path('LuCY/notebooks/lucy_arc_agi_submission.ipynb')
with open(src) as f:
    nb = json.load(f)

# ----------------------------------------------------------------
# Patch Cell 0 (markdown title)
# ----------------------------------------------------------------
nb['cells'][0]['source'] = [
    "# LuCY Kernel — ARC-AGI-3 Submission\n",
    "\n",
    "**LuCY** (Language Understanding Cognitive sYstem) — cognitive kernel evaluation on ARC-AGI-3 puzzles.\n",
    "\n",
    "- CERTIFIED_100=false | unique_human_proven=false | DEBUG=true\n",
    "- Architecture: 8 cognitive operators (SE/SI/NE/NI/TE/TI/FE/FI) + Arbitrator\n",
    "- Strategy: Each ARC puzzle is encoded as a structured text stimulus\n",
    "- Output: Predicted output grids based on cognitive pattern analysis\n",
    "- Competition: **arc-prize-2026-arc-agi-3**\n",
    "\n",
    "**Note scientifique honnête:** LuCY Phase 4 est un moteur de raisonnement cognitif symbolique.\n",
    "Les puzzles ARC-AGI-3 nécessitent de la reconnaissance de motifs visuels/abstraits que les 8 opérateurs\n",
    "actuels ne modélisent pas encore directement. Ce notebook documente le comportement réel du kernel.\n",
]

# ----------------------------------------------------------------
# Patch Cell 1 (add ARC3 competition marker)
# ----------------------------------------------------------------
cell1_src = ''.join(nb['cells'][1]['source'])
# Update the print line to show ARC-AGI-3
cell1_src = cell1_src.replace(
    'print(f"LuCY ARC-AGI Submission — {EVAL_TS}")',
    'print(f"LuCY ARC-AGI-3 Submission — {EVAL_TS}")\nCOMPETITION = "arc-prize-2026-arc-agi-3"'
)
nb['cells'][1]['source'] = cell1_src

# ----------------------------------------------------------------
# Patch Cell 2 — dataset discovery for ARC-AGI-3 specifically
# ----------------------------------------------------------------
cell2_new = '''\
# ============================================================
# CELL 2 — Locate ARC-AGI-3 dataset files
# ============================================================
import glob

# Kaggle competition datasets are mounted at /kaggle/input/
INPUT_DIR = Path('/kaggle/input')
COMPETITION_ID = "arc-prize-2026-arc-agi-3"

# Search for ARC-AGI-3 specific test files first
test_files = (
    list(INPUT_DIR.rglob('arc_agi_3_test_challenges.json')) +
    list(INPUT_DIR.rglob('arc-agi-3-test-challenges.json')) +
    list(INPUT_DIR.rglob('*arc*3*test*.json')) +
    list(INPUT_DIR.rglob('*test*challenges*.json'))
)

# Also look for sample submission
sample_files = (
    list(INPUT_DIR.rglob('sample_submission*.csv')) +
    list(INPUT_DIR.rglob('sample_submission*.json'))
)

print("=== Input directory contents ===")
for p in sorted(INPUT_DIR.rglob('*')):
    if p.is_file():
        size = p.stat().st_size
        print(f"  {p.relative_to(INPUT_DIR)} ({size:,} bytes)")

print(f"\\nTest files found: {len(test_files)}")
for f in test_files:
    print(f"  {f}")

print(f"\\nSample submission files found: {len(sample_files)}")
for f in sample_files:
    print(f"  {f}")
'''
nb['cells'][2]['source'] = cell2_new

# ----------------------------------------------------------------
# Patch Cell 3 — load_test_puzzles: prioritize ARC-AGI-3 paths
# ----------------------------------------------------------------
cell3_old = ''.join(nb['cells'][3]['source'])
cell3_new = cell3_old.replace(
    "candidate_paths = [\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'arc_agi_3_test_challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-2' / 'arc_agi_2_test_challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-2' / 'arc-agi-2-test-challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'arc-agi-3-test-challenges.json',\n"
    "    ]",
    "candidate_paths = [\n"
    "        # ARC-AGI-3 paths (priority)\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'arc_agi_3_test_challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'arc-agi-3-test-challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'test_challenges.json',\n"
    "        input_dir / 'arc-prize-2026-arc-agi-3' / 'test.json',\n"
    "        # Generic fallback\n"
    "        input_dir / 'arc-prize-2026-arc-agi-2' / 'arc_agi_2_test_challenges.json',\n"
    "    ]"
)
nb['cells'][3]['source'] = cell3_new

# ----------------------------------------------------------------
# Patch Cell 7 — update forensic summary for ARC-AGI-3
# ----------------------------------------------------------------
cell7_old = ''.join(nb['cells'][7]['source'])
cell7_new = cell7_old.replace(
    'print("LuCY ARC-AGI Evaluation Summary")',
    'print("LuCY ARC-AGI-3 Evaluation Summary")'
)
cell7_new = cell7_new.replace(
    'print(f"submission.json: {len(submission)} puzzles — ready for evaluation")',
    'print(f"submission.json: {len(submission)} puzzles — ready for ARC-AGI-3 evaluation")\n'
    'print(f"Competition: arc-prize-2026-arc-agi-3")'
)
nb['cells'][7]['source'] = cell7_new

# ----------------------------------------------------------------
# Write output notebook
# ----------------------------------------------------------------
out = Path('LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb')
with open(out, 'w') as f:
    json.dump(nb, f, indent=1)

print(f"[OK] Notebook written: {out}")
print(f"     Cells: {len(nb['cells'])}")
print(f"     Size: {out.stat().st_size:,} bytes")
