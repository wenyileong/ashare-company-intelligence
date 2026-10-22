"""v2.0.5: the default user agent and the request-rate ceiling."""
import importlib

import ashare
from ashare import config
from ashare.http import RateLimitedClient


def test_default_user_agent_names_version_and_repository(monkeypatch):
    monkeypatch.delenv("ASHARE_USER_AGENT", raising=False)
    cfg = importlib.reload(config)
    try:
        assert cfg.USER_AGENT.startswith(f"AshareResearchDataCollector/{ashare.__version__} ")
        assert "github.com/wenyileong/ashare-company-intelligence" in cfg.USER_AGENT
        assert "replace-contact" not in cfg.USER_AGENT
    finally:
        importlib.reload(config)


def test_user_agent_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ASHARE_USER_AGENT", "Study/1.0 (someone@example.org)")
    cfg = importlib.reload(config)
    try:
        assert cfg.USER_AGENT == "Study/1.0 (someone@example.org)"
    finally:
        monkeypatch.delenv("ASHARE_USER_AGENT")
        importlib.reload(config)


def test_rate_cannot_exceed_the_ceiling():
    fast = RateLimitedClient("UA", 50)
    assert abs(fast.delay - 1.0 / config.MAX_REQUESTS_PER_SECOND) < 1e-9
    assert config.MAX_REQUESTS_PER_SECOND == 2.0


def test_rate_can_be_lowered_and_has_a_floor():
    assert abs(RateLimitedClient("UA", 0.5).delay - 2.0) < 1e-9
    assert abs(RateLimitedClient("UA", 1).delay - 1.0) < 1e-9
    assert abs(RateLimitedClient("UA", 0).delay - 10.0) < 1e-9
