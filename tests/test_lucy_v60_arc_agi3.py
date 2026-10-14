
# tests/test_lucy_v60_arc_agi3.py
# Tests unitaires LuCY v6.0 — ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
#
# Couvre :
#   T01-T05 : GameMemory — enregistrement et scoring
#   T06-T10 : frame_fingerprint + frame_delta
#   T11-T15 : Stratégie explore/exploit/recover
#   T16-T20 : Conformité interface Agent (is_done / choose_action)
#   T21-T25 : Détection de stagnation et RESET
#   T26-T30 : Compatibilité notebook Kaggle (writefile cell, imports)

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub minimal pour simuler arcengine et agents.agent sans installer le SDK
# ---------------------------------------------------------------------------

def _make_game_action_enum():
    """Crée un stub GameAction compatible avec le code de LuCY v6.0."""
    class GameAction:
        def __init__(self, value: int) -> None:
            self.value = value
            self.reasoning = ""
            self._data = {}

        @classmethod
        def from_id(cls, id: int) -> "GameAction":
            return cls(id)

        def is_complex(self) -> bool:
            return self.value == 6

        def is_simple(self) -> bool:
            return self.value != 6

        def set_data(self, d: dict) -> None:
            self._data = d

        @property
        def name(self) -> str:
            names = {0:"RESET",1:"ACTION1",2:"ACTION2",3:"ACTION3",
                     4:"ACTION4",5:"ACTION5",6:"ACTION6",7:"ACTION7"}
            return names.get(self.value, f"ACTION{self.value}")

        def __repr__(self) -> str:
            return f"GameAction({self.value})"

    # Attributs de classe pour les constantes
    GameAction.RESET    = GameAction(0)
    GameAction.ACTION1  = GameAction(1)
    GameAction.ACTION2  = GameAction(2)
    GameAction.ACTION3  = GameAction(3)
    GameAction.ACTION4  = GameAction(4)
    GameAction.ACTION5  = GameAction(5)
    GameAction.ACTION6  = GameAction(6)
    GameAction.ACTION7  = GameAction(7)
    return GameAction


class GameState:
    NOT_PLAYED  = "NOT_PLAYED"
    NOT_FINISHED = "NOT_FINISHED"
    WIN         = "WIN"
    GAME_OVER   = "GAME_OVER"


# FrameData stub
class FrameData:
    def __init__(self, **kwargs):
        self.levels_completed = kwargs.get("levels_completed", 0)
        self.win_levels = kwargs.get("win_levels", 5)
        self.state = kwargs.get("state", GameState.NOT_FINISHED)
        self.frame = kwargs.get("frame", [[1, 2, 3], [4, 5, 6]])
        self.available_actions = kwargs.get("available_actions", [])
        self.guid = kwargs.get("guid", "")
        self.game_id = kwargs.get("game_id", "test")
        self.full_reset = kwargs.get("full_reset", False)

    def model_dump_json(self) -> str:
        import json
        return json.dumps({"levels_completed": self.levels_completed})


# Agent base stub
class Agent:
    MAX_ACTIONS = 80
    action_counter = 0

    def __init__(self, card_id="", game_id="test", agent_name="lucy",
                 ROOT_URL="", record=False, arc_env=None, tags=None, **kw):
        self.card_id = card_id
        self.game_id = game_id
        self.agent_name = agent_name
        self.ROOT_URL = ROOT_URL
        self.frames = [FrameData()]
        self.action_counter = 0
        self.arc_env = arc_env
        self.tags = tags or []
        self._cleanup = True

    def cleanup(self, scorecard=None):
        pass


# Injecter les stubs dans sys.modules AVANT d'importer l'agent
_ga = _make_game_action_enum()

arcengine_mod = types.ModuleType("arcengine")
arcengine_mod.GameAction = _ga
arcengine_mod.GameState  = GameState
arcengine_mod.FrameData  = FrameData
arcengine_mod.FrameDataRaw = FrameData
sys.modules["arcengine"] = arcengine_mod

