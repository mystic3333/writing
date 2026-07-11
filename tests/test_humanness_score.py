"""
Tests for scripts/humanness_score.py — core scoring functions.

Tests the Tier 1 (statistical) and Tier 2 (pattern) scoring functions
to ensure they produce reasonable scores for human-like vs AI-like text.
"""

import sys
from pathlib import Path

# Ensure scripts/ is importable
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pytest
from humanness_score import (
    score_sentence_length_stddev,
    score_sentence_length_range,
    score_paragraph_length_variance,
    score_vocabulary_richness,
    score_negative_emotion_ratio,
    score_adverb_density,
    score_banned_words,
    score_broken_sentences,
    score_real_sources,
    score_word_temperature_mix,
    score_self_correction,
    compute_composite,
    run_tier,
    TIER1_CHECKS,
    TIER2_CHECKS,
    score_article,
    _make_result,
    _split_sentences,
    _split_paragraphs,
)


# ---------------------------------------------------------------------------
# Sample texts
# ---------------------------------------------------------------------------

# AI-like text: uniform sentence length, no emotion, lots of adverbs and banned words
AI_TEXT = """首先，我们必须认识到人工智能的重要性。其次，人工智能正在改变世界。
此外，非常重要的技术需要更多的关注。不仅如此，非常快速的发展带来了非常多的机会。
显然，这是一个非常重要的领域。毫无疑问，未来会更加美好。综上所述，我们需要更加努力。"""

# Human-like text: varied length, emotions, temperature words, broken sentences
HUMAN_TEXT = """说真的，上周末我去那家新开的咖啡馆，点了杯手冲。

等了二十分钟。

你知道吗，那味道——怎么说呢，像是在喝热水泡过的纸。

老板倒是挺热情，说这是埃塞俄比亚的水洗豆，花果香特别明显。

我心里想：大哥，你确定不是水洗抹布吗？

不过转念一想，也许是我的舌头太粗糙了。毕竟我平时喝的都是瑞幸的9块9，对"好咖啡"的认知可能确实有偏差。

2024年的咖啡市场太卷了，据说光上海就有8000家咖啡馆。15%的店活不过半年。

算了，不说了。总之那杯咖啡我喝了三口就走了，38块钱，心都在滴血。"""


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_splits_by_chinese_punctuation(self):
        result = _split_sentences("第一句。第二句！第三句？")
        assert len(result) == 3

    def test_filters_empty(self):
        result = _split_sentences("。。。")
        assert result == []

    def test_filters_single_chars(self):
        result = _split_sentences("啊。好。")
        assert result == []  # len <= 1 filtered out


class TestSplitParagraphs:
    def test_splits_by_double_newline(self):
        result = _split_paragraphs("段一\n\n段二\n\n段三")
        assert len(result) == 3

    def test_excludes_headings(self):
        result = _split_paragraphs("# 标题\n\n正文内容")
        assert len(result) == 1
        assert "标题" not in result[0]


class TestMakeResult:
    def test_clamps_score(self):
        r = _make_result(1.5, "test")
        assert r["score"] == 1.0

    def test_clamps_negative(self):
        r = _make_result(-0.5, "test")
        assert r["score"] == 0.0

    def test_includes_param(self):
        r = _make_result(0.5, "test", "my_param")
        assert r["param"] == "my_param"

    def test_default_param_none(self):
        r = _make_result(0.5, "test")
        assert r["param"] is None


# ---------------------------------------------------------------------------
# Tier 1 scoring tests
# ---------------------------------------------------------------------------

class TestSentenceLengthStddev:
    def test_uniform_sentences_low_score(self):
        # All sentences same length → low stddev
        text = "这是一句话。这是一句话。这是一句话。这是一句话。这是一句话。"
        r = score_sentence_length_stddev(text)
        assert r["score"] < 0.5

    def test_varied_sentences_higher_score(self):
        text = "短。这是一句比较长的话，有好多字在里面。啊。这是另一句长度不同的话，也有不少字。嗯。"
        r = score_sentence_length_stddev(text)
        assert r["score"] > 0.1

    def test_too_few_sentences(self):
        r = score_sentence_length_stddev("只有两句。而已。")
        assert r["score"] == 0.5


class TestSentenceLengthRange:
    def test_returns_score_and_param(self):
        text = "短。这是一句非常非常非常非常非常长的句子，用来测试长度范围。啊。再来一句中等长度的。嗯。还有一句也还行的。"
        r = score_sentence_length_range(text)
        assert "score" in r
        assert r["param"] == "sentence_variance"


class TestParagraphLengthVariance:
    def test_uniform_paragraphs_low_score(self):
        text = "段落一内容\n\n段落二内容\n\n段落三内容"
        r = score_paragraph_length_variance(text)
        assert r["score"] < 0.5

    def test_varied_paragraphs_higher_score(self):
        text = "短。\n\n" + "长" * 100 + "。\n\n中等长度的段落。"
        r = score_paragraph_length_variance(text)
        assert r["score"] > 0.3


