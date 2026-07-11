import pytest
from open_graph_core.ids import new_id


def test_prefixed_uuid7() -> None:
    value = new_id("ds")
    assert value.startswith("ds_") and value.split("_", 1)[1][14] == "7"


def test_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        new_id("user")