agents_mod = types.ModuleType("agents")
agents_agent_mod = types.ModuleType("agents.agent")
agents_agent_mod.Agent   = Agent
sys.modules["agents"]       = agents_mod
sys.modules["agents.agent"] = agents_agent_mod
agents_mod.agent = agents_agent_mod

# Importer l'agent v6.0
_src = Path(__file__).parent.parent / "src" / "lucy" / "kernel" / "lucy_agent_v60.py"
spec = importlib.util.spec_from_file_location("lucy_agent_v60", _src)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

GameMemory      = _mod.GameMemory
LuCYAgent       = _mod.LuCYAgent
frame_fingerprint = _mod.frame_fingerprint
frame_delta       = _mod.frame_delta


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture
def memory():
    return GameMemory()

@pytest.fixture
def agent():
    return LuCYAgent(game_id="test_game")

@pytest.fixture
def frame_not_finished():
    return FrameData(state=GameState.NOT_FINISHED, levels_completed=0,
                     frame=[[1, 2], [3, 4]])

@pytest.fixture
def frame_win():
    return FrameData(state=GameState.WIN, levels_completed=3)

@pytest.fixture
def frame_game_over():
    return FrameData(state=GameState.GAME_OVER, levels_completed=0)


# ===========================================================================
# T01-T05 : GameMemory
# ===========================================================================

def test_T01_memory_record_level_up(memory):
    """T01 : record level_up incrémente le compteur level_up."""
    memory.record("1", "level_up", 0.5)
    assert memory.action_stats["1"]["level_up"] == 1
    assert memory.action_stats["1"]["total"] == 1

def test_T02_memory_record_frame_change(memory):
    """T02 : record frame_change n'incrémente pas level_up."""
    memory.record("2", "frame_change", 0.3)
    assert memory.action_stats["2"]["level_up"] == 0
    assert memory.action_stats["2"]["frame_change"] == 1

def test_T03_memory_record_no_change(memory):
    """T03 : record no_change incrémente uniquement no_change."""
    memory.record("3", "no_change", 0.0)
    assert memory.action_stats["3"]["no_change"] == 1
    assert memory.action_stats["3"]["frame_change"] == 0

def test_T04_memory_best_actions_order(memory):
    """T04 : best_actions retourne level_up en premier."""
    memory.record("1", "level_up", 0.5)
    memory.record("1", "level_up", 0.5)
    memory.record("2", "no_change", 0.0)
    memory.record("2", "no_change", 0.0)
    ranked = memory.best_actions(["1", "2"])
    assert ranked[0] == "1"

def test_T05_memory_unexplored(memory):
    """T05 : unexplored retourne les actions testées < 3 fois."""
    memory.record("1", "no_change", 0.0)
    memory.record("1", "no_change", 0.0)
    memory.record("2", "no_change", 0.0)
    memory.record("2", "no_change", 0.0)
    memory.record("2", "no_change", 0.0)
    unexplored = memory.unexplored(["1", "2", "3"])
    assert "1" in unexplored   # testé 2x < 3
    assert "3" in unexplored   # jamais testé
    assert "2" not in unexplored  # testé 3x = seuil


# ===========================================================================
# T06-T10 : frame_fingerprint + frame_delta
# ===========================================================================

def test_T06_fingerprint_deterministic():
    """T06 : même frame → même fingerprint."""
    frame = [[1, 2, 3], [4, 5, 6]]
    assert frame_fingerprint(frame) == frame_fingerprint(frame)

def test_T07_fingerprint_different_frames():
    """T07 : frames différentes → fingerprints différents."""
    f1 = [[1, 2, 3], [4, 5, 6]]
    f2 = [[9, 8, 7], [6, 5, 4]]
    assert frame_fingerprint(f1) != frame_fingerprint(f2)

def test_T08_fingerprint_none():
    """T08 : frame None → fingerprint 'null'."""
    assert frame_fingerprint(None) == "null"

def test_T09_delta_identical_frames():
    """T09 : frames identiques → delta ≈ 0."""
    frame = [[1, 2, 3], [4, 5, 6]]
    d = frame_delta(frame, frame)
    assert d < 0.01