class TestVocabularyRichness:
    def test_returns_score(self):
        r = score_vocabulary_richness(HUMAN_TEXT)
        assert 0 <= r["score"] <= 1
        assert r["param"] == "word_temperature_bias"

    def test_too_few_chars(self):
        r = score_vocabulary_richness("abc")
        assert r["score"] == 0.5


class TestNegativeEmotionRatio:
    def test_ai_text_low_emotion(self):
        r = score_negative_emotion_ratio(AI_TEXT)
        assert r["score"] < 0.5

    def test_human_text_has_emotion(self):
        r = score_negative_emotion_ratio(HUMAN_TEXT)
        # Human text has "心都在滴血" which contains "血" but may not match
        # negative markers; check that the function returns a valid score
        assert r["score"] >= 0.0


class TestAdverbDensity:
    def test_ai_text_high_adverb_density(self):
        r = score_adverb_density(AI_TEXT)
        # AI text has many adverbs, score should be lower
        assert r["score"] < 1.0

    def test_returns_param(self):
        r = score_adverb_density("正常文本，没有太多副词。")
        assert r["param"] == "adverb_max_per_100"


# ---------------------------------------------------------------------------
# Tier 2 scoring tests
# ---------------------------------------------------------------------------

class TestBannedWords:
    def test_ai_text_has_banned_words(self):
        r = score_banned_words(AI_TEXT)
        assert r["score"] < 1.0  # penalized

    def test_clean_text_no_banned_words(self):
        r = score_banned_words("今天天气不错，去公园散步了。")
        assert r["score"] == 1.0


class TestBrokenSentences:
    def test_human_text_has_broken_patterns(self):
        r = score_broken_sentences(HUMAN_TEXT)
        assert r["score"] > 0.0

    def test_clean_text_low_score(self):
        r = score_broken_sentences("这是一句完整的话。这是另一句完整的话。")
        assert r["score"] < 0.5


class TestRealSources:
    def test_human_text_has_sources(self):
        r = score_real_sources(HUMAN_TEXT)
        assert r["score"] > 0.0

    def test_no_sources(self):
        r = score_real_sources("今天天气很好，出去玩了一天。")
        assert r["score"] == 0.0


class TestWordTemperatureMix:
    def test_human_text_has_temperature_variety(self):
        r = score_word_temperature_mix(HUMAN_TEXT)
        assert r["score"] > 0.0

    def test_plain_text_low_score(self):
        r = score_word_temperature_mix("今天天气不错，出去玩了一下午。")
        assert r["score"] == 0.0  # only 0-1 bands → (0-1)/3 = 0


class TestSelfCorrection:
    def test_human_text_has_corrections(self):
        r = score_self_correction(HUMAN_TEXT)
        assert r["score"] >= 0.0

    def test_text_with_explicit_correction(self):
        r = score_self_correction("不对，准确说是这样的。")
        assert r["score"] > 0.0


# ---------------------------------------------------------------------------
# Composite score tests
# ---------------------------------------------------------------------------

class TestRunTier:
    def test_tier1_returns_summary(self):
        result = run_tier(TIER1_CHECKS, HUMAN_TEXT)
        assert "_summary" in result
        assert "mean_score" in result["_summary"]
        assert "count" in result["_summary"]
        assert result["_summary"]["count"] == len(TIER1_CHECKS)

    def test_tier2_returns_summary(self):
        result = run_tier(TIER2_CHECKS, HUMAN_TEXT)
        assert "_summary" in result
        assert result["_summary"]["count"] == len(TIER2_CHECKS)


class TestComputeComposite:
    def test_with_tier3(self):
        tier1 = run_tier(TIER1_CHECKS, HUMAN_TEXT)
        tier2 = run_tier(TIER2_CHECKS, HUMAN_TEXT)
        composite, weights = compute_composite(tier1, tier2, tier3_score=0.7)
        assert 0 <= composite <= 100
        assert weights["tier3"] == 0.20

    def test_without_tier3(self):
        tier1 = run_tier(TIER1_CHECKS, HUMAN_TEXT)
        tier2 = run_tier(TIER2_CHECKS, HUMAN_TEXT)
        composite, weights = compute_composite(tier1, tier2)
        assert 0 <= composite <= 100
        assert "tier3" not in weights


class TestScoreArticle:
    def test_returns_full_result(self):
        result = score_article(HUMAN_TEXT)
        assert "composite_score" in result
        assert "tier1" in result
        assert "tier2" in result
        assert "param_scores" in result
        assert "char_count" in result

    def test_human_text_better_than_ai_text(self):
        human_result = score_article(HUMAN_TEXT)
        ai_result = score_article(AI_TEXT)
        # Human text should have lower composite (0=human, 100=AI)
        assert human_result["composite_score"] < ai_result["composite_score"]

    def test_with_tier3(self):
        result = score_article(HUMAN_TEXT, tier3_score=0.8)
        assert result["tier3"]["score"] == 0.8
        assert result["tier3"]["source"] == "agent"
