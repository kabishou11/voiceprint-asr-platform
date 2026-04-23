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


def _duration_seconds(audio_path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(audio_path))
    if not info.samplerate:
        return 0.0
    return float(info.frames) / float(info.samplerate)


def _split_reference_units(text: str) -> list[str]:
    units = [part for part in re.split(r"(?<=[。！？；!?;])", text) if part]
    if units:
        return units
    stripped = text.strip()
    return [stripped] if stripped else []


def slice_reference_text_by_ratio(
    text: str,
    *,
    audio_duration_seconds: float,
    max_seconds: float | None,
) -> str:
    payload = text or ""
    if not payload.strip():
        return payload
    if max_seconds is None or max_seconds <= 0 or audio_duration_seconds <= 0 or max_seconds >= audio_duration_seconds:
        return payload

    ratio = max(0.0, min(1.0, float(max_seconds) / float(audio_duration_seconds)))
    units = _split_reference_units(payload)
    if len(units) <= 1:
        slice_len = max(1, int(round(len(payload) * ratio)))
        return payload[:slice_len]

    total_chars = max(1, sum(len(unit) for unit in units))
    target_chars = max(1, int(round(total_chars * ratio)))
    collected: list[str] = []
    collected_chars = 0
    for unit in units:
        collected.append(unit)
        collected_chars += len(unit)
        if collected_chars >= target_chars:
            break
    return "".join(collected).strip()


