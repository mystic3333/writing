#!/usr/bin/env python3
"""
Humanness scoring for WeWrite articles.

Three-tier evaluation aligned with writing-guide.md's anti-AI checklist:

  Tier 1 (Statistical, 50%): 6 checks measuring statistical properties
         that AI detectors analyze (burstiness, distribution, variance).
  Tier 2 (Pattern, 30%):     5 checks for specific linguistic patterns
         (banned words, broken sentences, real sources).
  Tier 3 (LLM, 20%):        Semantic analysis done by the agent in SKILL.md
         (style drift, density waves, coherence). Passed via --tier3 flag.

Each check outputs a continuous 0-1 score and maps to a writing-config
parameter, so the optimization loop knows which knob to turn.

Standalone mode (no --tier3): weights redistribute to T1=62.5%, T2=37.5%.

Usage:
    python3 humanness_score.py article.md                    # single score
    python3 humanness_score.py article.md --verbose          # detailed report
    python3 humanness_score.py article.md --json             # full JSON
    python3 humanness_score.py article.md --json --tier3 0.7 # with agent score
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Import shared word lists and patterns (single source of truth)
from word_lists import (
    BANNED_WORDS,
    NEGATIVE_MARKERS,
    COMMON_ADVERBS,
    COLD_WORDS,
    WARM_WORDS,
    HOT_WORDS,
    WILD_WORDS,
    REAL_SOURCE_PATTERNS,
    SELF_CORRECTION_PATTERNS,
    BROKEN_SENTENCE_PATTERNS_SCORE as BROKEN_SENTENCE_PATTERNS,
    # Pre-compiled helper functions for performance
    find_banned_words,
    find_negative_markers,
    count_adverbs as _count_adverbs,
    count_temperature_words,
    find_real_sources as _find_real_sources,
    count_broken_sentences as _count_broken,
    count_self_corrections as _count_self_corrections,
)


# ============================================================
# Helpers
# ============================================================

def _split_sentences(text):
    """Split text by Chinese sentence-ending and clause-level punctuation."""
    sentences = re.split(r'[。！？；;…\n]', text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 1]


def _split_paragraphs(text):
    """Split text into paragraphs, excluding headings."""
    return [p.strip() for p in text.split('\n\n')
            if p.strip() and not p.strip().startswith('#')]


def _make_result(score, detail, param=None):
    """Create a check result dict."""
    r = {"score": round(max(0.0, min(1.0, score)), 4), "detail": detail}
    if param is not None:
        r["param"] = param
    else:
        r["param"] = None
    return r


# ============================================================
# Tier 1: Statistical Checks (weight 50%)
# ============================================================

def score_sentence_length_stddev(text):
    """[1.1] Sentence length standard deviation. → sentence_variance"""
    sentences = _split_sentences(text)
    if len(sentences) < 5:
        return _make_result(0.5, "too few sentences to measure", "sentence_variance")
    lengths = [len(s) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    stddev = variance ** 0.5
    score = min(1.0, stddev / 25.0)
    return _make_result(score, f"stddev={stddev:.1f} (target ≥15)", "sentence_variance")


def score_sentence_length_range(text):
    """[1.1] Sentence length range (max - min). → sentence_variance"""
    sentences = _split_sentences(text)
    if len(sentences) < 5:
        return _make_result(0.5, "too few sentences", "sentence_variance")
    lengths = [len(s) for s in sentences]
    rng = max(lengths) - min(lengths)
    range_score = min(1.0, rng / 40.0)
    # Check for single-sentence short paragraphs
    lines = text.split('\n')
    short_paras = sum(1 for l in lines if l.strip() and 1 <= len(l.strip()) <= 5
                      and not l.strip().startswith('#'))
    expected = max(1, len(text) / 500)
    short_score = min(1.0, short_paras / expected)
    score = range_score * 0.6 + short_score * 0.4
    return _make_result(score, f"range={rng} (target ≥30), short_paras={short_paras}", "sentence_variance")


def score_paragraph_length_variance(text):
    """[1.3] Paragraph length variance. → paragraph_rhythm"""
    paragraphs = _split_paragraphs(text)
    if len(paragraphs) < 3:
        return _make_result(0.5, "too few paragraphs", "paragraph_rhythm")
    total_pairs = len(paragraphs) - 1
    similar = sum(1 for i in range(total_pairs)
                  if abs(len(paragraphs[i]) - len(paragraphs[i + 1])) <= 20)
    score = 1.0 - (similar / total_pairs) if total_pairs > 0 else 0.5
    return _make_result(score, f"{similar}/{total_pairs} consecutive similar-length pairs", "paragraph_rhythm")


def score_vocabulary_richness(text):
    """[1.2] CJK bigram type-token ratio + temperature mix. → word_temperature_bias"""
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(cjk_chars) < 20:
        return _make_result(0.5, "too few CJK characters", "word_temperature_bias")
    bigrams = [cjk_chars[i] + cjk_chars[i + 1] for i in range(len(cjk_chars) - 1)]
    ttr = len(set(bigrams)) / len(bigrams) if bigrams else 0
    ttr_score = min(1.0, ttr / 0.7)
    # Temperature mix bonus — use pre-compiled helper
    temp_counts = count_temperature_words(text)
    found_temps = sum(1 for v in temp_counts.values() if v > 0)
    temp_bonus = found_temps / 4.0 * 0.3
    score = min(1.0, ttr_score * 0.7 + temp_bonus)
    return _make_result(score, f"bigram_ttr={ttr:.3f}, temps={found_temps}/4", "word_temperature_bias")


def score_negative_emotion_ratio(text):
    """[1.4] Negative emotion ratio. → emotional_arc"""
    sentences = _split_sentences(text)
    if not sentences:
        return _make_result(0.5, "no sentences", "emotional_arc")
    # Use pre-compiled pattern for efficiency
    negative_count = sum(1 for s in sentences if find_negative_markers(s))
    ratio = negative_count / len(sentences)
    score = min(1.0, ratio / 0.25)
    return _make_result(score, f"negative={negative_count}/{len(sentences)} ({ratio:.0%}, target ≥20%)", "emotional_arc")


def score_adverb_density(text):
    """[1.5] Adverb density control. → adverb_max_per_100"""
    char_count = len(text)
    if char_count < 50:
        return _make_result(0.5, "text too short", "adverb_max_per_100")
    # Use pre-compiled helper for counting
    total_adverbs = _count_adverbs(text)
    density = total_adverbs / char_count * 100
    # Check consecutive sentences starting with adverbs
    sentences = _split_sentences(text)
    consecutive_adverb_starts = 0
    for i in range(len(sentences) - 1):
        a_starts = any(sentences[i].startswith(adv) for adv in COMMON_ADVERBS)
        b_starts = any(sentences[i + 1].startswith(adv) for adv in COMMON_ADVERBS)
        if a_starts and b_starts:
            consecutive_adverb_starts += 1
    score = 1.0
    if density > 3.0:
        score -= min(0.5, (density - 3.0) * 0.1)
    score -= consecutive_adverb_starts * 0.3
    return _make_result(score, f"density={density:.1f}/100chars, consecutive_starts={consecutive_adverb_starts}", "adverb_max_per_100")


# ============================================================
# Tier 2: Pattern Checks (weight 30%)
# ============================================================

def score_banned_words(text):
    """[2.1] Banned word check. → null (hard rule, no config param)"""
    found = find_banned_words(text)
    score = max(0.0, 1.0 - len(found) * 0.2)
    detail = "0 banned words" if not found else f"{len(found)} found: {found[:5]}"
    return _make_result(score, detail, None)


def score_broken_sentences(text):
    """[2.2] Broken/incomplete sentence patterns. → broken_sentence_rate"""
    # Use pre-compiled helper
    count = _count_broken(text, mode="score")
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if 1 <= len(line) <= 10 and not line.startswith('#'):
            count += 1
    char_count = len(text)
    expected = max(3, char_count / 500 * 3)
    score = min(1.0, count / expected)
    return _make_result(score, f"{count} broken structures (expected ≥{expected:.0f})", "broken_sentence_rate")


def score_real_sources(text):
    """[3.1] Real external source indicators. → real_data_density"""
    count = len(_find_real_sources(text))
    score = min(1.0, count / 5.0)
    return _make_result(score, f"{count} real-source indicators (target ≥5)", "real_data_density")


def score_word_temperature_mix(text):
    """[1.2] Word temperature band coverage. → word_temperature_bias"""
    temp_counts = count_temperature_words(text)
    found_temps = sum(1 for v in temp_counts.values() if v > 0)
    score = max(0.0, (found_temps - 1) / 3.0)
    return _make_result(score, f"{found_temps}/4 temperature bands", "word_temperature_bias")


def score_self_correction(text):
    """[2.2] Self-correction and parenthetical patterns. → self_correction_rate"""
    count = _count_self_corrections(text)
    score = min(1.0, count / 3.0)
    return _make_result(score, f"{count} self-corrections/insertions (target ≥3)", "self_correction_rate")


# ============================================================
# Tier Runners
# ============================================================

TIER1_CHECKS = [
    ("sentence_length_stddev", score_sentence_length_stddev),
    ("sentence_length_range", score_sentence_length_range),
    ("paragraph_length_variance", score_paragraph_length_variance),
    ("vocabulary_richness", score_vocabulary_richness),
    ("negative_emotion_ratio", score_negative_emotion_ratio),
    ("adverb_density", score_adverb_density),
]

TIER2_CHECKS = [
    ("banned_words", score_banned_words),
    ("broken_sentences", score_broken_sentences),
    ("real_sources", score_real_sources),
    ("word_temperature_mix", score_word_temperature_mix),
    ("self_correction", score_self_correction),
]


def run_tier(checks, text):
    """Run a tier of checks. Returns dict keyed by check name + _summary."""
    results = {}
    scores = []
    for name, fn in checks:
        r = fn(text)
        results[name] = r
        scores.append(r["score"])
    results["_summary"] = {
        "count": len(checks),
        "mean_score": round(sum(scores) / len(scores), 4) if scores else 0,
        "scores": [round(s, 4) for s in scores],
    }
    return results


# ============================================================
# Calibration (bell-curve + over-optimization penalty)
# ============================================================

# Human article baselines (from 15 example articles, 2026-03-30)
# Dimensions where AI over-optimizes: bell-curve scoring penalizes
# both "too low" AND "too high" relative to human average.
_BELL_CURVE_CHECKS = {
    "broken_sentences": 0.39,
    "self_correction": 0.20,
    "sentence_length_range": 0.71,
    "paragraph_length_variance": 0.52,
    "banned_words": 0.73,
}


def _bell_curve(raw_score, center):
    """Score peaks at center (human avg), penalizes over-optimization.

    Below center: linear rise (as before).
    Above center: quadratic penalty — too much is suspicious.
    """
    if center <= 0:
        return raw_score
    if raw_score <= center:
        return raw_score / center
    else:
        overshoot = (raw_score - center) / (1.0 - center) if center < 1 else 0
        return max(0.0, 1.0 - overshoot * overshoot)


def calibrate_tiers(tier1, tier2):
    """Apply bell-curve calibration and over-optimization penalty in-place."""
    # 1. Bell-curve adjustment for over-optimizable dimensions
    for tier in [tier1, tier2]:
        for name, data in tier.items():
            if name.startswith("_"):
                continue
            if name in _BELL_CURVE_CHECKS:
                raw = data["score"]
                center = _BELL_CURVE_CHECKS[name]
                calibrated = round(max(0.0, min(1.0, _bell_curve(raw, center))), 4)
                data["raw_score"] = raw
                data["score"] = calibrated
                data["detail"] += f" [calibrated from {raw:.2f}, center={center}]"

    # 2. Over-optimization penalty: if 60%+ of checks score > 0.8,
    #    the article is suspiciously "perfect" — apply global penalty.
    all_scores = []
    for tier in [tier1, tier2]:
        for name, data in tier.items():
            if not name.startswith("_"):
                all_scores.append(data["score"])

    high_count = sum(1 for s in all_scores if s > 0.8)
    over_opt_ratio = high_count / len(all_scores) if all_scores else 0
    penalty = 1.0
    if over_opt_ratio >= 0.6:
        penalty = 0.85  # 15% penalty for suspiciously perfect articles

    if penalty < 1.0:
        for tier in [tier1, tier2]:
            for name, data in tier.items():
                if not name.startswith("_"):
                    data["score"] = round(data["score"] * penalty, 4)

    # 3. Recalculate tier summaries
    for tier in [tier1, tier2]:
        scores = [data["score"] for name, data in tier.items() if not name.startswith("_")]
        tier["_summary"]["mean_score"] = round(sum(scores) / len(scores), 4) if scores else 0
        tier["_summary"]["scores"] = [round(s, 4) for s in scores]

    return penalty


# ============================================================
# Composite Score
# ============================================================

def compute_composite(tier1, tier2, tier3_score=None):
    """Compute composite score (0=human, 100=AI).

    With tier3: T1=50%, T2=30%, T3=20%
    Without:    T1=62.5%, T2=37.5%
    """
    t1_mean = tier1["_summary"]["mean_score"]
    t2_mean = tier2["_summary"]["mean_score"]

    if tier3_score is not None:
        humanness = t1_mean * 0.50 + t2_mean * 0.30 + tier3_score * 0.20
        weights = {"tier1": 0.50, "tier2": 0.30, "tier3": 0.20}
    else:
        humanness = t1_mean * 0.625 + t2_mean * 0.375
        weights = {"tier1": 0.625, "tier2": 0.375}

    composite = round((1 - humanness) * 100, 2)
    return composite, weights


def build_param_scores(tier1, tier2):
    """Build flat param→score map for optimization. Averages if multiple checks map to same param."""
    param_map = {}
    for tier in [tier1, tier2]:
        for name, data in tier.items():
            if name.startswith("_"):
                continue
            param = data.get("param")
            if param is None:
                continue
            if param not in param_map:
                param_map[param] = []
            param_map[param].append(data["score"])
    return {p: round(sum(scores) / len(scores), 4) for p, scores in param_map.items()}


# ============================================================
# Main API
# ============================================================

def score_article(text, verbose=False, tier3_score=None):
    """Score an article. Returns full results dict."""
    clean = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE).strip()

    tier1 = run_tier(TIER1_CHECKS, clean)
    tier2 = run_tier(TIER2_CHECKS, clean)
    over_opt_penalty = calibrate_tiers(tier1, tier2)
    composite, weights = compute_composite(tier1, tier2, tier3_score)
    param_scores = build_param_scores(tier1, tier2)

    result = {
        "composite_score": composite,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": {
            "score": tier3_score,
            "source": "agent" if tier3_score is not None else "not_available",
        },
        "weights": weights,
        "param_scores": param_scores,
        "over_optimization_penalty": over_opt_penalty,
        "char_count": len(clean),
    }

    if verbose:
        _print_verbose(result)

    return result


def _print_verbose(result):
    """Print a human-readable report."""
    composite = result["composite_score"]
    print(f"\n{'=' * 60}")
    print(f"HUMANNESS SCORE: {composite:.1f}/100 (lower = more human)")
    print(f"{'=' * 60}")

    for tier_name, tier_label, weight in [
        ("tier1", "Tier 1 — Statistical", result["weights"].get("tier1", 0)),
        ("tier2", "Tier 2 — Pattern", result["weights"].get("tier2", 0)),
    ]:
        tier = result[tier_name]
        summary = tier["_summary"]
        print(f"\n{tier_label} (weight {weight:.0%}, mean {summary['mean_score']:.2f})")
        for name, data in tier.items():
            if name.startswith("_"):
                continue
            bar = "█" * int(data["score"] * 10) + "░" * (10 - int(data["score"] * 10))
            param_tag = f" [{data['param']}]" if data.get("param") else ""
            print(f"  {bar} {data['score']:.2f}  {name}{param_tag}")
            print(f"         {data['detail']}")

    t3 = result["tier3"]
    if t3["score"] is not None:
        t3_weight = result["weights"].get("tier3", 0)
        print(f"\nTier 3 — LLM (weight {t3_weight:.0%})")
        print(f"  Score: {t3['score']:.2f} (source: {t3['source']})")
    else:
        print(f"\nTier 3 — LLM: not available (standalone mode)")

    print(f"\nComposite: {composite:.1f} (0=完美人类, 100=明显AI)")
    print(f"Weights: {result['weights']}")

    param_scores = result["param_scores"]
    if param_scores:
        sorted_params = sorted(param_scores.items(), key=lambda x: x[1])
        print(f"\nLowest-scoring parameters (optimize these first):")
        for param, score in sorted_params[:3]:
            print(f"  {param}: {score:.2f}")


# ============================================================
# Calibration Baselines
# ============================================================

CALIBRATION_BASELINES = {
    "pure_ai": {
        "label": "Pure AI (typical ChatGPT output)",
        "expected_composite_min": 75,
        "expected_composite_max": 85,
    },
    "ai_with_editing": {
        "label": "AI draft + human editing",
        "expected_composite_min": 40,
        "expected_composite_max": 55,
    },
    "human_written": {
        "label": "Genuine human blog post",
        "expected_composite_min": 15,
        "expected_composite_max": 30,
    },
    "target_range": {
        "label": "WeWrite target range",
        "expected_composite_min": 25,
        "expected_composite_max": 45,
    },
}


def _calibration_verdict(result):
    """Return calibration info dict with target range and verdict."""
    composite = result["composite_score"]
    target = CALIBRATION_BASELINES["target_range"]
    t_min = target["expected_composite_min"]
    t_max = target["expected_composite_max"]
    if composite <= t_max:
        if composite >= t_min:
            verdict = "PASS: within target range"
        else:
            verdict = "PASS: below target (very human-like)"
    else:
        verdict = "WARNING: above target, needs more humanization"
    return {
        "target_min": t_min,
        "target_max": t_max,
        "verdict": verdict,
    }


def _print_calibration(result):
    """Print calibration comparison table."""
    composite = result["composite_score"]
    cal = _calibration_verdict(result)

    print(f"\n{'=' * 60}")
    print(f"CALIBRATION COMPARISON")
    print(f"{'=' * 60}")
    print(f"  Your article:  {composite:.1f}")
    print()
    for key, baseline in CALIBRATION_BASELINES.items():
        lo = baseline["expected_composite_min"]
        hi = baseline["expected_composite_max"]
        marker = ""
        if key == "target_range":
            if lo <= composite <= hi:
                marker = "  <-- YOUR SCORE IS HERE"
            elif composite < lo:
                marker = "  (your score is below this)"
            else:
                marker = "  (your score is above this)"
        elif lo <= composite <= hi:
            marker = "  <-- YOUR SCORE IS HERE"
        print(f"  {baseline['label']:.<40s} {lo}-{hi}{marker}")
    print()
    print(f"  Verdict: {cal['verdict']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Score article humanness (0=human, 100=AI)")
    parser.add_argument("input", help="Markdown article file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed report")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--tier3", type=float, default=None,
                        help="Tier 3 LLM score (0-1), passed by agent from SKILL.md")
    parser.add_argument("--calibrate", action="store_true",
                        help="Compare scores against calibration baselines")
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    result = score_article(text, verbose=args.verbose, tier3_score=args.tier3)

    if args.calibrate:
        _print_calibration(result)

    if args.json:
        if args.verbose or args.calibrate:
            result["calibration"] = _calibration_verdict(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.verbose and not args.calibrate:
        print(f"{result['composite_score']:.1f}")


if __name__ == "__main__":
    main()
