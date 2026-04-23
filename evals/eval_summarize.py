"""
Rule-based evals for summarize.py output quality.
Uses DeepEval's BaseMetric interface for structured pass/fail reporting,
with all assertions being deterministic (no LLM judge = free to run in CI).
"""
import re
import pytest
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from newstome.summarize import Summary
from .fixtures import GOOD_SUMMARIES, BAD_SUMMARIES


# ── Metrics ───────────────────────────────────────────────────────────────────

class HeadlineWordCount(BaseMetric):
    """Headline must be 6-10 words."""
    name = "HeadlineWordCount"
    threshold = 1.0

    def measure(self, test_case: LLMTestCase) -> float:
        headline = test_case.actual_output
        count = len(headline.split())
        self.success = 6 <= count <= 10
        self.score = 1.0 if self.success else 0.0
        self.reason = f"{count} words" if not self.success else None
        return self.score

    def is_successful(self) -> bool:
        return self.success

    async def a_measure(self, test_case):
        return self.measure(test_case)


class HeadlineNoBannedPhrases(BaseMetric):
    """No filler openers or trailing punctuation."""
    name = "HeadlineNoBannedPhrases"
    threshold = 1.0
    _BANNED = re.compile(
        r"^(in a recent|breaking:|just in|wow|amazing|shocking)",
        re.IGNORECASE,
    )
    _TRAILING_PUNCT = re.compile(r"[.!?;:,]$")

    def measure(self, test_case: LLMTestCase) -> float:
        h = test_case.actual_output
        banned = bool(self._BANNED.match(h))
        punct = bool(self._TRAILING_PUNCT.search(h))
        self.success = not banned and not punct
        self.score = 1.0 if self.success else 0.0
        reasons = []
        if banned:
            reasons.append("starts with banned filler")
        if punct:
            reasons.append("ends with punctuation")
        self.reason = "; ".join(reasons) or None
        return self.score

    def is_successful(self) -> bool:
        return self.success

    async def a_measure(self, test_case):
        return self.measure(test_case)


class BodyWordCount(BaseMetric):
    """Body must be 30-40 words."""
    name = "BodyWordCount"
    threshold = 1.0

    def measure(self, test_case: LLMTestCase) -> float:
        # Strip HTML tags before counting (jargon busting adds <abbr> tags)
        body = re.sub(r"<[^>]+>", "", test_case.actual_output)
        count = len(body.split())
        self.success = 30 <= count <= 40
        self.score = 1.0 if self.success else 0.0
        self.reason = f"{count} words (expected 30-40)" if not self.success else None
        return self.score

    def is_successful(self) -> bool:
        return self.success

    async def a_measure(self, test_case):
        return self.measure(test_case)


class BodyNoExclamation(BaseMetric):
    """No exclamation marks in body."""
    name = "BodyNoExclamation"
    threshold = 1.0

    def measure(self, test_case: LLMTestCase) -> float:
        self.success = "!" not in test_case.actual_output
        self.score = 1.0 if self.success else 0.0
        self.reason = "contains exclamation mark" if not self.success else None
        return self.score

    def is_successful(self) -> bool:
        return self.success

    async def a_measure(self, test_case):
        return self.measure(test_case)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_metric(metric: BaseMetric, output: str) -> bool:
    tc = LLMTestCase(input="", actual_output=output)
    metric.measure(tc)
    return metric.is_successful()


# ── Tests: good summaries should pass all metrics ────────────────────────────

@pytest.mark.parametrize("summary", GOOD_SUMMARIES, ids=[s.url for s in GOOD_SUMMARIES])
def test_good_headline_word_count(summary: Summary):
    assert _run_metric(HeadlineWordCount(), summary.headline), \
        f"Headline '{summary.headline}' has {len(summary.headline.split())} words"


@pytest.mark.parametrize("summary", GOOD_SUMMARIES, ids=[s.url for s in GOOD_SUMMARIES])
def test_good_headline_no_banned_phrases(summary: Summary):
    m = HeadlineNoBannedPhrases()
    assert _run_metric(m, summary.headline), m.reason


@pytest.mark.parametrize("summary", GOOD_SUMMARIES, ids=[s.url for s in GOOD_SUMMARIES])
def test_good_body_word_count(summary: Summary):
    m = BodyWordCount()
    assert _run_metric(m, summary.body), m.reason


@pytest.mark.parametrize("summary", GOOD_SUMMARIES, ids=[s.url for s in GOOD_SUMMARIES])
def test_good_body_no_exclamation(summary: Summary):
    assert _run_metric(BodyNoExclamation(), summary.body)


# ── Tests: bad summaries should fail at least one metric ─────────────────────

def test_bad_summary_headline_fails_word_count():
    bad = BAD_SUMMARIES[0]
    assert not _run_metric(HeadlineWordCount(), bad.headline)


def test_bad_summary_headline_fails_banned_phrases():
    bad = BAD_SUMMARIES[0]
    assert not _run_metric(HeadlineNoBannedPhrases(), bad.headline)


def test_bad_summary_body_fails_word_count():
    bad = BAD_SUMMARIES[0]
    assert not _run_metric(BodyWordCount(), bad.body)


def test_bad_summary_body_fails_exclamation():
    bad = BAD_SUMMARIES[1]
    # headline contains "!!!" — check body metric doesn't false-positive
    assert _run_metric(BodyNoExclamation(), bad.body)  # body itself is clean


# ── Trim helper tests ─────────────────────────────────────────────────────────

def test_trim_body_within_limit():
    from newstome.summarize import _trim_body
    text = " ".join(["word"] * 35)
    assert _trim_body(text) == text


def test_trim_body_cuts_at_sentence():
    from newstome.summarize import _trim_body
    # Sentence boundary is in the first half, so hard-cut applies
    text = "First sentence ends here. " + " ".join(["extra"] * 20)
    result = _trim_body(text)
    assert len(result.split()) <= 41  # cut at 40 words max


def test_trim_body_hard_cut():
    from newstome.summarize import _trim_body
    # No sentence boundary — should hard-cut and add period
    text = " ".join(["word"] * 50)
    result = _trim_body(text)
    assert len(result.split()) <= 41  # 40 words + trailing "."
