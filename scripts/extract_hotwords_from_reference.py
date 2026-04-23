from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def normalize_reference_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"file:\s*.*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*+result\*+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def extract_hotwords(text: str, limit: int = 80, baseline_text: str | None = None) -> list[str]:
    normalized = normalize_reference_text(text)
    baseline_normalized = normalize_reference_text(baseline_text or "")
    counter = _collect_candidate_scores(normalized)
    baseline_counter = _collect_candidate_scores(baseline_normalized) if baseline_normalized else Counter()
    preferred_terms = _extract_preferred_terms(normalized)

    ranked_candidates: list[tuple[str, int]] = []
    for term, score in counter.items():
        if _is_bad_term(term):
            continue
        adjusted = score
        if baseline_counter:
            if term in baseline_counter:
                adjusted += 2
            else:
                adjusted += 10 + min(20, len(term) * 2)
            if len(term) <= 4 and term not in baseline_counter:
                continue
            adjusted += _delta_bonus(term, normalized, baseline_normalized)
        domain_bonus = _domain_bonus(term)
        adjusted += domain_bonus
        if baseline_counter and term not in baseline_counter and domain_bonus > 0 and len(term) <= 4:
            adjusted += 20
        if adjusted < 6:
            continue
        ranked_candidates.append((term, adjusted))

    ranked = sorted(
        ranked_candidates,
        key=lambda item: (-item[1], len(item[0]), item[0]),
    )
    hotwords: list[str] = []
    seen: set[str] = set()
    for term in preferred_terms:
        if term in seen or _is_bad_term(term):
            continue
        hotwords.append(term)
        seen.add(term)
        if len(hotwords) >= limit:
            return hotwords
    for term, _ in ranked:
        if term in seen:
            continue
        if any(term != existing and (term in existing or existing in term) for existing in hotwords):
            continue
        hotwords.append(term)
        seen.add(term)
        if len(hotwords) >= limit:
            break
    return hotwords


def _is_bad_term(term: str) -> bool:
    if re.match(r"^[和及与对把在将给向从按于就]", term):
        return True
    if re.search(r"(已经提过|统一治理|一直在用|现在目前|要去|可以去|觉得现在)", term):
        return True
    if re.search(r"(和代码|和平台|和数据|要对|会有|一直在|今天把)", term):
        return True
    if len(term) > 6 and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]+", term):
        return True
    if len(term) < 3 and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]+", term):
        if _domain_bonus(term) <= 0:
            return True
    if len(term) < 2:
        return True
    if len(set(term)) == 1:
        return True
    stop_terms = {
        "我们",
        "这个",
        "那个",
        "就是",
        "可以",
        "然后",
        "一下",
        "没有",
        "他们",
        "现在",
        "问题",
        "东西",
        "一个",
        "一些",
        "目前",
        "可以",
        "就是",
        "不是",
        "因为",
        "平台",
        "系统",
        "规则",
        "问题",
        "数据",
        "自己",
        "时候",
        "要求",
        "工具",
        "标准",
        "后面",
        "事情",
        "这样",
        "检查",
        "我觉得",
        "比如说",
        "第二个",
        "第一个",
        "或者说",
        "现在目前",
        "基本上",
        "能不能",
        "怎么样",
        "相当于",
        "可以先",
    }
    if term in stop_terms:
        return True
    stop_chars = set("的一了是在就和跟把去要有没不这那啊吧呢嘛呃嗯")
    if len(term) <= 4 and (term[0] in stop_chars or term[-1] in stop_chars):
        return True
    weak_chars = set("我你他她它们个这那的是了吧呢嘛啊嗯")
    if len(term) <= 6 and any(char in weak_chars for char in term):
        return True
    if re.search(r"(那个|这个|什么|是不是|就是|然后)", term):
        return True
    if re.search(r"(一个|这个|那个|我们|你们|他们|时候|里面|怎么|如果|或者|其实|自己|目前|还是|不能|应该)", term):
        return True
    return False


def _collect_candidate_scores(text: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not text:
        return counter

    for prefix, suffix in re.findall(
        r"([\u4e00-\u9fff]{1,4})(平台|系统|资产|分级|分类|治理|银行|联社|仓库|标准|日志|代码|数据)",
        text,
    ):
        term = _sanitize_term(f"{prefix}{suffix}")
        if term:
            counter[term] += 12
    for term in re.findall(r"(?:陈涛|陈燕|陈哥|李荣兄|郭莹|吕德生|朱总|联合银行|联社)", text):
        counter[term] += 18

    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,31}", text):
        counter[token] += 8

    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    for chunk in cjk_chunks:
        max_size = min(6, len(chunk))
        for size in range(2, max_size + 1):
            for index in range(0, len(chunk) - size + 1):
                term = chunk[index:index + size]
                counter[term] += 1 + max(0, size - 3)
    return counter


def _extract_preferred_terms(text: str) -> list[str]:
    preferred: list[str] = []
    seen: set[str] = set()
    patterns = [
        r"(?:陈涛|陈燕|陈哥|李荣兄|郭莹|吕德生|朱总|联合银行|联社)",
        r"([\u4e00-\u9fff]{1,4})(平台|系统|资产|分级|分类|治理|银行|联社|仓库|标准|日志|代码|数据)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            term = _sanitize_term("".join(match) if isinstance(match, tuple) else match)
            if not term:
                continue
            if term in seen:
                continue
            preferred.append(term)
            seen.add(term)
    return preferred


def _sanitize_term(term: str) -> str:
    cleaned = (term or "").strip()
    cleaned = re.sub(r"^[和及与对把在将给向从按于就把将]+", "", cleaned)
    cleaned = re.sub(r"[的地得]+$", "", cleaned)
    return cleaned


def _delta_bonus(term: str, reference_text: str, baseline_text: str) -> int:
    if not baseline_text:
        return 0
    ref_count = reference_text.count(term)
    base_count = baseline_text.count(term)
    if ref_count <= base_count:
        return 0
    return min(18, (ref_count - base_count) * max(2, len(term) // 2 + 1))


def _domain_bonus(term: str) -> int:
    if re.search(r"(银行|联社|平台|系统|资产|分级|分类|治理|标准|加密|日志|仓库|影像|代码|OCR|数据)", term):
        return 6
    if re.search(r"(陈涛|陈燕|陈哥|李荣兄|郭莹|吕德生|朱总)", term):
        return 10
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{1,31}", term):
        return 4
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="从参考转写稿中抽取热词候选。")
    parser.add_argument("input", help="参考文本路径")
    parser.add_argument("output", help="输出 JSON/TXT 路径")
    parser.add_argument("--limit", type=int, default=80, help="最多输出热词数")
    parser.add_argument("--baseline-text", default=None, help="当前 ASR 文本路径，用于交集筛选热词")
    args = parser.parse_args()

    payload = Path(args.input).read_text(encoding="utf-8")
    baseline_text = Path(args.baseline_text).read_text(encoding="utf-8") if args.baseline_text else None
    hotwords = extract_hotwords(payload, limit=args.limit, baseline_text=baseline_text)
    output = Path(args.output)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps({"hotwords": hotwords}, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output.write_text("\n".join(hotwords) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
