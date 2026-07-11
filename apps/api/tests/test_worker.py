from app.worker import ping


def test_ping() -> None:
    assert ping.run() == "pong"
