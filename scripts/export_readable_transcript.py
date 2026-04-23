from __future__ import annotations

import argparse
from pathlib import Path

from domain.schemas.transcript import Segment
from domain.schemas.transcript import TranscriptResult


def format_ms(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    millis = max(0, ms % 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def render_readable_transcript(
    result: TranscriptResult,
    title: str | None = None,
    include_full_text: bool = False,
) -> str:
    display_segments = prepare_display_segments(result.segments)
    lines: list[str] = []
    if title:
        lines.append(f"文件: {title}")
    lines.append(f"语言: {result.language or 'unknown'}")
    lines.append(f"全文长度: {len(result.text)} 字")
    lines.append(f"分段数: {len(display_segments)}")
    total_duration_ms = max((segment.end_ms for segment in display_segments), default=0)
    lines.append(f"总时长: {format_ms(total_duration_ms)}")
    lines.append("")
    lines.append("=== Speaker 汇总 ===")
    summaries = build_speaker_summaries(display_segments)
    if not summaries:
        lines.append("（无 speaker 分段）")
    for speaker, segment_count, duration_ms in summaries:
        lines.append(f"- {speaker}: {segment_count} 段 | {format_ms(duration_ms)}")
    lines.append("")
    lines.append("=== 分段 ===")
    for index, segment in enumerate(display_segments, start=1):
        speaker = segment.speaker or "SPEAKER_00"
        confidence = f" | conf={segment.confidence:.2f}" if segment.confidence is not None else ""
        lines.append(
            f"{index:04d}. [{format_ms(segment.start_ms)} - {format_ms(segment.end_ms)} | {format_ms(segment.end_ms - segment.start_ms)}] {speaker}{confidence}"
        )
        lines.append(_clean_export_text(segment.text) or "（无文本）")
    if include_full_text:
        lines.append("")
        lines.append("=== 全文 ===")
        lines.append(_clean_export_text(result.text) or "（无文本）")
    return "\n".join(lines).strip() + "\n"


def build_speaker_summaries(segments: list[Segment]) -> list[tuple[str, int, int]]:
    summary: dict[str, tuple[int, int]] = {}
    for segment in segments:
        speaker = segment.speaker or "SPEAKER_00"
        count, duration = summary.get(speaker, (0, 0))
        summary[speaker] = (count + 1, duration + max(0, segment.end_ms - segment.start_ms))
    return sorted(
        [(speaker, count, duration) for speaker, (count, duration) in summary.items()],
        key=lambda item: (-item[2], item[0]),
    )


def prepare_display_segments(segments: list[Segment]) -> list[Segment]:
    prepared = [
        segment.model_copy(
            update={
                "text": _clean_export_text(segment.text),
            }
        )
        for segment in segments
    ]
    prepared = _merge_display_segments(prepared)
    return [segment for segment in prepared if not _should_hide_segment(segment)]


def _clean_export_text(text: str | None) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("文文档", "文档")
    cleaned = cleaned.replace("图像类那些东西，那些东西", "图像类那些东西")
    cleaned = cleaned.replace("代码代码", "代码")
    cleaned = cleaned.replace("日志日志", "日志")
    cleaned = cleaned.replace("分类分类", "分类")
    cleaned = cleaned.replace("平台功能基本。周前", "平台功能基本，周前")
    cleaned = cleaned.replace("做到的对吧？做到的对吧？", "做到的对吧？")
    cleaned = cleaned.replace("存在的两个比较大的问题。存在的两个比较大的问题啊。", "存在的两个比较大的问题啊。")
    cleaned = cleaned.replace("可以去可 以去", "可以去")
    cleaned = cleaned.replace("它它", "它")
    cleaned = cleaned.replace("我我我", "我")
    cleaned = cleaned.replace("有有有", "有")
    cleaned = cleaned.replace("去去去去", "去")
    cleaned = cleaned.replace("对对对对", "对")
    cleaned = cleaned.replace("一个一个一个一个", "一个")
    cleaned = cleaned.replace("可以先先先", "可以先")
    cleaned = cleaned.replace("那个那个", "那个")
    cleaned = cleaned.replace("前前", "前")
    cleaned = cleaned.replace("主主", "主")
    cleaned = cleaned.replace("分分", "分")
    cleaned = cleaned.replace("有有 什么", "有什么")
    cleaned = cleaned.replace("台啊 ，", "台啊，")
    cleaned = cleaned.replace("嘛 ，", "嘛，")
    cleaned = cleaned.replace("？ ", "？")
    cleaned = cleaned.replace("。 ", "。")
    cleaned = cleaned.replace("， ", "，")
    cleaned = cleaned.replace("  ", " ")
    cleaned = cleaned.replace("可 以", "可以")
    cleaned = cleaned.replace("这这种", "这种")
    cleaned = cleaned.replace("影像 台", "影像台")
    cleaned = cleaned.replace("或 者", "或者")
    cleaned = cleaned.replace("存 在", "存在")
    cleaned = cleaned.replace("分 类分 级", "分类分级")
    cleaned = cleaned.replace("数 据", "数据")
    cleaned = cleaned.replace("现 在", "现在")
    cleaned = cleaned.replace("前 面", "前面")
    cleaned = cleaned.replace("比 如", "比如")
    cleaned = cleaned.replace("完 善", "完善")
    cleaned = cleaned.replace("咨 询", "咨询")
    cleaned = cleaned.replace("没问 题", "没问题")
    cleaned = cleaned.replace("准 确率", "准确率")
    cleaned = cleaned.replace("平 介绍", "平台介绍")
    cleaned = cleaned.replace("联 社", "联社")
    cleaned = cleaned.replace("太仓和无锡的调了一下", "基于太仓和无锡调了一下")
    cleaned = cleaned.replace("目标 嘛", "目标嘛")
    cleaned = cleaned.replace("第 二个", "第二个")
    cleaned = cleaned.replace("技 术类", "技术类")
    cleaned = cleaned.replace("影像 、图像 类", "影像、图像类")
    cleaned = cleaned.replace("应 用功能", "应用功能")
    cleaned = cleaned.replace("本 周", "本周")
    cleaned = cleaned.replace("主流程 其实已 经通了", "主流程其实已经通了")
    return cleaned.strip()


def _should_hide_segment(segment: Segment) -> bool:
    duration = max(0, segment.end_ms - segment.start_ms)
    normalized = _clean_export_text(segment.text)
    if not normalized:
        return True
    if duration > 1200:
        return False
    stripped = normalized.strip("，。！？；,.!?; ")
    if not stripped:
        return True
    fillers = {"啊", "嗯", "呃", "额", "唉", "欸", "哦", "哎", "那个", "就是", "对吧"}
    return stripped in fillers or len(stripped) <= 1


def _merge_display_segments(
    segments: list[Segment],
    min_duration_ms: int = 700,
    max_gap_ms: int = 400,
    max_merged_duration_ms: int = 12000,
) -> list[Segment]:
    if len(segments) <= 1:
        return segments

    ordered = sorted(segments, key=lambda item: (item.start_ms, item.end_ms))
    merged: list[Segment] = []
    current = ordered[0]
    for segment in ordered[1:]:
        gap = segment.start_ms - current.end_ms
        current_duration = current.end_ms - current.start_ms
        segment_duration = segment.end_ms - segment.start_ms
        if (
            segment.speaker == current.speaker
            and gap <= max_gap_ms
            and (segment.end_ms - current.start_ms) <= max_merged_duration_ms
        ):
            current = current.model_copy(
                update={
                    "end_ms": segment.end_ms,
                    "text": _join_export_text(current.text, segment.text),
                }
            )
            continue
        if segment_duration <= min_duration_ms and _should_hide_segment(segment):
            current = current.model_copy(update={"end_ms": max(current.end_ms, segment.end_ms)})
            continue
        if current_duration <= min_duration_ms and _should_hide_segment(current) and merged:
            prev = merged[-1]
            merged[-1] = prev.model_copy(
                update={
                    "end_ms": current.end_ms,
                    "text": _join_export_text(prev.text, current.text),
                }
            )
        else:
            merged.append(current)
        current = segment

    if merged and (current.end_ms - current.start_ms) <= min_duration_ms and _should_hide_segment(current):
        prev = merged[-1]
        merged[-1] = prev.model_copy(
            update={
                "end_ms": current.end_ms,
                "text": _join_export_text(prev.text, current.text),
            }
        )
    else:
        merged.append(current)
    return merged


def _join_export_text(left: str | None, right: str | None) -> str:
    left_text = _clean_export_text(left)
    right_text = _clean_export_text(right)
    if not left_text:
        return right_text
    if not right_text:
        return left_text
    if left_text.endswith(right_text):
        return left_text
    return f"{left_text} {right_text}".strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="将 TranscriptResult JSON 导出为可读文本。")
    parser.add_argument("input", help="TranscriptResult JSON 文件路径")
    parser.add_argument("output", help="导出的可读文本路径")
    parser.add_argument("--title", default=None, help="显示标题")
    parser.add_argument("--include-full-text", action="store_true", help="在末尾附带全文")
    args = parser.parse_args()

    from domain.schemas.transcript import TranscriptResult

    payload = Path(args.input).read_text(encoding="utf-8")
    result = TranscriptResult.model_validate_json(payload)
    Path(args.output).write_text(
        render_readable_transcript(result, title=args.title, include_full_text=args.include_full_text),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
