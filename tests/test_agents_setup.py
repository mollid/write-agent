from novel.agents.character import CharacterAgent
from novel.agents.outliner import OutlinerAgent
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.models import Character, Concept, World
from novel.providers import FakeProvider, ModelConfig


def _prov():
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=30000, audience="adult")
    world = World(setting="city of bells")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    return FakeProvider(responses={
        "strategist": concept, "worldbuilder": world,
        "character": chars, "outliner": __import__("novel.models", fromlist=["Outline"]).Outline(),
    }, tag_key="agent"), concept, world, chars


def test_strategist(tmp_path):
    p, _concept, _world, _chars = _prov()
    out = StrategistAgent(p, ModelConfig("zhipu", "x")).run("a thief steals time")
    assert out.genre == "fantasy"


def test_worldbuilder(tmp_path):
    p, concept, _world, _chars = _prov()
    out = WorldbuilderAgent(p, ModelConfig("anthropic", "claude")).run(concept)
    assert out.setting == "city of bells"


def test_character(tmp_path):
    p, concept, world, _chars = _prov()
    out = CharacterAgent(p, ModelConfig("anthropic", "claude")).run((concept, world))
    assert out[0].id == "c1"


def test_outliner(tmp_path):
    p, concept, world, chars = _prov()
    out = OutlinerAgent(p, ModelConfig("anthropic", "claude")).run((concept, world, chars))
    assert out is not None


def test_strategist_build_messages_uses_v2_prompt():
    p, *_ = _prov()
    agent = StrategistAgent(p, ModelConfig("zhipu", "x"))
    msgs = agent.build_messages("a thief steals time")
    assert "senior development executive" in msgs[0]["content"]
    assert msgs[0]["content"].rstrip().endswith("No preamble, no markdown fences.")
    assert "<premise>" in msgs[1]["content"]
    assert "a thief steals time" in msgs[1]["content"]
    assert msgs[1]["content"].rstrip().endswith("</premise>")


def test_worldbuilder_build_messages_uses_v2_prompt():
    p, concept, _world, _chars = _prov()
    agent = WorldbuilderAgent(p, ModelConfig("anthropic", "claude"))
    msgs = agent.build_messages(concept)
    assert "worldbuilding architect" in msgs[0]["content"]
    assert "Output ONLY the JSON object." in msgs[0]["content"]
    assert "<concept>" in msgs[1]["content"]
    assert concept.model_dump_json() in msgs[1]["content"]
    assert msgs[1]["content"].rstrip().endswith("</concept>")


def test_character_build_messages_uses_v2_prompt():
    p, concept, world, _chars = _prov()
    agent = CharacterAgent(p, ModelConfig("anthropic", "claude"))
    msgs = agent.build_messages((concept, world))
    assert "casting director" in msgs[0]["content"]
    assert '"id"' in msgs[0]["content"]
    assert "<concept>" in msgs[1]["content"]
    assert "<world>" in msgs[1]["content"]
    assert concept.model_dump_json() in msgs[1]["content"]
    assert world.model_dump_json() in msgs[1]["content"]


def test_outliner_build_messages_uses_v2_prompt():
    p, concept, world, chars = _prov()
    agent = OutlinerAgent(p, ModelConfig("anthropic", "claude"))
    msgs = agent.build_messages((concept, world, chars))
    system, user = msgs[0]["content"], msgs[1]["content"]
    # v2 identity + schema + critical rules present verbatim
    assert "story architect" in system
    assert '"arc_name"' in system
    assert '"foreshadow_ledger"' in system
    assert "ID discipline" in system
    assert system.rstrip().endswith("Return ONLY the JSON object.")
    # roster_block injected into both system and user
    roster_line = "- c1 (Ara): protagonist"
    assert roster_line in system
    assert roster_line in user
    # user carries concept/world XML blocks
    assert "<concept>" in user and "</concept>" in user
    assert "<world>" in user and "</world>" in user
    assert concept.model_dump_json() in user
    assert world.model_dump_json() in user
    assert user.rstrip().endswith("</characters>")
