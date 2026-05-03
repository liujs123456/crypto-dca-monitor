"""Property-based tests for lib/ladder.py using Hypothesis.

These complement the example-based tests in test_ladder.py — they assert
*invariants* that should hold for ANY valid (price, ref, armed) input,
fuzzing thousands of combinations to surface edge cases (off-by-one
re-arm, tier ordering violations, decide_notification side-effect leaks)
that hand-written examples miss.

If a property fails, hypothesis prints the minimal counterexample, e.g.:

    Falsifying example: test_lower_tier_implies_higher_tier_disarmed(
        ref=10000.0, prices=[9001.0, 8001.0]
    )

— far more useful than a generic assertion failure.

Tests are wrapped in unittest.TestCase classes so they run under
`python -m unittest discover` alongside the existing test_ladder.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lib import ladder

# Realistic BTC ref-price range — keeps hypothesis from generating
# pathological floats (NaN, inf, sub-cent values that round to 0).
ref_price = st.floats(min_value=1_000.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)
spot_price = st.floats(min_value=0.01, max_value=2_000_000.0, allow_nan=False, allow_infinity=False)
states = st.sampled_from(["GREEN", "WATCH", "T1", "T2", "T3", "T4"])
TIER_NAMES = [name for name, _, _ in ladder.TIER_CONFIG]


def _armed_strategy() -> st.SearchStrategy[dict[str, bool]]:
    return st.fixed_dictionaries({name: st.booleans() for name in TIER_NAMES})


class TestTierPricesProperties(unittest.TestCase):
    """Invariants of ladder.tier_prices()."""

    @given(ref=ref_price)
    def test_strictly_descend(self, ref: float) -> None:
        """T1 > T2 > T3 > T4 always.

        Otherwise a price could be classified into a more-severe tier
        without crossing the less-severe ones — financially incoherent.
        """
        p = ladder.tier_prices(ref)
        self.assertGreater(p["WATCH"], p["T1"])
        self.assertGreater(p["T1"], p["T2"])
        self.assertGreater(p["T2"], p["T3"])
        self.assertGreater(p["T3"], p["T4"])

    @given(ref=ref_price)
    def test_below_reference(self, ref: float) -> None:
        """All tier prices are below the reference (they're dip thresholds)."""
        p = ladder.tier_prices(ref)
        for tier in ("WATCH", "T1", "T2", "T3", "T4"):
            self.assertLess(p[tier], ref)

    @given(ref=ref_price, multiplier=st.floats(min_value=1.001, max_value=100.0, allow_nan=False))
    def test_scale_linearly(self, ref: float, multiplier: float) -> None:
        """Doubling the ref doubles every tier price (within rounding)."""
        p1 = ladder.tier_prices(ref)
        p2 = ladder.tier_prices(ref * multiplier)
        for tier in ("WATCH", "T1", "T2", "T3", "T4"):
            ratio = p2[tier] / p1[tier]
            # tier_prices rounds to 2 decimals; 1% slack handles the rounding error
            self.assertLess(abs(ratio - multiplier) / multiplier, 0.01)


class TestClassifyStateProperties(unittest.TestCase):
    @given(price=spot_price, ref=ref_price)
    def test_total(self, price: float, ref: float) -> None:
        """classify_state returns one of the known states for any valid input."""
        self.assertIn(
            ladder.classify_state(price, ref),
            {"GREEN", "WATCH", "T1", "T2", "T3", "T4"},
        )

    @given(price=spot_price, ref=ref_price)
    def test_idempotent(self, price: float, ref: float) -> None:
        """Same inputs always produce the same state — no hidden state."""
        self.assertEqual(
            ladder.classify_state(price, ref),
            ladder.classify_state(price, ref),
        )

    @given(ref=ref_price, drop_pct=st.floats(min_value=0.0, max_value=0.6))
    def test_monotone_in_price(self, ref: float, drop_pct: float) -> None:
        """A lower price never produces a less-severe state."""
        rank = {"GREEN": 0, "WATCH": 1, "T1": 2, "T2": 3, "T3": 4, "T4": 5}
        higher_price = ref * (1 - drop_pct)
        lower_price = higher_price * 0.99
        s_high = ladder.classify_state(higher_price, ref)
        s_low = ladder.classify_state(lower_price, ref)
        self.assertGreaterEqual(rank[s_low], rank[s_high])


class TestUpdateArmedProperties(unittest.TestCase):
    @given(armed=_armed_strategy(), price=spot_price, ref=ref_price)
    def test_never_disarms(
        self, armed: dict[str, bool], price: float, ref: float
    ) -> None:
        """update_armed only RE-arms; it never disarms an armed tier.

        Disarming is exclusively the job of decide_notification on a real fire.
        """
        new = ladder.update_armed(armed, price, ref)
        for name in TIER_NAMES:
            if armed[name]:
                self.assertTrue(new[name], f"{name} was armed but became disarmed")

    @given(armed=_armed_strategy(), ref=ref_price)
    def test_below_threshold_keeps_disarmed(
        self, armed: dict[str, bool], ref: float
    ) -> None:
        """A disarmed tier stays disarmed if price < tier_price * (1 + REARM_BUFFER)."""
        prices = ladder.tier_prices(ref)
        min_rearm = min(prices[n] * (1 + ladder.REARM_BUFFER) for n in TIER_NAMES)
        price = min_rearm * 0.99
        assume(price > 0)
        new = ladder.update_armed(armed, price, ref)
        for name in TIER_NAMES:
            self.assertEqual(new[name], armed[name])

    @given(armed=_armed_strategy(), ref=ref_price)
    def test_above_all_thresholds_arms_everything(
        self, armed: dict[str, bool], ref: float
    ) -> None:
        """Price well above ref → every disarmed tier re-arms."""
        new = ladder.update_armed(armed, ref * 10, ref)
        for name in TIER_NAMES:
            self.assertTrue(new[name])


class TestDecideNotificationProperties(unittest.TestCase):
    @given(state=states, prev_state=states, armed=_armed_strategy())
    def test_never_fires_disarmed_tier(
        self, state: str, prev_state: str, armed: dict[str, bool]
    ) -> None:
        """decide_notification never returns a tier name whose armed flag is False."""
        kind, _ = ladder.decide_notification(state, prev_state, armed)
        if kind in TIER_NAMES:
            self.assertTrue(armed[kind], f"fired {kind} but it was disarmed")

    @given(state=states, prev_state=states, armed=_armed_strategy())
    def test_only_disarms_what_it_fires(
        self, state: str, prev_state: str, armed: dict[str, bool]
    ) -> None:
        """Only the *fired* tier flips True->False; other tiers untouched."""
        kind, new_armed = ladder.decide_notification(state, prev_state, armed)
        for name in TIER_NAMES:
            if name == kind:
                self.assertFalse(new_armed[name])
            else:
                self.assertEqual(new_armed[name], armed[name])

    @given(state=states, prev_state=states, armed=_armed_strategy())
    def test_known_kinds(
        self, state: str, prev_state: str, armed: dict[str, bool]
    ) -> None:
        """The notify_kind is None or a known notification key."""
        kind, _ = ladder.decide_notification(state, prev_state, armed)
        self.assertIn(kind, {None, "WATCH", "T1", "T2", "T3", "T4", "RECOVERED"})

    @given(state=states, armed=_armed_strategy())
    def test_no_change_when_state_same(
        self, state: str, armed: dict[str, bool]
    ) -> None:
        """If state == prev_state, no notification fires and armed is unchanged."""
        kind, new_armed = ladder.decide_notification(state, state, armed)
        self.assertIsNone(kind)
        self.assertEqual(new_armed, armed)


class TestSimulatedWalkProperties(unittest.TestCase):
    @settings(max_examples=200)
    @given(prices=st.lists(spot_price, min_size=1, max_size=50), ref=ref_price)
    def test_armed_dict_stays_well_formed(
        self, prices: list[float], ref: float
    ) -> None:
        """Walk a sequence of prices through the full state-machine loop;
        the armed dict's invariants hold at every step."""
        armed = ladder.default_armed()
        prev_state = "GREEN"

        for p in prices:
            armed = ladder.update_armed(armed, p, ref)
            state = ladder.classify_state(p, ref)
            _, armed = ladder.decide_notification(state, prev_state, armed)
            prev_state = state

            self.assertEqual(set(armed.keys()), set(TIER_NAMES))
            for name in TIER_NAMES:
                self.assertIn(armed[name], (True, False))


if __name__ == "__main__":
    unittest.main()
