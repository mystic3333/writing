"""
Shared word lists and regex patterns for article quality checking.

Used by both humanness_score.py and inline_check.py to ensure consistent
evaluation across Step 4.5 (inline check) and Step 5.3 (humanness scoring).

Previously these lists were duplicated in both files and had diverged —
WILD_WORDS and REAL_SOURCE_PATTERNS were different. This module is the
single source of truth.
"""

import re

# ============================================================
# Banned words — AI cliché phrases that should never appear
# ============================================================

BANNED_WORDS = [
    "首先", "其次", "再者", "最后", "总之", "综上所述", "总而言之",
    "此外", "另外", "与此同时", "不仅如此", "更重要的是", "在此基础上",
    "作为一个", "让我们", "值得注意的是", "需要指出的是", "不可否认",
    "毋庸置疑", "众所周知", "事实上", "显而易见", "可以说", "从某种意义上说",
    "非常重要", "至关重要", "不言而喻", "具有重要意义", "发挥着重要作用",
    "意义深远", "影响深远", "引发了广泛关注", "引起了热烈讨论",
    "总的来说", "综合来看", "由此可见", "不难发现", "通过以上分析",
    "正如我们所看到的",
]

# ============================================================
# Negative emotion markers
# ============================================================

NEGATIVE_MARKERS = [
    # 直接负面情绪
    "失望", "糟糕", "扯", "坑", "烂", "差劲", "崩溃", "吐槽", "骂",
    "怒", "烦", "焦虑", "担忧", "不满", "恶心", "可怕", "可悲", "可笑",
    "离谱", "尴尬", "无语", "蠢", "惨", "亏", "危",
    # 绝望/迷茫
    "绝望", "迷茫", "心累", "丧", "后悔", "后怕", "心寒",
    # 欺骗/操控（隐性负面）
    "骗", "忽悠", "割韭菜", "套路", "画大饼", "洗脑",
    # 失败/徒劳
    "白费", "白搭", "没戏", "黄了", "凉了", "废了",
    # 自嘲/自贬
    "傻", "天真", "吃亏", "自嗨", "打脸",
    # 讽刺/反语
    "呵呵", "好吧", "行吧", "真服了",
    # 短语
    "太扯了", "说实话我很失望", "搞什么", "不靠谱", "受不了",
    "受够了", "想哭", "伤心", "苦哈哈", "得过且过",
]

# ============================================================
# Common adverbs — AI overuses these
# ============================================================

COMMON_ADVERBS = [
    "非常", "十分", "极其", "特别", "相当", "尤其", "格外",
    "更加", "越来越", "逐渐", "不断", "始终", "一直",
    "已经", "正在", "将要", "可能", "大概", "或许",
    "似乎", "显然", "明显", "确实", "果然", "居然",
    "竟然", "简直", "几乎", "完全", "绝对", "必然",
]

# ============================================================
# Word temperature bands
# ============================================================

COLD_WORDS = [
    "边际", "认知负荷", "信息不对称", "路径依赖", "商业模式", "生态系统", "增量",
    "技术栈", "标准化", "结构性", "规模化", "护城河", "飞轮", "闭环",
    "赛道", "壁垒", "方法论", "底层逻辑", "第一性原理", "杠杆", "复利",
    "ROI", "PMF", "代运营", "供给侧", "需求侧",
]

WARM_WORDS = [
    "说白了", "其实吧", "讲真", "说实话", "坦白讲", "懂的都懂", "怎么说呢",
    "老实说", "这么说吧", "你想啊", "别急", "慢慢来",
    "有意思的是", "好玩的是", "巧的是", "说来话长", "话说回来",
]

HOT_WORDS = [
    "DNA动了", "格局打开", "遥遥领先", "卷", "内卷", "炸了", "杀疯了", "吃灰",
    "凡尔赛", "标题党", "躺平", "摆烂", "破防", "上头", "内耗",
    "蒸发", "出圈", "降维打击", "弯道超车",
]

# WILD_WORDS — merged union of both files' lists (they had diverged)
WILD_WORDS = [
    "整挺好", "不靠谱", "瞎折腾", "搁这儿", "糊弄", "扯", "嗯",
    "苦哈哈", "傻乎乎", "稀里糊涂", "得了吧", "算了吧",
    "摔了跤", "交学费", "踩坑", "翻车", "栽了",
    # from inline_check.py (not in humanness_score.py previously)
    "整", "贼", "特", "巨", "超", "老", "超纲", "无语子", "绝了",
]

# ============================================================
# Real source indicator patterns
# ============================================================

# Merged union: humanness_score.py had 6, inline_check.py had 7 (different items)
REAL_SOURCE_PATTERNS = [
    r'[A-Z][a-z]+\s+[A-Z][a-z]+',
    r'[\u4e00-\u9fff]{2,4}(?:表示|指出|认为|写道|提到|说过|评论)',
    r'(?:据|根据|来自)\s*[\u4e00-\u9fff]+(?:报告|数据|研究|调查|分析)',
    r'20[12]\d\s*年',
    r'\d+(?:\.\d+)?[%％]',
    r'(?:亿|万|千)\s*(?:美元|元|人民币|欧元|日元)',
    # from inline_check.py: named platforms/sources
    r'App\s*Store|GitHub|微博|知乎|36氪|虎嗅|钛媒体',
]

