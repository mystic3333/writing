#!/usr/bin/env python3
"""
Inline quality check for WeWrite drafts — runs between Step 4.5 and Step 5.

Checks the 5 realtime-check.md items (sentence variance, emotional anchoring,
vocabulary temperature, source anchoring, syntactic deformation) plus
banned-word scan, adverb density, and opening hook quality.

Unlike humanness_score.py (which runs later for full scoring), this script is
meant to catch issues *immediately after writing*, when the agent can still
do a lightweight fix without re-entering the full SEO/validation pipeline.

Usage:
    python3 inline_check.py output/article.md
    python3 inline_check.py output/article.md --verbose
    python3 inline_check.py output/article.md --json
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────

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

NEGATIVE_MARKERS = [
    "失望", "糟糕", "扯", "坑", "烂", "差劲", "崩溃", "吐槽", "骂",
    "怒", "烦", "焦虑", "担忧", "不满", "恶心", "可怕", "可悲", "可笑",
    "离谱", "尴尬", "无语", "蠢", "惨", "亏", "危",
    "绝望", "迷茫", "心累", "丧", "后悔", "后怕", "心寒",
    "骗", "忽悠", "割韭菜", "套路", "画大饼", "洗脑",
    "白费", "白搭", "没戏", "黄了", "凉了", "废了",
    "傻", "天真", "吃亏", "自嗨", "打脸",
    "呵呵", "好吧", "行吧", "真服了",
    "太扯了", "说实话我很失望", "搞什么", "不靠谱", "受不了",
    "受够了", "想哭", "伤心", "苦哈哈", "得过且过",
]

COMMON_ADVERBS = [
    "非常", "十分", "极其", "特别", "相当", "尤其", "格外",
    "更加", "越来越", "逐渐", "不断", "始终", "一直",
    "已经", "正在", "将要", "可能", "大概", "或许",
    "似乎", "显然", "明显", "确实", "果然", "居然",
    "竟然", "简直", "几乎", "完全", "绝对", "必然",
]

COLD_WORDS = [
    "边际", "认知负荷", "信息不对称", "路径依赖", "商业模式", "生态系统",
    "技术栈", "标准化", "结构性", "规模化", "护城河", "飞轮", "闭环",
    "赛道", "壁垒", "方法论", "底层逻辑", "第一性原理", "杠杆", "复利",
    "ROI", "PMF", "供给侧", "需求侧",
]
WARM_WORDS = [
    "说白了", "其实吧", "讲真", "说实话", "坦白讲", "懂的都懂", "怎么说呢",
    "老实说", "这么说吧", "你想啊", "别急", "慢慢来",
    "有意思的是", "好玩的是", "巧的是", "说来话长", "话说回来",
]
HOT_WORDS = [
    "DNA动了", "格局打开", "遥遥领先", "卷", "内卷", "炸了", "杀疯了",
    "凡尔赛", "标题党", "躺平", "摆烂", "破防", "上头", "内耗",
    "蒸发", "出圈", "降维打击", "弯道超车",
]
WILD_WORDS = [
    "整挺好", "不靠谱", "瞎折腾", "搁这儿", "糊弄", "整", "贼",
    "特", "巨", "超", "老", "超纲", "无语子", "绝了",
]

REAL_SOURCE_PATTERNS = [
    r'[A-Z][a-z]+\s+[A-Z][a-z]+',
    r'(?:据|根据|来自)\s*[\u4e00-\u9fff]+(?:报告|数据|研究|调查|分析)',
    r'20[12]\d\s*年',
    r'\d+(?:\.\d+)?[%％]',
    r'(?:亿|万|千)\s*(?:美元|元|人民币|欧元|日元)',
    r'[\u4e00-\u9fff]{2,4}(?:表示|指出|认为|写道|提到|说过|评论)',
    r'App\s*Store|GitHub|微博|知乎|36氪|虎嗅|钛媒体',
]

BROKEN_SENTENCE_PATTERNS = [
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


def strip_markdown(text):
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\*{1,3}', '', text)
    text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)
    text = re.sub(r'>\s+', '', text)
    text = re.sub(r'\|', '', text)
    text = re.sub(r':{3,}\w*', '', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


def get_h2_sections(text):
    lines = text.split('\n')
    sections = []
    current_h2 = "(before first H2)"
    current_lines = []
    for line in lines:
        if line.startswith('## '):
            if current_lines:
                sections.append((current_h2, '\n'.join(current_lines).strip()))
            current_h2 = line.lstrip('# ').strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_h2, '\n'.join(current_lines).strip()))
    return sections


def get_sliding_windows(text, window_size=500, step=250):
    windows = []
    start = 0
    while start < len(text):
        end = min(start + window_size, len(text))
        if end - start < 100:
            break
        windows.append((start, end, text[start:end]))
        start += step
    return windows


def count_chinese_chars(text):
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def split_sentences(text):
    text = re.sub(r'\n+', '。', text)
    raw = re.split(r'([。！？\n!?])', text)
    sentences = []
    buffer = ''
    for part in raw:
        if re.match(r'^[。！？\n!?]$', part):
            if buffer.strip():
                sentences.append(buffer.strip() + part)
                buffer = ''
        else:
            buffer = part
    if buffer.strip():
        sentences.append(buffer.strip())
    return [s for s in sentences if count_chinese_chars(s) >= 2]


def check_sentence_variance(text, window_text, verbose=False):
    sentences = split_sentences(window_text)
    if len(sentences) < 4:
        return {"pass": True, "detail": "too few sentences to check", "issues": []}

    lengths = [count_chinese_chars(s) for s in sentences]
    issues = []
    for i in range(len(sentences) - 2):
        trio = lengths[i:i+3]
        if abs(trio[0] - trio[1]) <= 5 and abs(trio[1] - trio[2]) <= 5:
            issues.append({
                "start_idx": i,
                "texts": sentences[i:i+3],
                "lengths": trio,
                "note": "3 consecutive sentences within ±5 chars"
            })

    has_short = any(l <= 5 for l in lengths)
    has_long = any(l >= 25 for l in lengths)
    max_l = max(lengths) if lengths else 0
    min_l = min(lengths) if lengths else 0

    return {
        "pass": len(issues) == 0 and (max_l - min_l) >= 15,
        "sentence_count": len(sentences),
        "max_length": max_l,
        "min_length": min_l,
        "range": max_l - min_l,
        "issues": issues,
        "has_short_and_long": has_short and has_long,
    }


def check_emotion(text, window_text, verbose=False):
    found = [m for m in NEGATIVE_MARKERS if m in window_text]
    count = len(found)
    char_count = count_chinese_chars(window_text)
    return {
        "pass": count >= 2,
        "negative_count": count,
        "char_count": char_count,
        "rate_per_500": round(count / max(char_count, 1) * 500, 1),
        "markers_found": found[:10],
    }


def check_temperature(text, window_text, verbose=False):
    cold = sum(1 for w in COLD_WORDS if w in window_text)
    warm = sum(1 for w in WARM_WORDS if w in window_text)
    hot = sum(1 for w in HOT_WORDS if w in window_text)
    wild = sum(1 for w in WILD_WORDS if w in window_text)
    present = []
    if cold > 0: present.append("cold")
    if warm > 0: present.append("warm")
    if hot > 0: present.append("hot")
    if wild > 0: present.append("wild")
    return {
        "pass": len(present) >= 2,
        "types_found": present,
        "counts": {"cold": cold, "warm": warm, "hot": hot, "wild": wild},
        "target_at_least": 2,
    }


def check_sources(text, h2_sections, verbose=False):
    total_h2 = len(h2_sections)
    h2_with_sources = 0
    h2_details = []
    for h2_name, h2_text in h2_sections:
        matches = []
        for pat in REAL_SOURCE_PATTERNS:
            found = re.findall(pat, h2_text)
            matches.extend(found)
        unique_matches = list(set(matches))
        has_source = len(unique_matches) >= 1
        if has_source:
            h2_with_sources += 1
        h2_details.append({
            "h2": h2_name[:40],
            "pass": has_source,
            "source_count": len(unique_matches),
            "samples": unique_matches[:3],
        })
    return {
        "pass": total_h2 == 0 or h2_with_sources >= total_h2,
        "total_h2": total_h2,
        "h2_with_sources": h2_with_sources,
        "h2_details": h2_details,
    }


def check_syntax(text, window_text, verbose=False):
    total = 0
    patterns_found = {}
    for pat in BROKEN_SENTENCE_PATTERNS:
        matches = re.findall(pat, window_text)
        if matches:
            patterns_found[pat] = len(matches)
            total += len(matches)
    return {
        "pass": total >= 1,
        "total_hits": total,
        "patterns": {k: v for k, v in patterns_found.items()},
    }


def check_banned_words(text, verbose=False):
    found = []
    for w in BANNED_WORDS:
        positions = [m.start() for m in re.finditer(re.escape(w), text)]
        if positions:
            context_start = max(0, positions[0] - 15)
            context_end = min(len(text), positions[0] + len(w) + 15)
            snippet = text[context_start:context_end].replace('\n', ' ')
            found.append({"word": w, "count": len(positions), "snippet": snippet})
    return {
        "pass": len(found) == 0,
        "total": sum(f["count"] for f in found),
        "items": found,
    }


def check_adverb_density(text, verbose=False):
    lines = text.split('\n')
    content_lines = [l for l in lines if count_chinese_chars(l) > 10]
    char_count = count_chinese_chars(text)
    adverb_count = 0
    consecutive_adverb_starts = 0
    adverb_start_issues = 0
    for i, line in enumerate(content_lines):
        found_adverbs = [a for a in COMMON_ADVERBS if a in line]
        adverb_count += len(found_adverbs)
        if found_adverbs and line.startswith(tuple(found_adverbs)):
            consecutive_adverb_starts += 1
            if consecutive_adverb_starts >= 2:
                adverb_start_issues += 1
        else:
            consecutive_adverb_starts = 0
    per_100 = adverb_count / max(char_count, 1) * 100
    return {
        "pass": per_100 <= 3 and adverb_start_issues == 0,
        "adverb_count": adverb_count,
        "char_count": char_count,
        "per_100_chars": round(per_100, 2),
        "max_recommended": 3,
        "consecutive_adverb_start_issues": adverb_start_issues,
    }


def check_opening(text, first_500=None, verbose=False):
    if first_500 is None:
        first_500 = text[:500]
    has_question = '?' in first_500 or '？' in first_500
    has_quote = '"' in first_500 or '"' in first_500 or '「' in first_500
    has_exclamation = '!' in first_500 or '！' in first_500
    has_scene = any(
        p in first_500[:100] for p in [
            "昨天", "今天", "前天", "刚才", "晚上", "早上", "下午",
            "我", "我们", "一个朋友", "有个",
        ]
    )
    hook_score = sum([has_question, has_quote, has_exclamation, has_scene])
    return {
        "pass": hook_score >= 1,
        "hook_score": hook_score,
        "has_question": has_question,
        "has_quote": has_quote,
        "has_exclamation": has_exclamation,
        "has_scene_or_personal": has_scene,
        "suggestion": (
            "开头的钩子力度不足" if hook_score < 1
            else "开头有钩子元素" if hook_score < 3
            else "开头钩子充分"
        ),
    }


def check(text, verbose=False):
    clean = strip_markdown(text)
    h2_sections = get_h2_sections(text)
    windows = get_sliding_windows(clean)
    first_500 = clean[:500] if len(clean) >= 500 else clean

    window_results = []
    for start, end, window_text in windows:
        window_results.append({
            "offset": f"{start}-{end}",
            "char_count": count_chinese_chars(window_text),
            "sentence_variance": check_sentence_variance(text, window_text, verbose),
            "emotion": check_emotion(text, window_text, verbose),
            "temperature": check_temperature(text, window_text, verbose),
            "syntax": check_syntax(text, window_text, verbose),
        })

    source_check = check_sources(text, h2_sections, verbose)
    banned_check = check_banned_words(text, verbose)
    adverb_check = check_adverb_density(text, verbose)
    opening_check = check_opening(text, first_500, verbose)

    all_window_pass = all(
        w["sentence_variance"]["pass"]
        and w["emotion"]["pass"]
        and w["temperature"]["pass"]
        and w["syntax"]["pass"]
        for w in window_results
    )

    overall_pass = (
        all_window_pass
        and source_check["pass"]
        and banned_check["pass"]
        and adverb_check["pass"]
        and opening_check["pass"]
    )

    findings = []
    fix_suggestions = []
    for w in window_results:
        offset = w["offset"]
        if not w["sentence_variance"]["pass"]:
            issues = w["sentence_variance"].get("issues", [])
            n_issues = len(issues)
            findings.append(f"[{offset}] 句长交替: {n_issues} 处连续3句长度接近")
            fix_suggestions.append(
                f"窗口 {offset}: 将连续接近的句子拆短或插入极短句（3-5字）"
            )
        if not w["emotion"]["pass"]:
            findings.append(f"[{offset}] 情绪锚定: 仅 {w['emotion']['negative_count']} 处负面表达（目标≥2）")
            fix_suggestions.append(
                f"窗口 {offset}: 在观点判断处加入带刺的负面表达"
            )
        if not w["temperature"]["pass"]:
            found = w["temperature"]["types_found"]
            findings.append(f"[{offset}] 词汇温度: 仅 {len(found)} 种温度 ({found})，目标≥2")
            fix_suggestions.append(
                f"窗口 {offset}: 将1-2个书面语替换为口语/网络/野性词汇"
            )
        if not w["syntax"]["pass"]:
            findings.append(f"[{offset}] 句法变形: 未检测到破句/自纠/反问")
            fix_suggestions.append(
                f"窗口 {offset}: 加入至少1处破句、自我纠正或反问连击"
            )

    if not source_check["pass"]:
        missing = [d for d in source_check["h2_details"] if not d["pass"]]
        for m in missing:
            findings.append(f"H2「{m['h2']}」: 缺少具名来源或具体数据")
            fix_suggestions.append(
                f"段落「{m['h2']}」: 补充一个具名来源+具体数据/引述"
            )

    if not banned_check["pass"]:
        for item in banned_check["items"]:
            findings.append(f"禁用词: 「{item['word']}」出现 {item['count']} 次")
            fix_suggestions.append(
                f"禁用词「{item['word']}」: 替换为具体表达或删除"
            )

    if not adverb_check["pass"]:
        findings.append(
            f"副词密度: {adverb_check['per_100_chars']}/100字（目标≤3）"
            + (f"，连续副词开头 {adverb_check['consecutive_adverb_start_issues']} 处" if adverb_check['consecutive_adverb_start_issues'] else "")
        )
        fix_suggestions.append("减少副词，用具体描述替代（如「非常快速地增长」→「三个月翻了一番」）")

    if not opening_check["pass"]:
        findings.append("开头钩子不足：前500字缺少悬念/冲突/好奇心触发器")
        fix_suggestions.append("重写开头前3句：用一个场景、反问、数据冲击或冲突引入")

    result = {
        "file": str(Path(text).name) if text else "",
        "overall_pass": overall_pass,
        "window_count": len(windows),
        "h2_count": len(h2_sections),
        "total_chars": count_chinese_chars(clean),
        "window_results": window_results,
        "source_check": source_check,
        "banned_words": banned_check,
        "adverb_density": adverb_check,
        "opening_hook": opening_check,
        "findings": findings,
        "fix_suggestions": fix_suggestions,
        "finding_count": len(findings),
    }
    return result


def print_verbose(result):
    status = "PASS ✓" if result["overall_pass"] else "ISSUES FOUND ✗"
    print(f"\n{'='*60}")
    print(f"  Inline Check Report — {result['file']}")
    print(f"  Overall: {status}")
    print(f"  Chinese chars: {result['total_chars']}")
    print(f"  H2 sections: {result['h2_count']}")
    print(f"  Windows checked: {result['window_count']}")
    print(f"{'='*60}")

    if result["findings"]:
        print(f"\n  🔴 {result['finding_count']} Findings:")
        for f in result["findings"]:
            print(f"    • {f}")
        print(f"\n  🛠  Fix suggestions:")
        for s in result["fix_suggestions"]:
            print(f"    → {s}")
    else:
        print(f"\n  ✅ No issues found.")

    print()

    for i, w in enumerate(result["window_results"]):
        print(f"  ── Window {i+1} ({w['offset']}, {w['char_count']} chars) ──")
        sv = w["sentence_variance"]
        em = w["emotion"]
        tp = w["temperature"]
        sx = w["syntax"]
        print(f"    句长: {'✓' if sv['pass'] else '✗'} (range {sv.get('range', '?')}字, sentences {sv.get('sentence_count', '?')})")
        if not sv["pass"] and sv.get("issues"):
            for iss in sv["issues"]:
                for t in iss.get("texts", [])[:3]:
                    print(f"      「{t[:40]}...」" if len(t) > 40 else f"      「{t}」")
        print(f"    情绪: {'✓' if em['pass'] else '✗'} ({em['negative_count']} neg marks)")
        print(f"    温度: {'✓' if tp['pass'] else '✗'} ({tp['types_found']})")
        print(f"    句法: {'✓' if sx['pass'] else '✗'} ({sx['total_hits']} hits)")
        print()

    src = result["source_check"]
    print(f"  ── Source Anchoring ──")
    print(f"    {'✓' if src['pass'] else '✗'} {src['h2_with_sources']}/{src['total_h2']} H2s with sources")
    for d in src.get("h2_details", []):
        print(f"    {'✓' if d['pass'] else '✗'} {d['h2']}: {d['source_count']} sources")

    bw = result["banned_words"]
    ad = result["adverb_density"]
    oh = result["opening_hook"]
    print(f"\n  ── Global Checks ──")
    print(f"    禁用词: {'✓' if bw['pass'] else '✗'} ({bw['total']} hits)")
    print(f"    副词密度: {'✓' if ad['pass'] else '✗'} ({ad['per_100_chars']}/100字)")
    print(f"    开头钩子: {'✓' if oh['pass'] else '✗'} (score {oh['hook_score']}/4)")
    print()


def main():
    parser = argparse.ArgumentParser(description="WeWrite inline quality check")
    parser.add_argument("file", help="Path to article markdown file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed report")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    result = check(text, verbose=args.verbose)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.verbose:
        print_verbose(result)
    else:
        print("PASS" if result["overall_pass"] else f"FAIL ({result['finding_count']} issues)")
        for f in result["findings"]:
            print(f"  • {f}")

    sys.exit(0 if result["overall_pass"] else 1)


if __name__ == "__main__":
    main()
