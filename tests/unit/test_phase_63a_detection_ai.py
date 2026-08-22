"""Phase 63a: Detection → AI Assessment — FOW sensor/signature wiring tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from stochastic_warfare.simulation.battle import _get_unit_signature
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.core.types import Position, Domain


def _make_unit(uid="u1", side="blue", pos=None, unit_type="m1_abrams"):
    u = Unit(
        entity_id=uid,
        position=pos or Position(100.0, 200.0, 0.0),
        name=uid,
        unit_type=unit_type,
        side=side,
        domain=Domain.GROUND,
        status=UnitStatus.ACTIVE,
    )
    return u


class TestGetUnitSignature:
    """Test the _get_unit_signature helper."""

    def test_returns_profile_when_available(self):
        sig_loader = MagicMock()
        sig_loader.get_profile.return_value = {"visual": 10.0}
        ctx = SimpleNamespace(sig_loader=sig_loader)
        unit = _make_unit()
        result = _get_unit_signature(ctx, unit)
        assert result == {"visual": 10.0}
        sig_loader.get_profile.assert_called_once_with("m1_abrams")

    def test_returns_none_when_no_sig_loader(self):
        ctx = SimpleNamespace()
        unit = _make_unit()
        assert _get_unit_signature(ctx, unit) is None

    def test_returns_none_when_sig_loader_is_none(self):
        ctx = SimpleNamespace(sig_loader=None)
        unit = _make_unit()
        assert _get_unit_signature(ctx, unit) is None

    def test_returns_none_on_key_error(self):
        sig_loader = MagicMock()
        sig_loader.get_profile.side_effect = KeyError("unknown")
        ctx = SimpleNamespace(sig_loader=sig_loader)
        unit = _make_unit()
        assert _get_unit_signature(ctx, unit) is None

    def test_returns_none_on_attribute_error(self):
        sig_loader = MagicMock()
        sig_loader.get_profile.side_effect = AttributeError
        ctx = SimpleNamespace(sig_loader=sig_loader)
        unit = _make_unit()
        assert _get_unit_signature(ctx, unit) is None

    def test_missing_unit_type_returns_none_without_error(self):
        """A missing unit type has an explicit None fallback without error."""
        sig_loader = MagicMock()
        sig_loader.get_profile.return_value = None
        ctx = SimpleNamespace(sig_loader=sig_loader)
        unit = SimpleNamespace(unit_type=None)
        assert _get_unit_signature(ctx, unit) is None
        sig_loader.get_profile.assert_called_once_with(None)