def extract_hotwords(text: str, limit: int = 80, baseline_text: str | None = None) -> list[str]:
    normalized = normalize_reference_text(text)
    baseline_normalized = normalize_reference_text(baseline_text or "")

    direct_terms = _extract_direct_terms(normalized)
    delta_counter = _collect_delta_candidates(normalized, baseline_normalized)
    phrase_counter = _collect_candidate_scores(normalized)
    baseline_counter = _collect_candidate_scores(baseline_normalized) if baseline_normalized else Counter()

    ranked: list[tuple[str, int]] = []
    for term in set(direct_terms) | set(delta_counter) | set(phrase_counter):
        clean = _sanitize_term(term)
        if not clean or _is_bad_term(clean):
            continue

        reference_count = max(normalized.count(clean), phrase_counter.get(clean, 0))
        baseline_count = baseline_normalized.count(clean)
        delta_gain = max(0, reference_count - baseline_count)

        score = 0
        score += delta_counter.get(clean, 0)
        score += phrase_counter.get(clean, 0)
        score += _domain_bonus(clean)
        score += min(18, delta_gain * max(2, len(clean) // 2 + 1))
        if clean in direct_terms:
            score += 14
        if clean not in baseline_counter and _domain_bonus(clean) > 0:
            score += 8
        if reference_count >= 2:
            score += 5
        if baseline_count > 0 and delta_gain == 0:
            score -= 8
        if len(clean) <= 3 and clean not in direct_terms and _domain_bonus(clean) <= 0:
            score -= 8
        if _looks_like_phrase_noise(clean):
            score -= 20
        if score < 10:
            continue
        ranked.append((clean, score))

    ordered = sorted(ranked, key=lambda item: (-item[1], -len(item[0]), item[0]))
    hotwords: list[str] = []
    seen: set[str] = set()

    for term in direct_terms:
        clean = _sanitize_term(term)
        if not clean or clean in seen or _is_bad_term(clean) or _looks_like_phrase_noise(clean):
            continue
        hotwords.append(clean)
        seen.add(clean)
        if len(hotwords) >= limit:
            return hotwords

    for term, _ in ordered:
        if term in seen:
            continue
        if any(term != existing and (term in existing or existing in term) for existing in hotwords):
            continue
        hotwords.append(term)
        seen.add(term)
        if len(hotwords) >= limit:
            break
    return hotwords


def _extract_direct_terms(text: str) -> list[str]:
    preferred: list[str] = []
    seen: set[str] = set()
    for term in re.findall(r"(?:陈涛|陈燕|陈哥|陈月|郭莹|吕德峰|吕东生|朱总|联合银行|联社|太仓|无锡|江南)", text):
        clean = _sanitize_term(term)
        if clean and clean not in seen and not _is_bad_term(clean):
            preferred.append(clean)
            seen.add(clean)

    suffixes = ("平台", "系统", "资产", "分级", "分类", "治理", "银行", "联社", "仓库", "标准", "日志", "代码", "影像", "功能", "规则")
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for suffix in suffixes:
            start = 0
            while True:
                index = chunk.find(suffix, start)
                if index < 0:
                    break
                for prefix_len in range(2, min(4, index) + 1):
                    prefix = _sanitize_term(chunk[index - prefix_len:index])
                    if len(prefix) < 2:
                        continue
                    if not prefix or _looks_like_bad_compound_prefix(prefix):
                        continue
                    clean = _sanitize_term(f"{prefix}{suffix}")
                    if clean and clean not in seen and not _is_bad_term(clean):
                        preferred.append(clean)
                        seen.add(clean)
                start = index + len(suffix)

    for term in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,31}", text):
        clean = _sanitize_term(term)
        if clean and clean not in seen and not _is_bad_term(clean):
            preferred.append(clean)
            seen.add(clean)
    return preferred


def _collect_delta_candidates(reference_text: str, baseline_text: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not reference_text or not baseline_text:
        return counter

    reference_sentences = _split_units(reference_text)
    baseline_sentences = _split_units(baseline_text)
    baseline_joined = "".join(baseline_sentences)

    for sentence in reference_sentences:
        if not sentence:
            continue
        sentence_ratio = 0.0
        if baseline_sentences:
            sentence_ratio = max(_simple_ratio(sentence, candidate) for candidate in baseline_sentences)
        if sentence_ratio >= 0.95:
            continue
        for term in _extract_sentence_terms(sentence):
            if term in baseline_joined:
                continue
            if _is_bad_term(term):
                continue
            counter[term] += 14 + min(12, len(term))

    return counter


def _split_units(text: str) -> list[str]:
    units = [part.strip() for part in re.split(r"(?<=[。！？；!?;])", text) if part.strip()]
    if units:
        return units
    return [text.strip()] if text.strip() else []


def _extract_sentence_terms(text: str) -> list[str]:
    return _extract_direct_terms(text)


def _collect_candidate_scores(text: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not text:
        return counter

    for term in _extract_direct_terms(text):
        counter[term] += 18

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,31}", text):
        counter[token] += 6
    return counter


def _sanitize_term(term: str) -> str:
    cleaned = (term or "").strip()
    cleaned = re.sub(r"^[和及与对把在将给向从按于就再都也先还仅仅]+", "", cleaned)
    cleaned = re.sub(r"[的地得吧呢啊嗯呃嘛]+$", "", cleaned)
    return cleaned


def _looks_like_bad_compound_prefix(prefix: str) -> bool:
    if not prefix:
        return True
    if re.search(r"[的是有了在就和把跟这那但而且那么该也个种]", prefix):
        return True
    if re.search(r"(类似|现在|一个|问题|场景|逻辑|时候|觉得|可以|统一)", prefix):
        return True
    if re.search(r"(平台|系统|资产|分级|分类|治理|银行|联社|仓库|标准|日志|代码|影像|功能|规则)$", prefix):
        allowed = {"分类", "数据", "代码", "影像", "营销", "文档云", "联合"}
        return prefix not in allowed
    return False


def _looks_like_phrase_noise(term: str) -> bool:
    if re.search(r"(.)(?:\1)[\u4e00-\u9fff]{1,6}", term):
        return True
    if re.search(r"(我们|你们|他们|可以|觉得|问题|这个|那个|一下|现在|其实|然后|就是|会有|不会|应该|如果)", term):
        return True
    if re.search(r"(去做|去跑|去看|去把|要去|可以去|先去|现在在|我觉得|我其实|通过它的|平台里面)", term):
        return True
    if re.search(r"(同样按照|局限在|因为本身|据出来做|定不会比|说像现在|直之前跟)", term):
        return True
    if re.search(r"(代码代码|数数据|文文档)", term):
        return True
    if len(term) > 8 and _domain_bonus(term) <= 0:
        return True
    return False


def _is_bad_term(term: str) -> bool:
    if not term or len(term) < 2:
        return True
    if len(set(term)) == 1:
        return True
    if re.search(r"([\u4e00-\u9fffA-Za-z0-9])\1", term):
        return True
    if re.fullmatch(r"[\W_]+", term):
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
        "不是",
        "因为",
        "自己",
        "时候",
        "要求",
        "这样",
        "比如说",
        "第二个",
        "第一个",
        "或者说",
        "基本上",
        "能不能",
        "怎么样",
        "相当于",
        "可以先",
        "分类分析",
        "页面应用功能",
        "应用功能上",
    }
    if term in stop_terms:
        return True
    if re.search(r"(那个|这个|什么|是不是|就是|然后|觉得|其实|一下|我们|你们|他们)", term):
        return True
    if re.search(r"(应用功能上|平台问题的|大概两三周前|这个场景下|有一条路是可以)", term):
        return True
    if re.search(r"^(这些|那些|整个|前不|今天把|一直在|是通过|要去|前不是|面的|多的)", term):
        return True
    if re.search(r"(通过他的平台|这些数据资产|这些数字资产|据出来做分类|前不是在联社|言回来的分类|今天把联社)", term):
        return True
    if term[0] in set("的一了是在就和跟把去要有没不这那但而且那么跟该呢啊呃嗯"):
        return True
    stop_chars = set("的一了是在就和跟把去要有没不这那啊吧呢嘛呃嗯")
    if len(term) <= 4 and (term[0] in stop_chars or term[-1] in stop_chars):
        return True
    return False


def _domain_bonus(term: str) -> int:
    if re.search(r"(银行|联社|平台|系统|资产|分级|分类|治理|标准|加密|日志|仓库|影像|代码|OCR|数据|规则|功能)", term):
        return 8
    if re.search(r"(陈涛|陈燕|陈哥|陈月|郭莹|吕德峰|吕东生|朱总|太仓|无锡|江南)", term):
        return 12
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{1,31}", term):
        return 4
    return 0


def _simple_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_chars = Counter(left)
    right_chars = Counter(right)
    overlap = sum((left_chars & right_chars).values())
    return (2.0 * overlap) / float(len(left) + len(right))


def main() -> None:
    parser = argparse.ArgumentParser(description="从参考转写稿中抽取热词候选。")
    parser.add_argument("input", help="参考文本路径")
    parser.add_argument("output", help="输出 JSON/TXT 路径")
    parser.add_argument("--limit", type=int, default=80, help="最多输出热词数")
    parser.add_argument("--baseline-text", default=None, help="当前 ASR 文本路径，用于差异驱动提词")
    parser.add_argument("--audio", default=None, help="对应音频路径，用于按时间窗裁参考稿")
    parser.add_argument("--max-seconds", type=float, default=None, help="只对参考稿前 N 秒窗口提词")
    args = parser.parse_args()

    payload = Path(args.input).read_text(encoding="utf-8")
    if args.audio and args.max_seconds and args.max_seconds > 0:
        payload = slice_reference_text_by_ratio(
            payload,
            audio_duration_seconds=_duration_seconds(Path(args.audio)),
            max_seconds=args.max_seconds,
        )
    baseline_text = Path(args.baseline_text).read_text(encoding="utf-8") if args.baseline_text else None
    hotwords = extract_hotwords(payload, limit=args.limit, baseline_text=baseline_text)
    output = Path(args.output)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps({"hotwords": hotwords}, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output.write_text("\n".join(hotwords) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