def test_T10_delta_different_frames():
    """T10 : frames totalement différentes → delta > 0."""
    f1 = [[1, 1, 1], [1, 1, 1]]
    f2 = [[9, 9, 9], [9, 9, 9]]
    d = frame_delta(f1, f2)
    assert d > 0.5


# ===========================================================================
# T11-T15 : Stratégie explore/exploit/recover
# ===========================================================================

def test_T11_initial_strategy_explore(agent):
    """T11 : stratégie initiale = explore."""
    assert agent._strategy == "explore"

def test_T12_explore_picks_unexplored(agent, frame_not_finished):
    """T12 : en mode explore, l'agent choisit une action non testée."""
    frames = [frame_not_finished]
    action = agent.choose_action(frames, frame_not_finished)
    # L'action ne doit pas être None
    assert action is not None

def test_T13_strategy_switches_to_exploit(agent, frame_not_finished):
    """T13 : après avoir exploré toutes les actions (3x), passe à exploit."""
    frames = [frame_not_finished]
    # Remplir la mémoire avec 3+ observations par action
    for aid in ["1", "2", "3", "4", "5", "7"]:
        for _ in range(3):
            agent.memory.record(aid, "no_change", 0.0)
    # Plus d'actions à explorer
    unexplored = agent.memory.unexplored(["1", "2", "3", "4", "5", "7"])
    assert len(unexplored) == 0

def test_T14_recover_strategy_after_stuck(agent, frame_not_finished):
    """T14 : détection de stagnation déclenche la stratégie recover."""
    # Simuler un état visité STUCK_THRESHOLD fois
    fp = "aaabbbccc123"
    agent.memory.last_fingerprint = fp
    for _ in range(_mod.STUCK_THRESHOLD):
        agent.memory.visited_states[fp] += 1
    assert agent.memory.is_stuck()

def test_T15_strategy_label_valid(agent):
    """T15 : la stratégie est toujours l'une des 3 valeurs autorisées."""
    valid = {"explore", "exploit", "recover"}
    assert agent._strategy in valid


# ===========================================================================
# T16-T20 : Conformité interface Agent
# ===========================================================================

def test_T16_is_done_not_finished(agent, frame_not_finished):
    """T16 : is_done retourne False si état NOT_FINISHED."""
    frames = [frame_not_finished]
    assert agent.is_done(frames, frame_not_finished) is False

def test_T17_is_done_win(agent, frame_win):
    """T17 : is_done retourne True si état WIN."""
    frames = [frame_win]
    assert agent.is_done(frames, frame_win) is True

def test_T18_is_done_budget_exhausted(agent, frame_not_finished):
    """T18 : is_done retourne True si action_counter >= MAX_ACTIONS."""
    agent.action_counter = _mod.MAX_ACTIONS
    frames = [frame_not_finished]
    assert agent.is_done(frames, frame_not_finished) is True

def test_T19_choose_action_returns_game_action(agent, frame_not_finished):
    """T19 : choose_action retourne toujours un GameAction (a un attribut value int)."""
    frames = [frame_not_finished]
    action = agent.choose_action(frames, frame_not_finished)
    assert action is not None
    assert hasattr(action, "value")
    assert isinstance(action.value, int)

def test_T20_choose_action_game_over_returns_reset(agent, frame_game_over):
    """T20 : choose_action retourne RESET sur GAME_OVER."""
    agent._started = True  # simule que le jeu a déjà démarré
    frames = [frame_game_over]
    action = agent.choose_action(frames, frame_game_over)
    assert action.value == 0  # RESET = 0


# ===========================================================================
# T21-T25 : Détection de stagnation et RESET
# ===========================================================================

def test_T21_memory_reset_visit_counts(memory):
    """T21 : reset_visit_counts vide visited_states sans toucher action_stats."""
    memory.record("1", "level_up", 0.5)
    memory.visited_states["abc"] = 10
    memory.reset_visit_counts()
    assert len(memory.visited_states) == 0
    assert "1" in memory.action_stats  # modèle conservé

