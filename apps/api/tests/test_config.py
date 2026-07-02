from __future__ import annotations

from sanad_api.core.config import Settings


def test_dev_mode_allows_egress() -> None:
    s = Settings(mode="dev")
    assert s.egress_allowed


def test_sovereign_mode_blocks_egress_and_external_judges() -> None:
    # prime directive 1: sovereignty is a build mode
    s = Settings(mode="sovereign", allow_external_judges=True)
    assert not s.egress_allowed
    assert s.allow_external_judges is False  # forced off outside dev


def test_edge_mode_blocks_external_judges() -> None:
    s = Settings(mode="edge", allow_external_judges=True)
    assert s.allow_external_judges is False
