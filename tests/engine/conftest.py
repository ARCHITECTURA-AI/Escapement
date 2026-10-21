import pytest
from escapement_engine.core import CompiledRoom, Episode
from escapement_engine.generation import build_practice, practice_manifest


@pytest.fixture(scope="session")
def practice():
    return practice_manifest()


@pytest.fixture(scope="session")
def practice_room(practice):
    return CompiledRoom(practice)


@pytest.fixture(scope="session")
def practice_solution():
    return build_practice().solution


@pytest.fixture
def ep(practice_room):
    return Episode.start(practice_room, "test-run")


def act(tool, **arguments):
    return {"tool": tool, "arguments": arguments}
