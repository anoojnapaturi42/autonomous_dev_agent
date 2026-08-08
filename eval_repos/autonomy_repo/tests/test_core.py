from app_pkg import answer


def test_answer() -> None:
    assert answer() == 42
