"""Tests for entities/organization/special_org.py."""

from stochastic_warfare.entities.organization.special_org import (
    OrgType,
    SpecialOrgManager,
    SpecialOrgTraits,
)


class TestOrgType:
    def test_values(self) -> None:
        assert OrgType.CONVENTIONAL == 0
        assert OrgType.COALITION == 3

    def test_count(self) -> None:
        assert len(OrgType) == 4


class TestSpecialOrgTraits:
    def test_creation(self) -> None:
        t = SpecialOrgTraits(
            org_type=int(OrgType.SOF),
            independent_ops=True,
            network_structure=False,
            interoperability=0.8,
            c2_flexibility=0.9,
        )
        assert t.org_type == int(OrgType.SOF)
        assert t.independent_ops is True

    def test_defaults(self) -> None:
        t = SpecialOrgTraits(org_type=int(OrgType.CONVENTIONAL))
        assert t.independent_ops is False
        assert t.interoperability == 1.0


class TestSpecialOrgManager:
    def test_designate_and_get(self) -> None:
        mgr = SpecialOrgManager()
        traits = SpecialOrgTraits(
            org_type=int(OrgType.SOF),
            independent_ops=True,
            c2_flexibility=0.95,
        )
        mgr.designate_special("sf-team-1", traits)
        result = mgr.get_traits("sf-team-1")
        assert result is not None
        assert result.org_type == int(OrgType.SOF)
        assert result.independent_ops is True

    def test_get_none_for_conventional(self) -> None:
        mgr = SpecialOrgManager()
        assert mgr.get_traits("regular-unit") is None

    def test_remove(self) -> None:
        mgr = SpecialOrgManager()
        traits = SpecialOrgTraits(org_type=int(OrgType.IRREGULAR))
        mgr.designate_special("u1", traits)
        mgr.remove("u1")
        assert mgr.get_traits("u1") is None

    def test_remove_nonexistent_no_error(self) -> None:
        mgr = SpecialOrgManager()
        mgr.remove("nonexistent")

    def test_roundtrip(self) -> None:
        mgr = SpecialOrgManager()
        mgr.designate_special("sf-1", SpecialOrgTraits(
            org_type=int(OrgType.SOF), independent_ops=True,
        ))
        mgr.designate_special("irr-1", SpecialOrgTraits(
            org_type=int(OrgType.IRREGULAR), network_structure=True,
        ))
        state = mgr.get_state()

        restored = SpecialOrgManager()
        restored.set_state(state)

        t1 = restored.get_traits("sf-1")
        assert t1 is not None
        assert t1.independent_ops is True
        t2 = restored.get_traits("irr-1")
        assert t2 is not None
        assert t2.network_structure is True
