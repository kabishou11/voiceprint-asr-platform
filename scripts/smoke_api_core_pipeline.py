from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

TERMINAL_STATUSES = {"succeeded", "failed"}


@dataclass
class SmokeStep:
    name: str
    method: str
    path: str
    status_code: int | None
    elapsed_ms: int
    ok: bool
    detail: str | None = None


@dataclass
class SmokeReport:
    started_at: str
    base_url: str
    steps: list[SmokeStep] = field(default_factory=list)
    asset_name: str | None = None
    job_id: str | None = None
    final_status: str | None = None
    transcript: dict[str, Any] | None = None
    minutes: dict[str, Any] | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "base_url": self.base_url,
            "asset_name": self.asset_name,
            "job_id": self.job_id,
            "final_status": self.final_status,
            "transcript": self.transcript,
            "minutes": self.minutes,
            "steps": [step.__dict__ for step in self.steps],
        }


class SmokeRunFailed(RuntimeError):
    def __init__(self, message: str, report: SmokeReport) -> None:
        super().__init__(message)
        self.report = report


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_api_base_url(raw: str) -> str:
    base = raw.rstrip("/")
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def build_transcription_payload(args: argparse.Namespace, asset_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "asset_name": asset_name,
        "asr_model": args.asr_model,
        "language": args.language,
        "vad_enabled": args.vad_enabled,
        "itn": args.itn,
        "hotwords": args.hotwords or None,
    }
    if not args.single_speaker:
        payload["diarization_model"] = args.diarization_model
    if args.num_speakers is not None:
        payload["num_speakers"] = args.num_speakers
    if args.min_speakers is not None:
        payload["min_speakers"] = args.min_speakers
    if args.max_speakers is not None:
        payload["max_speakers"] = args.max_speakers
    if args.voiceprint_scope_mode != "none":
        payload["voiceprint_scope_mode"] = args.voiceprint_scope_mode
    if args.voiceprint_group_id:
        payload["voiceprint_group_id"] = args.voiceprint_group_id
    if args.voiceprint_profile_ids:
        payload["voiceprint_profile_ids"] = args.voiceprint_profile_ids
    return payload


def load_hotwords_file(path: str | Path) -> list[str]:
    payload = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(payload)
        words = data.get("hotwords") if isinstance(data, dict) else data
        if not isinstance(words, list):
            raise ValueError(f"热词 JSON 格式错误: {path}")
        return [str(word) for word in words]
    return payload.splitlines()


def normalize_hotwords(words: list[str], *, limit: int = 120, max_length: int = 64) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for word in words:
        clean = " ".join(str(word).strip().split())
        if not clean or len(clean) > max_length or clean in seen:
            continue
        normalized.append(clean)
        seen.add(clean)
        if len(normalized) >= limit:
            break
    return normalized


def collect_hotwords(args: argparse.Namespace) -> list[str]:
    words = list(args.hotwords or [])
    for hotwords_file in args.hotwords_files or []:
        words.extend(load_hotwords_file(hotwords_file))
    return normalize_hotwords(words)


def summarize_transcript_response(payload: dict[str, Any]) -> dict[str, Any]:
    job = payload.get("job") or {}
    transcript = payload.get("transcript") or {}
    segments = transcript.get("segments") or []
    speakers = sorted(
        {
            segment.get("speaker")
            for segment in segments
            if isinstance(segment, dict) and segment.get("speaker")
        }
    )
    return {
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "text_length": len(transcript.get("text") or ""),
        "segment_count": len(segments),
        "speaker_count": len(speakers),
        "speakers": speakers,
    }


