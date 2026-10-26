"""Unit tests for the pure mapping logic in agent_advisor.

The agent run itself is an external OpenAI call and is not unit-tested here;
these cover the deterministic post-processing (filtering + R:R maths).
"""

from api.services.agent_advisor import AgentRecommendation, _to_recommendation


def _rec(**overrides) -> AgentRecommendation:
    base = dict(
        direction="LONG",
        confidence_score=75,
        entry_price=100.0,
        stop_price=90.0,
        target_price=130.0,
        timeframe="4h",
        thesis="t",
        reasoning="r",
        invalidation="i",
    )
    base.update(overrides)
    return AgentRecommendation(**base)


def test_maps_valid_long_setup_with_risk_reward():
    out = _to_recommendation("BTC-EUR", _rec())
    assert out is not None
    assert out["symbol"] == "BTC-EUR"
    assert out["direction"] == "LONG"
    # risk = |100-90| = 10, reward = |130-100| = 30 → 3.0
    assert out["risk_reward"] == 3.0
    assert "generated_at" in out


def test_none_direction_is_skipped():
    assert _to_recommendation("BTC-EUR", _rec(direction=None, confidence_score=0)) is None


def test_low_confidence_is_skipped():
    assert _to_recommendation("BTC-EUR", _rec(confidence_score=49)) is None


def test_confidence_boundary_is_kept():
    assert _to_recommendation("BTC-EUR", _rec(confidence_score=50)) is not None


def test_zero_risk_yields_zero_rr_not_crash():
    out = _to_recommendation("BTC-EUR", _rec(entry_price=100.0, stop_price=100.0))
    assert out is not None
    assert out["risk_reward"] == 0