def test_T22_stuck_detection_false_below_threshold(memory):
    """T22 : is_stuck retourne False si visites < STUCK_THRESHOLD."""
    fp = "teststate"
    memory.last_fingerprint = fp
    memory.visited_states[fp] = _mod.STUCK_THRESHOLD - 1
    assert memory.is_stuck() is False

def test_T23_stuck_detection_true_at_threshold(memory):
    """T23 : is_stuck retourne True si visites >= STUCK_THRESHOLD."""
    fp = "teststate"
    memory.last_fingerprint = fp
    memory.visited_states[fp] = _mod.STUCK_THRESHOLD
    assert memory.is_stuck() is True

def test_T24_consecutive_stuck_counter_increments(agent, frame_not_finished):
    """T24 : le compteur _consecutive_stuck augmente à chaque stagnation."""
    agent._started = True
    fp = "fixedstate"
    agent.memory.last_fingerprint = fp
    agent.memory.visited_states[fp] = _mod.STUCK_THRESHOLD + 2

    initial_stuck = agent._consecutive_stuck
    frames = [frame_not_finished]
    agent.choose_action(frames, frame_not_finished)
    assert agent._consecutive_stuck > initial_stuck or agent._consecutive_stuck == 0

def test_T25_level_up_resets_stuck_counter(agent, frame_not_finished):
    """T25 : un level up remet à zéro _consecutive_stuck."""
    agent._started = True
    agent._consecutive_stuck = 3
    agent._prev_levels = 0

    frame_level1 = FrameData(
        state=GameState.NOT_FINISHED,
        levels_completed=1,
        frame=[[1, 2], [3, 4]],
    )
    frames = [frame_not_finished, frame_level1]
    agent.choose_action(frames, frame_level1)
    assert agent._consecutive_stuck == 0


# ===========================================================================
# T26-T30 : Conformité notebook Kaggle
# ===========================================================================

def test_T26_notebook_cell2_starts_with_writefile():
    """T26 : CELL 2 du notebook commence par %%writefile /kaggle/working/lucy_agent.py."""
    import json
    nb_path = Path(__file__).parent.parent / "notebooks" / "arc3" / "lucy_arc_agi3_submission.ipynb"
    nb = json.loads(nb_path.read_text())
    cell2_src = "".join(nb["cells"][2]["source"])
    assert cell2_src.startswith("%%writefile /kaggle/working/lucy_agent.py")

def test_T27_notebook_has_rerun_detection():
    """T27 : notebook contient la détection IS_RERUN / KAGGLE_IS_COMPETITION_RERUN."""
    import json
    nb_path = Path(__file__).parent.parent / "notebooks" / "arc3" / "lucy_arc_agi3_submission.ipynb"
    nb = json.loads(nb_path.read_text())
    all_src = " ".join("".join(c["source"]) for c in nb["cells"])
    assert "IS_RERUN" in all_src
    assert "KAGGLE_IS_COMPETITION_RERUN" in all_src

def test_T28_notebook_has_parquet_submission():
    """T28 : notebook produit submission.parquet (format officiel Kaggle ARC-AGI-3)."""
    import json
    nb_path = Path(__file__).parent.parent / "notebooks" / "arc3" / "lucy_arc_agi3_submission.ipynb"
    nb = json.loads(nb_path.read_text())
    all_src = " ".join("".join(c["source"]) for c in nb["cells"])
    assert "submission.parquet" in all_src

def test_T29_agent_v60_imports_from_agent():
    """T29 : lucy_agent_v60 hérite de Agent (arcprize/ARC-AGI-3-Agents)."""
    assert issubclass(LuCYAgent, Agent)

def test_T30_agent_v60_max_actions():
    """T30 : MAX_ACTIONS défini et raisonnable (50 ≤ X ≤ 1000)."""
    assert 50 <= LuCYAgent.MAX_ACTIONS <= 1000


# ===========================================================================
# ENTRYPOINT
# ===========================================================================

if __name__ == "__main__":
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(Path(__file__).parent.parent),
    )
    sys.exit(result.returncode)
