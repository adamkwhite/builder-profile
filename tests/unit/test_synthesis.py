from builder_profile.models import BehavioralSignals
from builder_profile.synthesis import _build_factual_cards


def _prompt_card(avg_words):
    sig = BehavioralSignals(avg_prompt_words=avg_words)
    cards = [c for c in _build_factual_cards(sig) if c.signal == "avg_prompt_words"]
    assert len(cards) == 1
    return cards[0]


class TestProductivityCard:
    def _timing_card(self, peak):
        sig = BehavioralSignals(peak_hour=peak)
        cards = [c for c in _build_factual_cards(sig) if c.signal == "peak_hour"]
        assert len(cards) == 1
        return cards[0]

    def test_evening_peak_labelled_night_owl(self):
        assert self._timing_card(21).title == "Night owl"

    def test_overnight_peak_labelled_night_owl(self):
        assert self._timing_card(2).title == "Night owl"

    def test_daytime_peak_not_night_owl(self):
        assert self._timing_card(14).title == "Peak: 14:00"


class TestPromptLengthCard:
    def test_terse_average_is_not_thorough(self):
        # 9 words is a dispatch, not thorough context (regression).
        card = _prompt_card(8.8)
        assert card.title == "Straight to the point"
        assert "thorough" not in card.body.lower()
        assert "say a lot with a little" in card.body

    def test_moderate_average_is_clear_and_direct(self):
        card = _prompt_card(18.0)
        assert card.title == "Clear and direct"
        assert "thorough" not in card.body.lower()

    def test_long_average_is_detailed(self):
        card = _prompt_card(30.0)
        assert card.title == "Detailed director"
        assert "thorough context" in card.body