def summarize_minutes_response(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") or {}
    evidence_counts = {
        key: len(value)
        for key, value in evidence.items()
        if isinstance(value, list)
    }
    return {
        "mode": payload.get("mode"),
        "model": payload.get("model"),
        "summary_length": len(payload.get("summary") or ""),
        "decision_count": len(payload.get("decisions") or []),
        "action_item_count": len(payload.get("action_items") or []),
        "risk_count": len(payload.get("risks") or []),
        "evidence_counts": evidence_counts,
    }


def default_report_path(audio_path: Path | None) -> Path:
    sample_name = audio_path.stem if audio_path is not None else "asset"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("storage") / "experiments" / sample_name / f"api_smoke_report_{timestamp}.json"


def record_step(
    report: SmokeReport,
    *,
    name: str,
    method: str,
    path: str,
    started: float,
    response: httpx.Response | None = None,
    error: Exception | None = None,
) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    detail = None
    if error is not None:
        detail = str(error)
    elif response is not None and response.status_code >= 400:
        detail = response.text[:1000]
    report.steps.append(
        SmokeStep(
            name=name,
            method=method,
            path=path,
            status_code=response.status_code if response is not None else None,
            elapsed_ms=elapsed_ms,
            ok=response is not None and response.status_code < 400 and error is None,
            detail=detail,
        )
    )


def request_json(
    client: httpx.Client,
    report: SmokeReport,
    *,
    name: str,
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any]:
    started = time.perf_counter()
    response: httpx.Response | None = None
    try:
        response = client.request(method, path, **kwargs)
        record_step(report, name=name, method=method, path=path, started=started, response=response)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        if response is None:
            record_step(report, name=name, method=method, path=path, started=started, error=exc)
        raise
    if not isinstance(payload, dict):
        raise RuntimeError(f"{name} 返回值不是 JSON object")
    return payload


def upload_asset(client: httpx.Client, report: SmokeReport, audio_path: Path) -> str:
    with audio_path.open("rb") as file_obj:
        payload = request_json(
            client,
            report,
            name="upload_asset",
            method="POST",
            path="/assets/upload",
            files={"file": (audio_path.name, file_obj, "application/octet-stream")},
        )
    asset_name = payload.get("asset_name")
    if not isinstance(asset_name, str) or not asset_name:
        raise RuntimeError("上传接口未返回 asset_name")
    return asset_name


def wait_for_job(
    client: httpx.Client,
    report: SmokeReport,
    *,
    job_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = request_json(
            client,
            report,
            name="poll_job",
            method="GET",
            path=f"/jobs/{job_id}",
        )
        last_payload = payload
        status = payload.get("status")
        report.final_status = status if isinstance(status, str) else None
        if status in TERMINAL_STATUSES:
            return payload
        time.sleep(poll_interval_seconds)
    raise TimeoutError(f"任务 {job_id} 在 {timeout_seconds:.0f}s 内未结束: {last_payload}")


def run_smoke(args: argparse.Namespace) -> SmokeReport:
    base_url = normalize_api_base_url(args.base_url)
    audio_path = Path(args.audio).resolve() if args.audio else None
    report = SmokeReport(started_at=utc_now_iso(), base_url=base_url)

    with httpx.Client(base_url=base_url, timeout=args.request_timeout_seconds) as client:
        if args.asset_name:
            asset_name = args.asset_name
        elif audio_path is not None:
            asset_name = upload_asset(client, report, audio_path)
        else:
            raise ValueError("必须提供 --audio 或 --asset-name")
        report.asset_name = asset_name

        create_payload = build_transcription_payload(args, asset_name)
        created = request_json(
            client,
            report,
            name="create_transcription",
            method="POST",
            path="/transcriptions",
            json=create_payload,
        )
        job = created.get("job") or {}
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError("创建转写任务未返回 job.job_id")
        report.job_id = job_id

        final_payload = wait_for_job(
            client,
            report,
            job_id=job_id,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.job_timeout_seconds,
        )
        if report.final_status != "succeeded":
            report.finished_at = utc_now_iso()
            job_error = final_payload.get("error_message") or final_payload.get("error")
            detail = f": {job_error}" if job_error else ""
            raise SmokeRunFailed(f"任务 {job_id} 最终状态为 {report.final_status}{detail}", report)

        transcript_payload = request_json(
            client,
            report,
            name="get_transcription",
            method="GET",
            path=f"/transcriptions/{job_id}",
        )
        report.transcript = summarize_transcript_response(transcript_payload)

        if args.minutes_mode != "skip" and report.final_status == "succeeded":
            minutes_payload = request_json(
                client,
                report,
                name="generate_minutes",
                method="POST",
                path=f"/transcriptions/{job_id}/minutes",
                params={"use_llm": args.minutes_mode == "llm"},
            )
            report.minutes = summarize_minutes_response(minutes_payload)

    report.finished_at = utc_now_iso()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="端到端 API smoke：上传音频、创建转写、轮询、读取结果并生成会议纪要。"
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API 根地址或 /api/v1 地址。",
    )
    parser.add_argument("--audio", help="要上传的本地音频路径。提供 --asset-name 时可省略。")
    parser.add_argument("--asset-name", help="复用已经上传到后端 storage/uploads 的 asset_name。")
    parser.add_argument(
        "--single-speaker",
        action="store_true",
        help="创建单人转写；默认创建多人转写。",
    )
    parser.add_argument("--asr-model", default="funasr-nano")
    parser.add_argument("--diarization-model", default="3dspeaker-diarization")
    parser.add_argument("--language", default="zh-cn")
    parser.add_argument("--vad-enabled", action="store_true")
    parser.add_argument("--no-itn", dest="itn", action="store_false")
    parser.set_defaults(itn=True)
    parser.add_argument("--hotword", dest="hotwords", action="append", default=[])
    parser.add_argument(
        "--hotwords-file",
        dest="hotwords_files",
        action="append",
        default=[],
        help="热词文件，支持 txt 或 {hotwords: []} JSON，可重复传入。",
    )
    parser.add_argument("--num-speakers", type=int)
    parser.add_argument("--min-speakers", type=int)
    parser.add_argument("--max-speakers", type=int)
    parser.add_argument("--voiceprint-scope-mode", choices=["none", "all", "group"], default="none")
    parser.add_argument("--voiceprint-group-id")
    parser.add_argument(
        "--voiceprint-profile-id",
        dest="voiceprint_profile_ids",
        action="append",
        default=[],
    )
    parser.add_argument("--minutes-mode", choices=["skip", "local", "llm"], default="local")
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--job-timeout-seconds", type=float, default=3600.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--output",
        type=Path,
        help="报告输出路径。默认写入 storage/experiments/<sample>/。",
    )
    args = parser.parse_args()
    args.hotwords = collect_hotwords(args)
    return args


def main() -> int:
    args = parse_args()
    audio_path = Path(args.audio).resolve() if args.audio else None
    output_path = args.output or default_report_path(audio_path)
    try:
        report = run_smoke(args)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except SmokeRunFailed as exc:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = exc.report.to_dict()
        payload["error"] = str(exc)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"API smoke 失败，报告已写入: {output_path}")
        print(exc)
        return 1
    except Exception as exc:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        failure = {
            "started_at": utc_now_iso(),
            "finished_at": utc_now_iso(),
            "base_url": normalize_api_base_url(args.base_url),
            "error": str(exc),
        }
        output_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"API smoke 失败，报告已写入: {output_path}")
        print(exc)
        return 1

    print(f"API smoke 完成，报告已写入: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