# ============================================================
# Self-correction patterns
# ============================================================

SELF_CORRECTION_PATTERNS = [
    r'不对[，,]', r'准确说', r'算了', r'说错了',
    r'其实不是', r'我记混了', r'应该说', r'更准确地说',
    r'（[^）]{4,}）',  # Chinese parenthetical insertion (≥4 chars)
]

# ============================================================
# Broken sentence patterns
# ============================================================

# Used by humanness_score.py for scoring (subset — structural indicators)
BROKEN_SENTENCE_PATTERNS_SCORE = [
    r'——(?!.*[，。！？])',
    r'\.{3,}|…',
    r'不对[，,]',
    r'算了',
]

# Used by inline_check.py for detection (broader — includes conversational markers)
BROKEN_SENTENCE_PATTERNS_CHECK = [
    r'——[^，。！？\n]*[。！？\n]',
    r'——不对',
    r'——准确说',
    r'说白了',
    r'怎么说呢',
    r'好吧[，。]',
    r'行吧[，。]',
    r'\*\*[^*]+\*\*',
    r'[？?]\s*[？?]',
    r'[！!]\s*[！!]',
]


# ============================================================
# Pre-compiled regex patterns (performance optimization)
# ============================================================

def _compile_word_pattern(words: list[str]) -> re.Pattern:
    """Compile a list of literal words into a single alternation regex."""
    # Sort by length descending so longer matches take priority
    sorted_words = sorted(words, key=len, reverse=True)
    return re.compile("|".join(re.escape(w) for w in sorted_words))


def _compile_pattern_list(patterns: list[str]) -> list[re.Pattern]:
    """Compile a list of regex pattern strings."""
    return [re.compile(p) for p in patterns]


# Pre-compiled patterns for fast scanning
_BANNED_WORDS_RE = _compile_word_pattern(BANNED_WORDS)
_NEGATIVE_MARKERS_RE = _compile_word_pattern(NEGATIVE_MARKERS)
_COMMON_ADVERBS_RE = _compile_word_pattern(COMMON_ADVERBS)
_COLD_WORDS_RE = _compile_word_pattern(COLD_WORDS)
_WARM_WORDS_RE = _compile_word_pattern(WARM_WORDS)
_HOT_WORDS_RE = _compile_word_pattern(HOT_WORDS)
_WILD_WORDS_RE = _compile_word_pattern(WILD_WORDS)

_REAL_SOURCE_PATTERNS_COMPILED = _compile_pattern_list(REAL_SOURCE_PATTERNS)
_SELF_CORRECTION_PATTERNS_COMPILED = _compile_pattern_list(SELF_CORRECTION_PATTERNS)
_BROKEN_SCORE_COMPILED = _compile_pattern_list(BROKEN_SENTENCE_PATTERNS_SCORE)
_BROKEN_CHECK_COMPILED = _compile_pattern_list(BROKEN_SENTENCE_PATTERNS_CHECK)


def find_banned_words(text: str) -> list[str]:
    """Find all banned words in text. Returns list of matched words."""
    return _BANNED_WORDS_RE.findall(text)


def find_negative_markers(text: str) -> list[str]:
    """Find all negative emotion markers in text."""
    return _NEGATIVE_MARKERS_RE.findall(text)


def count_adverbs(text: str) -> int:
    """Count total adverb occurrences in text."""
    return len(_COMMON_ADVERBS_RE.findall(text))


def find_adverbs_starting_sentence(sentence: str, adverbs: list[str] = None) -> list[str]:
    """Find which adverbs appear at the start of a sentence."""
    if adverbs is None:
        adverbs = COMMON_ADVERBS
    return [adv for adv in adverbs if sentence.startswith(adv)]


def count_temperature_words(text: str) -> dict[str, int]:
    """Count words in each temperature band. Returns {'cold': N, 'warm': N, ...}."""
    return {
        "cold": len(_COLD_WORDS_RE.findall(text)),
        "warm": len(_WARM_WORDS_RE.findall(text)),
        "hot": len(_HOT_WORDS_RE.findall(text)),
        "wild": len(_WILD_WORDS_RE.findall(text)),
    }


def find_real_sources(text: str) -> list[str]:
    """Find all real source indicators in text."""
    results = []
    for pattern in _REAL_SOURCE_PATTERNS_COMPILED:
        results.extend(pattern.findall(text))
    return results


def find_real_sources_in_section(text: str) -> list[str]:
    """Find unique real source indicators (for per-H2 checking)."""
    return list(set(find_real_sources(text)))


def count_broken_sentences(text: str, mode: str = "score") -> int:
    """Count broken sentence patterns.

    Args:
        mode: "score" for humanness_score patterns, "check" for inline_check patterns.
    """
    compiled = _BROKEN_SCORE_COMPILED if mode == "score" else _BROKEN_CHECK_COMPILED
    total = 0
    for pattern in compiled:
        total += len(pattern.findall(text))
    return total


def count_self_corrections(text: str) -> int:
    """Count self-correction patterns in text."""
    total = 0
    for pattern in _SELF_CORRECTION_PATTERNS_COMPILED:
        total += len(pattern.findall(text))
    return total
