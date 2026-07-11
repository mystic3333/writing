"""
Tests for scripts/word_lists.py — shared word lists and pattern matching.

These tests guard against the word list divergence bug that was previously
present when BANNED_WORDS, WILD_WORDS, etc. were duplicated across
humanness_score.py and inline_check.py with different content.
"""

import sys
from pathlib import Path

# Ensure scripts/ is importable
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pytest
from word_lists import (
    BANNED_WORDS,
    NEGATIVE_MARKERS,
    COMMON_ADVERBS,
    COLD_WORDS,
    WARM_WORDS,
    HOT_WORDS,
    WILD_WORDS,
    REAL_SOURCE_PATTERNS,
    find_banned_words,
    find_negative_markers,
    count_adverbs,
    count_temperature_words,
    find_real_sources,
    find_real_sources_in_section,
    count_broken_sentences,
    count_self_corrections,
)


# ---------------------------------------------------------------------------
# Word list integrity
# ---------------------------------------------------------------------------

class TestWordListIntegrity:
    """Verify word lists are non-empty and contain expected entries."""

    def test_banned_words_not_empty(self):
        assert len(BANNED_WORDS) > 30

    def test_banned_words_contains_known_ai_cliches(self):
        assert "首先" in BANNED_WORDS
        assert "综上所述" in BANNED_WORDS
        assert "众所周知" in BANNED_WORDS

    def test_negative_markers_not_empty(self):
        assert len(NEGATIVE_MARKERS) > 30

    def test_negative_markers_contains_emotions(self):
        assert "焦虑" in NEGATIVE_MARKERS
        assert "崩溃" in NEGATIVE_MARKERS
        assert "割韭菜" in NEGATIVE_MARKERS

    def test_adverbs_not_empty(self):
        assert len(COMMON_ADVERBS) > 20

    def test_temperature_words_not_empty(self):
        assert len(COLD_WORDS) > 10
        assert len(WARM_WORDS) > 5
        assert len(HOT_WORDS) > 5
        assert len(WILD_WORDS) > 10

    def test_wild_words_contains_merged_entries(self):
        """WILD_WORDS should contain the union of both previous lists."""
        # From humanness_score.py
        assert "摔了跤" in WILD_WORDS
        assert "踩坑" in WILD_WORDS
        assert "翻车" in WILD_WORDS
        # From inline_check.py
        assert "整" in WILD_WORDS
        assert "贼" in WILD_WORDS
        assert "无语子" in WILD_WORDS

    def test_real_source_patterns_not_empty(self):
        assert len(REAL_SOURCE_PATTERNS) >= 6

    def test_no_duplicates_in_lists(self):
        for lst in [BANNED_WORDS, NEGATIVE_MARKERS, COMMON_ADVERBS,
                    COLD_WORDS, WARM_WORDS, HOT_WORDS]:
            assert len(lst) == len(set(lst)), f"Duplicates in {lst}"


# ---------------------------------------------------------------------------
# Pattern matching functions
# ---------------------------------------------------------------------------

class TestFindBannedWords:
    def test_finds_banned_word(self):
        result = find_banned_words("首先，我们要讨论这个问题。")
        assert "首先" in result

    def test_finds_multiple_banned_words(self):
        result = find_banned_words("首先，其次，最后。综上所述。")
        assert "首先" in result
        assert "其次" in result
        assert "最后" in result
        assert "综上所述" in result

    def test_no_banned_words(self):
        result = find_banned_words("这是一段普通的文章，没有AI套话。")
        assert result == []

    def test_empty_text(self):
        assert find_banned_words("") == []


class TestFindNegativeMarkers:
    def test_finds_negative_marker(self):
        result = find_negative_markers("这个产品太糟糕了。")
        assert "糟糕" in result

    def test_finds_multiple_markers(self):
        result = find_negative_markers("我很焦虑，也很崩溃。")
        assert "焦虑" in result
        assert "崩溃" in result

    def test_no_markers(self):
        result = find_negative_markers("今天天气真好，心情愉快。")
        assert result == []


class TestCountAdverbs:
    def test_counts_single_adverb(self):
        assert count_adverbs("这个非常好看") == 1

    def test_counts_multiple_adverbs(self):
        count = count_adverbs("非常快速地增长，显然很成功。")
        assert count >= 2

    def test_no_adverbs(self):
        assert count_adverbs("昨天去买了杯咖啡。") == 0


class TestCountTemperatureWords:
    def test_counts_cold_words(self):
        result = count_temperature_words("这个商业模式有很强的护城河。")
        assert result["cold"] >= 2  # 商业模式, 护城河

    def test_counts_warm_words(self):
        result = count_temperature_words("说白了，这事很简单。")
        assert result["warm"] >= 1

    def test_counts_hot_words(self):
        result = count_temperature_words("这个行业太卷了。")
        assert result["hot"] >= 1

    def test_counts_wild_words(self):
        result = count_temperature_words("整挺好，不靠谱。")
        assert result["wild"] >= 2

    def test_mixed_temperatures(self):
        result = count_temperature_words("说白了，这个护城河太卷了，整挺好。")
        assert result["warm"] >= 1
        assert result["cold"] >= 1
        assert result["hot"] >= 1
        assert result["wild"] >= 1

    def test_no_temperature_words(self):
        result = count_temperature_words("今天天气不错。")
        assert all(v == 0 for v in result.values())


class TestFindRealSources:
    def test_finds_percentage(self):
        result = find_real_sources("增长了15.5%")
        assert len(result) >= 1

    def test_finds_year(self):
        result = find_real_sources("2024年的数据显示")
        assert len(result) >= 1

    def test_finds_named_platform(self):
        result = find_real_sources("在GitHub上开源了")
        assert len(result) >= 1

    def test_finds_money_amount(self):
        result = find_real_sources("估值10亿美元")
        assert len(result) >= 1

    def test_finds_chinese_attribution(self):
        result = find_real_sources("据报告显示，专家指出")
        # At least one attribution pattern should match
        assert len(result) >= 1

    def test_no_sources(self):
        result = find_real_sources("这是一个普通句子。")
        assert result == []


class TestFindRealSourcesInSection:
    def test_deduplicates(self):
        text = "2024年增长了15%。2024年又是好的一年。"
        result = find_real_sources_in_section(text)
        # "2024年" appears twice but should be deduplicated
        assert len(result) < len(find_real_sources(text))

    def test_returns_list(self):
        result = find_real_sources_in_section("无数据")
        assert isinstance(result, list)


class TestCountBrokenSentences:
    def test_score_mode_counts_ellipsis(self):
        count = count_broken_sentences("说了一半...", mode="score")
        assert count >= 1

    def test_score_mode_counts_em_dash(self):
        count = count_broken_sentences("其实——", mode="score")
        assert count >= 1

    def test_check_mode_is_broader(self):
        text = "说白了，这事不好办。"
        score_count = count_broken_sentences(text, mode="score")
        check_count = count_broken_sentences(text, mode="check")
        assert check_count >= score_count

    def test_empty_text(self):
        assert count_broken_sentences("") == 0


class TestCountSelfCorrections:
    def test_finds_self_correction(self):
        count = count_self_corrections("不对，准确说是这样的。")
        assert count >= 1

    def test_finds_parenthetical(self):
        count = count_self_corrections("这个（其实不太确定）想法")
        assert count >= 1

    def test_no_self_corrections(self):
        assert count_self_corrections("今天天气很好。") == 0
