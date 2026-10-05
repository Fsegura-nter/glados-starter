import pathlib, pytest

@pytest.fixture
def raiz():
    return pathlib.Path(__file__).resolve().parent.parent
