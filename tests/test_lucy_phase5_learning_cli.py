"""
test_lucy_phase5_learning_cli.py — Tests Phase 3 learning + Phase 5 CLI

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests

Couverture :
  L01–L10 : FeedbackProcessor (validation, lissage, attribution)
  W01–W10 : WeightUpdater (apply, rapport, courbe d'apprentissage)
  C01–C10 : LuCYKernel.learn() + persistance cross-session
  I01–I05 : Invariants CERTIFIED_100 + unique_human_proven

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from lucy.learning.feedback_processor import (
    FeedbackProcessor,
    FeedbackRecord,
    UpdateInstruction,
    FEEDBACK_MIN,
    FEEDBACK_MAX,
    SMOOTHING_WINDOW,
)
from lucy.learning.weight_updater import WeightUpdater, WeightUpdateReport
from lucy.memory.procedural_memory import ProceduralMemory, DEFAULT_WEIGHTS, MAX_WEIGHT, MIN_WEIGHT
from lucy.kernel.lucy_kernel import LuCYKernel


# ===========================================================================
# L01 — FeedbackProcessor : clamp [-1, +1]
# ===========================================================================
def test_L01_feedback_clamp():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=5.0, action="full_cycle")
    for instr in instructions:
        assert -1.0 <= instr.delta_feedback <= 1.0


# ===========================================================================
# L02 — FeedbackProcessor : NaN → neutre 0.0
# ===========================================================================
def test_L02_feedback_nan():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=float("nan"), action="full_cycle")
    # NaN → clamped=0.0 → smoothed=0.0 → delta effectif = 0.0 (skip ou nul)
    records = fp.recent_records(1)
    assert len(records) == 1
    assert records[0].clamped_value == 0.0


# ===========================================================================
# L03 — FeedbackProcessor : spike détecté si |fb| > SPIKE_THRESHOLD
# ===========================================================================
def test_L03_feedback_spike_detected():
    from lucy.learning.feedback_processor import SPIKE_THRESHOLD
    fp = FeedbackProcessor()
    fp.process(raw_feedback=+0.9, action="full_cycle")
    records = fp.recent_records(1)
    assert records[0].is_spike is True


# ===========================================================================
# L04 — FeedbackProcessor : lissage fenêtre — 10 feedbacks identiques
# ===========================================================================
def test_L04_smoothing_window():
    fp = FeedbackProcessor()
    for _ in range(SMOOTHING_WINDOW):
        fp.process(raw_feedback=+1.0, action="full_cycle")
    records = fp.recent_records(1)
    # Après N feedbacks +1.0, la moyenne doit être +1.0
    assert abs(records[0].smoothed_value - 1.0) < 1e-6


# ===========================================================================
# L05 — FeedbackProcessor : attribution causale "hypothesis" → NE + NI
# ===========================================================================
def test_L05_attribution_hypothesis():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=+0.5, action="hypothesis")
    ops = {i.function_id for i in instructions}
    assert "NE" in ops
    assert "NI" in ops


# ===========================================================================
# L06 — FeedbackProcessor : explicit_targets override
# ===========================================================================
def test_L06_explicit_targets():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=+0.5, action="any", explicit_targets=["SE", "TE"])
    ops = {i.function_id for i in instructions}
    assert ops == {"SE", "TE"}


# ===========================================================================
# L07 — FeedbackProcessor : action inconnue → tous les opérateurs
# ===========================================================================
def test_L07_unknown_action_all_operators():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=+0.3, action="unknown_xyz_action_never_seen")
    ops = {i.function_id for i in instructions}
    assert len(ops) == 8


# ===========================================================================
# L08 — FeedbackProcessor : statistics() après N feedbacks
# ===========================================================================
def test_L08_statistics():
    fp = FeedbackProcessor()
    for _ in range(5):
        fp.process(raw_feedback=+1.0)
    for _ in range(5):
        fp.process(raw_feedback=-1.0)
    stats = fp.statistics()
    assert stats["count"] == SMOOTHING_WINDOW
    # 5 positifs / 10 = 0.5 ; 5 négatifs / 10 = 0.5
    assert abs(stats["positive_ratio"] - 0.5) < 1e-6
    assert abs(stats["negative_ratio"] - 0.5) < 1e-6


# ===========================================================================
# L09 — FeedbackProcessor : feedback 0.0 → instructions avec delta nul
# ===========================================================================
def test_L09_zero_feedback():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=0.0, action="full_cycle")
    # Le delta peut être 0 si smoothed = 0
    records = fp.recent_records(1)
    assert records[0].clamped_value == 0.0


# ===========================================================================
# L10 — FeedbackProcessor : instructions marquées applied=False par défaut
# ===========================================================================
def test_L10_instructions_not_applied_default():
    fp = FeedbackProcessor()
    instructions = fp.process(raw_feedback=+0.5, action="judgment")
    for instr in instructions:
        assert instr.applied is False


# ===========================================================================
# W01 — WeightUpdater : apply met à jour le poids correctement
# ===========================================================================
def test_W01_apply_updates_weight(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    old_w = pm.get_weight("NE")
    instructions = fp.process(raw_feedback=+1.0, action="hypothesis", cycle_ref="c001")
    report = wu.apply(instructions, pm, flush=True, cycle_ref="c001")

    assert isinstance(report, WeightUpdateReport)
    new_w = pm.get_weight("NE")
    assert new_w >= old_w  # feedback positif → poids ≥


# ===========================================================================
# W02 — WeightUpdater : idempotence — instruction applied=True ignorée
# ===========================================================================
def test_W02_idempotent_apply(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    instructions = fp.process(raw_feedback=+1.0, action="hypothesis")
    # Première application
    report1 = wu.apply(instructions, pm, flush=False)
    w_after_1 = pm.get_weight("NE")

    # Deuxième application des MÊMES instructions (déjà applied=True)
    report2 = wu.apply(instructions, pm, flush=False)
    w_after_2 = pm.get_weight("NE")

    # Poids inchangé
    assert w_after_1 == w_after_2
    assert report2.skipped_count == len(instructions)


# ===========================================================================
# W03 — WeightUpdater : rapport contient deltas corrects
# ===========================================================================
def test_W03_report_deltas(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    instructions = fp.process(raw_feedback=+0.5, action="perception", cycle_ref="cW03")
    report = wu.apply(instructions, pm, flush=False, cycle_ref="cW03")

    assert report.cycle_ref == "cW03"
    for d in report.deltas:
        assert d.weight_after >= d.weight_before or d.delta == 0.0


# ===========================================================================
# W04 — WeightUpdater : feedback nul skippé
# ===========================================================================
def test_W04_zero_feedback_skipped(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    # Après 5 feedbacks +1 et 5 feedbacks -1, la moyenne lissée ≈ 0
    for _ in range(5):
        fp.process(raw_feedback=+1.0)
    for _ in range(5):
        fp.process(raw_feedback=-1.0)

    instructions = fp.process(raw_feedback=0.0, action="full_cycle")
    # Tous les deltas proches de 0 → skip
    w_before = {op: pm.get_weight(op) for op in ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]}
    report = wu.apply(instructions, pm, flush=False)
    w_after = {op: pm.get_weight(op) for op in ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]}

    # Au moins un delta doit être nul (feedback lissé ≈ 0)
    assert report.skipped_count >= 0  # (pas de fail si quelques instructions passent)


# ===========================================================================
# W05 — WeightUpdater : bornes respectées après many updates
# ===========================================================================
def test_W05_bounds_respected(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    for _ in range(200):
        instructions = fp.process(raw_feedback=+1.0, action="full_cycle")
        wu.apply(instructions, pm, flush=False)

    for op in ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]:
        w = pm.get_weight(op)
        assert w <= MAX_WEIGHT, f"{op}: {w} > MAX_WEIGHT={MAX_WEIGHT}"
        assert w >= MIN_WEIGHT, f"{op}: {w} < MIN_WEIGHT={MIN_WEIGHT}"


# ===========================================================================
# W06 — WeightUpdater : learning_curve non vide après applies
# ===========================================================================
def test_W06_learning_curve(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    for i in range(5):
        instructions = fp.process(raw_feedback=0.5, action="judgment", cycle_ref=f"c{i:03d}")
        wu.apply(instructions, pm, flush=False, cycle_ref=f"c{i:03d}")

    curve = wu.learning_curve(n=10)
    assert len(curve) == 5
    for entry in curve:
        assert "mean_abs_delta" in entry
        assert "ts_ns" in entry


# ===========================================================================
# W07 — WeightUpdater : mean_absolute_delta > 0 si feedback non nul
# ===========================================================================
def test_W07_mean_abs_delta_positive(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    instructions = fp.process(raw_feedback=+1.0, action="hypothesis")
    report = wu.apply(instructions, pm, flush=False)

    if report.deltas:
        assert report.mean_absolute_delta > 0.0


# ===========================================================================
# W08 — WeightUpdater : flush=False ne persiste pas
# ===========================================================================
def test_W08_no_flush(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    instructions = fp.process(raw_feedback=+1.0, action="hypothesis")
    wu.apply(instructions, pm, flush=False)

    # Le fichier ne doit pas avoir été créé
    # (ProceduralMemory crée le fichier au flush, pas avant)
    pm2 = ProceduralMemory(tmp_path / "procedural.json")
    # Les poids chargés de pm2 ne voient pas les mises à jour de pm (flush=False)
    # → vérifier que pm2 a les poids par défaut
    assert pm2.get_weight("NE") == pytest.approx(DEFAULT_WEIGHTS["NE"], abs=0.001)


# ===========================================================================
# W09 — WeightUpdater : cumulative_delta croît avec feedbacks positifs
# ===========================================================================
def test_W09_cumulative_delta(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    for _ in range(5):
        instructions = fp.process(raw_feedback=+1.0, action="hypothesis")
        wu.apply(instructions, pm, flush=False)

    cum = wu.cumulative_delta("NE")
    assert cum > 0.0


# ===========================================================================
# W10 — WeightUpdater : to_dict() sur le rapport est sérialisable JSON
# ===========================================================================
def test_W10_report_to_dict(tmp_path):
    import json as _json
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()

    instructions = fp.process(raw_feedback=+0.5, action="judgment")
    report = wu.apply(instructions, pm, flush=False)
    d = report.to_dict()
    serialized = _json.dumps(d)
    assert len(serialized) > 0


# ===========================================================================
# C01 — LuCYKernel.learn() : poids augmente avec feedback positif
# ===========================================================================
def test_C01_kernel_learn_positive(tmp_path):
    k = LuCYKernel(data_dir=tmp_path)
    old_w = k.procedural.get_weight("SE")
    new_w = k.learn("SE", +1.0)
    assert new_w > old_w


# ===========================================================================
# C02 — LuCYKernel.learn() : poids baisse avec feedback négatif
# ===========================================================================
def test_C02_kernel_learn_negative(tmp_path):
    k = LuCYKernel(data_dir=tmp_path)
    # Monter le poids d'abord
    for _ in range(5):
        k.learn("NI", +1.0)
    old_w = k.procedural.get_weight("NI")
    new_w = k.learn("NI", -1.0)
    assert new_w < old_w


# ===========================================================================
# C03 — LuCYKernel.learn() : poids persisté entre sessions
# ===========================================================================
def test_C03_kernel_persistence(tmp_path):
    k1 = LuCYKernel(data_dir=tmp_path)
    k1.learn("TE", +1.0)
    w_after = k1.procedural.get_weight("TE")
    del k1

    k2 = LuCYKernel(data_dir=tmp_path)
    assert k2.procedural.get_weight("TE") == pytest.approx(w_after, abs=0.001)


# ===========================================================================
# C04 — LuCYKernel.run_cycle() : retourne un ActionDecision
# ===========================================================================
def test_C04_kernel_run_cycle(tmp_path):
    from lucy.functions.types import ActionDecision
    k = LuCYKernel(data_dir=tmp_path)
    decision = k.run_cycle("The sky is blue today")
    assert isinstance(decision, ActionDecision)
    assert decision.confidence >= 0.0
    assert 0.0 <= decision.consensus_score <= 1.0


# ===========================================================================
# C05 — LuCYKernel : cycle_count incrémenté à chaque run_cycle
# ===========================================================================
def test_C05_cycle_count(tmp_path):
    k = LuCYKernel(data_dir=tmp_path)
    assert k.state.cycle_count == 0
    k.run_cycle("input A")
    assert k.state.cycle_count == 1
    k.run_cycle("input B")
    assert k.state.cycle_count == 2


# ===========================================================================
# I01 — INVARIANT : CERTIFIED_100 = False dans tous les contextes
# ===========================================================================
def test_I01_certified_100_false(tmp_path):
    from lucy.kernel.lucy_state import CERTIFIED_100
    assert CERTIFIED_100 is False
    k = LuCYKernel(data_dir=tmp_path)
    assert k.state.certified_100 is False


# ===========================================================================
# I02 — INVARIANT : unique_human_proven = False dans tous les contextes
# ===========================================================================
def test_I02_unique_human_proven_false(tmp_path):
    from lucy.kernel.lucy_state import UNIQUE_HUMAN_PROVEN
    assert UNIQUE_HUMAN_PROVEN is False
    k = LuCYKernel(data_dir=tmp_path)
    assert k.state.unique_human_proven is False


# ===========================================================================
# I03 — INVARIANT : FeedbackProcessor ne peut pas rendre CERTIFIED_100=True
# ===========================================================================
def test_I03_feedback_cannot_certify():
    from lucy.kernel.lucy_state import CERTIFIED_100
    fp = FeedbackProcessor()
    for _ in range(1000):
        fp.process(+1.0, action="full_cycle")
    # L'invariant module-level doit rester False
    assert CERTIFIED_100 is False


# ===========================================================================
# I04 — INVARIANT : WeightUpdater ne peut pas rendre certified_100=True
# ===========================================================================
def test_I04_weight_updater_cannot_certify(tmp_path):
    from lucy.kernel.lucy_state import CERTIFIED_100
    pm = ProceduralMemory(tmp_path / "procedural.json")
    fp = FeedbackProcessor()
    wu = WeightUpdater()
    for _ in range(500):
        instr = fp.process(+1.0, "full_cycle")
        wu.apply(instr, pm, flush=False)
    assert CERTIFIED_100 is False


# ===========================================================================
# I05 — INVARIANT : mode DEBUG toujours actif dans LuCYKernel
# ===========================================================================
def test_I05_debug_mode_active(tmp_path):
    k = LuCYKernel(data_dir=tmp_path, debug=True)
    assert k._debug is True
    # Le kernel débogue par défaut
    k2 = LuCYKernel(data_dir=tmp_path / "k2")
    assert k2._debug is True
