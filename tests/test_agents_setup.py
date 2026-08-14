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
