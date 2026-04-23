from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from domain.schemas.transcript import Segment
from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
    VoiceprintVerificationResult,
)
from model_adapters.base import (
    AudioAsset,
    DiarizationAdapter,
    VoiceprintAdapter,
    has_cuda_runtime,
    require_available_model,
    resolve_model_reference,
)


class ThreeDSpeakerDiarizationAdapter(DiarizationAdapter):
    """真实说话人分离适配器，基于 VAD + CAM++ 说话人嵌入 + 谱聚类。

    完整管道：
    1. VAD 检测语音段落
    2. 对每个语音段切分为 1.5s 窗口（shift 0.75s）
    3. 提取 CAM++ 说话人嵌入
    4. 谱聚类（SpectralCluster）确定说话人数量和标签
    5. 后处理：合并相邻同说话人段、处理重叠区域、平滑短段
    """

    key = "3dspeaker-diarization"
    display_name = "3D-Speaker Diarization"
    provider = "3dspeaker"

    def __init__(
        self,
        model_name: str = "models/3D-Speaker/campplus",
        *,
        enable_adaptive_clustering: bool = False,
    ) -> None:
        self.model_name = resolve_model_reference(model_name)
        self.enable_adaptive_clustering = enable_adaptive_clustering
        self._vad_model: object | None = None
        self._campplus_model: object | None = None
        self._feature_extractor: object | None = None
        self._cluster_backend: object | None = None
        self._device: str | None = None
        self.num_speakers: int | None = None
        self.min_speakers: int | None = None
        self.max_speakers: int | None = None
        self._vad_segments_cache: list[list[float]] = []
        self.embedding_batch_size = 24
        self.cluster_line = 40
        self.min_cluster_size = 4
        self.merge_cosine_threshold = 0.8
        self.spectral_pval = 0.012
        self.spectral_pval_stable = 0.02
        self.spectral_pval_unstable = 0.008
        self.ahc_cosine_threshold = 0.4
        self.adjacent_similarity_strong_break = 0.45
        self.adjacent_similarity_stable = 0.75
        self.tail_merge_cosine_threshold = 0.72
        self.local_reassign_cosine_threshold = 0.58
        self.local_reassign_margin = 0.02
        self.chunk_run_reassign_max_s = 3.0
        self.chunk_run_bridge_margin = -0.02
        self.chunk_run_reassign_margin = 0.025
        self.frame_decode_step_s = 0.25
        self.frame_decode_stickiness = 0.035
        self.frame_label_vote_boost = 0.22
        self.frame_vote_margin = 0.03
        self.frame_single_speaker_vote_ratio = 0.45
        self.frame_single_speaker_switch_margin = 0.08
        self.frame_run_reassign_max_s = 1.25
        self.frame_run_bridge_margin = -0.05
        self.frame_run_reassign_margin = 0.03

    @property
    def availability(self) -> str:
        has_torch = importlib.util.find_spec("torch") is not None
        has_modelscope = importlib.util.find_spec("modelscope") is not None
        has_local_model = _has_model_artifacts(self.model_name)
        if not has_local_model:
            return "unavailable"
        return "available" if has_torch and has_modelscope and has_cuda_runtime() else "unavailable"

    def _ensure_backend(self) -> bool:
        try:
            import torch
        except ImportError:
            return False
        self._device = self._resolve_device()
        return True

    def _resolve_device(self) -> str:
        if not has_cuda_runtime():
            raise RuntimeError("3D-Speaker 高精度推理要求 CUDA GPU 可用，当前运行时未检测到可用 CUDA。")
        return "cuda:0"

    def _load_audio_raw(self, path: str) -> tuple[np.ndarray, int]:
        """加载音频为原始 PCM 数据（16kHz 单声道）。"""
        import librosa
        import soundfile as sf

        suffix = Path(path).suffix.lower()
        if suffix == ".wav":
            audio, sr = sf.read(path, dtype="float32", always_2d=False)
        else:
            audio, sr = librosa.load(path, sr=None, mono=True)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        # 重采样为 16kHz
        if sr != 16000:
            audio = librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sr, target_sr=16000)
            sr = 16000
        return np.asarray(audio, dtype=np.float32), sr

    def _run_vad(self, audio: np.ndarray, sample_rate: int = 16000) -> list[list[float]]:
        """运行 VAD，返回语音段落列表，每段格式为 [start_sec, end_sec]。"""
        vad_model_path = resolve_model_reference("models/FSMN-VAD")
        if not _has_model_artifacts(vad_model_path):
            return self._energy_vad(audio, sample_rate)
        try:
            from funasr.auto.auto_model import AutoModel

            vad_model = AutoModel(
                model=vad_model_path,
                device=self._device or "cpu",
                disable_update=True,
            )
            # VAD 输入可以是音频路径或 numpy 数组
            result = vad_model.generate(input=audio if isinstance(audio, str) else audio.tolist())
            segments = result[0].get("value", [])
            # 格式为 [[start_ms, end_ms], ...] → 转为 [[start_sec, end_sec], ...]
            return [[s[0] / 1000.0, s[1] / 1000.0] for s in segments]
        except Exception:
            # VAD 模型不可用时，使用能量检测作为后备
            return self._energy_vad(audio, sample_rate)

    def _energy_vad(self, audio: np.ndarray, sample_rate: int = 16000) -> list[list[float]]:
        """基于能量的简单 VAD 后备方案。"""
        frame_len = int(0.025 * sample_rate)  # 25ms 帧
        hop_len = int(0.010 * sample_rate)  # 10ms hop
        energy = np.array([
            np.sqrt(np.mean(audio[i:i + frame_len] ** 2))
            for i in range(0, len(audio) - frame_len, hop_len)
        ])
        threshold = np.mean(energy) * 0.5
        is_speech = energy > threshold

        segments: list[list[float]] = []
        in_speech = False
        start_frame = 0
        min_duration_frames = int(0.3 * sample_rate / hop_len)  # 最小 300ms

        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                start_frame = i
                in_speech = True
            elif not speech and in_speech:
                duration_frames = i - start_frame
                if duration_frames >= min_duration_frames:
                    segments.append([
                        start_frame * hop_len / sample_rate,
                        i * hop_len / sample_rate,
                    ])
                in_speech = False

        if in_speech:
            segments.append([
                start_frame * hop_len / sample_rate,
                len(is_speech) * hop_len / sample_rate,
            ])
        return segments

    def _extract_embeddings(
        self,
        audio: np.ndarray,
        chunk_list: list[tuple[float, float]],
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """从 chunk 语音段提取 CAM++ 说话人嵌入。"""
        try:
            import torch

            runtime = self._ensure_reference_embedding_runtime()
            if runtime is None:
                return np.array([])
            embedding_model, feature_extractor = runtime

            if not chunk_list:
                return np.array([])

            wave_chunks: list[torch.Tensor] = []
            for ch_start, ch_end in chunk_list:
                start = max(0, int(ch_start * sample_rate))
                end = max(start + 1, int(ch_end * sample_rate))
                chunk_audio = np.asarray(audio[start:end], dtype=np.float32)
                if chunk_audio.size == 0:
                    continue
                wave = torch.from_numpy(chunk_audio)
                wave_chunks.append(wave)

            if not wave_chunks:
                return np.array([])

            batch_embeddings: list[np.ndarray] = []
            for start_index in range(0, len(wave_chunks), self.embedding_batch_size):
                batch = wave_chunks[start_index:start_index + self.embedding_batch_size]
                batch_max_len = max(int(wave.shape[0]) for wave in batch)
                padded = []
                for wave in batch:
                    if int(wave.shape[0]) < batch_max_len:
                        repeat = int(np.ceil(batch_max_len / max(1, int(wave.shape[0]))))
                        wave = wave.repeat(repeat)[:batch_max_len]
                    padded.append(wave)
                wavs = torch.stack(padded).unsqueeze(1).to(self._device or "cuda:0")

                with torch.inference_mode():
                    features = torch.vmap(feature_extractor)(wavs)
                    batch_result = embedding_model(features).detach().cpu().numpy()
                batch_embeddings.append(np.asarray(batch_result, dtype=np.float32))
                _clear_cuda_cache()

            embeddings = np.concatenate(batch_embeddings, axis=0) if batch_embeddings else np.array([], dtype=np.float32)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return embeddings / norms

        except Exception:
            # CAM++ 模型不可用时返回空
            return np.array([])

    def _ensure_reference_embedding_runtime(self):
        if self._campplus_model is not None and self._feature_extractor is not None:
            return self._campplus_model, self._feature_extractor
        if not _has_model_artifacts(self.model_name):
            return None
        reference_root = _find_reference_3dspeaker_root()
        if reference_root is None:
            return None
        reference_root_str = str(reference_root)
        if reference_root_str not in sys.path:
            sys.path.insert(0, reference_root_str)
        try:
            import torch
            from speakerlab.models.campplus.DTDNN import CAMPPlus
            from speakerlab.process.processor import FBank

            config_path = Path(self.model_name) / "configuration.json"
            checkpoint_path = Path(self.model_name) / "campplus_cn_3dspeaker.bin"
            if not config_path.exists() or not checkpoint_path.exists():
                return None

            config = json.loads(config_path.read_text(encoding="utf-8"))
            model_config = config.get("model", {}).get("model_config", {})
            feature_dim = int(model_config.get("fbank_dim", 80))
            embedding_size = int(model_config.get("emb_size", 512))

            embedding_model = CAMPPlus(feat_dim=feature_dim, embedding_size=embedding_size)
            checkpoint = torch.load(checkpoint_path, map_location="cpu")
            if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
                checkpoint = checkpoint["state_dict"]
            if isinstance(checkpoint, dict):
                checkpoint = {
                    str(key).removeprefix("module."): value
                    for key, value in checkpoint.items()
                }
            embedding_model.load_state_dict(checkpoint, strict=False)
            embedding_model.eval().to(self._device or "cuda:0")

            feature_extractor = FBank(
                n_mels=feature_dim,
                sample_rate=16000,
                mean_nor=True,
            )
            self._campplus_model = embedding_model
            self._feature_extractor = feature_extractor
            return self._campplus_model, self._feature_extractor
        except Exception:
            return None

    def _cluster_embeddings(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> np.ndarray:
        """使用接近 3D-Speaker CommonClustering 的聚类路径。"""
        if embeddings.size == 0:
            return np.array([], dtype=int)
        if embeddings.shape[0] == 1:
            return np.zeros(1, dtype=int)
        if embeddings.shape[0] < self.cluster_line:
            labels = self._cluster_embeddings_ahc(embeddings)
        else:
            labels = self._cluster_embeddings_spectral(embeddings, chunk_list)

        labels = self._merge_minor_clusters(labels.astype(int), embeddings, min_cluster_size=self.min_cluster_size)
        if self.merge_cosine_threshold is not None:
            labels = self._merge_similar_speakers(labels, embeddings, cosine_threshold=self.merge_cosine_threshold)
        if chunk_list:
            labels = self._reassign_chunk_label_runs(chunk_list, labels, embeddings)
        return self._arrange_labels(labels)

    def _cluster_embeddings_ahc(self, embeddings: np.ndarray) -> np.ndarray:
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics.pairwise import cosine_similarity

        speaker_count = self._resolve_cluster_count(embeddings.shape[0])
        if speaker_count is not None:
            model = AgglomerativeClustering(
                n_clusters=speaker_count,
                metric="cosine",
                linkage="average",
            )
            return model.fit_predict(embeddings).astype(int)

        similarity = cosine_similarity(embeddings, embeddings)
        distance = np.clip(1.0 - similarity, 0.0, 2.0)
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=max(0.0, 1.0 - self.ahc_cosine_threshold),
        )
        return model.fit_predict(distance).astype(int)

    def _cluster_embeddings_spectral(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> np.ndarray:
        from sklearn.cluster import KMeans
        from sklearn.metrics.pairwise import cosine_similarity

        similarity = cosine_similarity(embeddings, embeddings)
        pval = self._resolve_spectral_pval(embeddings, chunk_list)
        pruned = self._prune_affinity(similarity, pval=pval, min_pnum=6)
        sym_pruned = 0.5 * (pruned + pruned.T)
        laplacian = self._build_laplacian(sym_pruned)

        cluster_count = self._resolve_cluster_count(embeddings.shape[0])
        if cluster_count is None:
            cluster_count = self._estimate_cluster_count_from_laplacian(laplacian, embeddings.shape[0], embeddings, chunk_list)

        cluster_count = max(1, min(cluster_count, embeddings.shape[0]))
        spectral_embeddings = self._compute_spectral_embeddings(laplacian, cluster_count)
        model = KMeans(n_clusters=cluster_count, n_init=10, random_state=0)
        return model.fit_predict(spectral_embeddings).astype(int)

    def _resolve_cluster_count(self, sample_count: int) -> int | None:
        if self.num_speakers is not None:
            return max(1, min(int(self.num_speakers), sample_count))
        return None

    def _prune_affinity(self, affinity: np.ndarray, pval: float, min_pnum: int) -> np.ndarray:
        pruned = affinity.copy()
        n_elems = int((1 - pval) * pruned.shape[0])
        n_elems = min(n_elems, max(0, pruned.shape[0] - min_pnum))
        if n_elems <= 0:
            return pruned
        for row_index in range(pruned.shape[0]):
            low_indexes = np.argsort(pruned[row_index, :])[:n_elems]
            pruned[row_index, low_indexes] = 0.0
        return pruned

    def _build_laplacian(self, affinity: np.ndarray) -> np.ndarray:
        matrix = affinity.copy()
        np.fill_diagonal(matrix, 0.0)
        degree = np.sum(np.abs(matrix), axis=1)
        laplacian = -matrix
        laplacian[np.diag_indices_from(laplacian)] = degree
        return laplacian

    def _estimate_cluster_count_from_laplacian(
        self,
        laplacian: np.ndarray,
        sample_count: int,
        embeddings: np.ndarray | None = None,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> int:
        min_num_spks, max_num_spks = self._spectral_cluster_bounds(sample_count, embeddings, chunk_list)
        max_eigen_count = min(max_num_spks + 1, laplacian.shape[0])
        try:
            eigen_values, _ = np.linalg.eigh(laplacian)
        except np.linalg.LinAlgError:
            return min_num_spks
        clipped = np.asarray(eigen_values[:max_eigen_count], dtype=np.float32)
        gaps = np.diff(clipped)
        if gaps.size == 0:
            return min_num_spks
        candidate_gaps = gaps[min_num_spks - 1:max_num_spks]
        if candidate_gaps.size == 0:
            return min_num_spks
        return int(np.argmax(candidate_gaps) + min_num_spks)

    def _compute_spectral_embeddings(self, laplacian: np.ndarray, cluster_count: int) -> np.ndarray:
        try:
            _, eigen_vectors = np.linalg.eigh(laplacian)
        except np.linalg.LinAlgError:
            return np.eye(laplacian.shape[0], cluster_count, dtype=np.float32)
        return np.asarray(eigen_vectors[:, :cluster_count], dtype=np.float32)

    def _spectral_cluster_bounds(
        self,
        sample_count: int,
        embeddings: np.ndarray | None = None,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> tuple[int, int]:
        if self.num_speakers is not None:
            target = max(1, min(int(self.num_speakers), sample_count))
            return target, target
        minimum = max(1, int(self.min_speakers or 1))
        maximum = int(self.max_speakers) if self.max_speakers is not None else 15
        maximum = max(minimum, maximum)
        maximum = min(maximum, sample_count)
        adaptive_upper = self._estimate_speaker_upper_bound(sample_count, embeddings, chunk_list)
        if adaptive_upper is not None:
            maximum = min(maximum, adaptive_upper)
            maximum = max(minimum, maximum)
        return minimum, maximum

    def _resolve_spectral_pval(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> float:
        if not self.enable_adaptive_clustering:
            return self.spectral_pval
        median_similarity = self._adjacent_similarity_median(embeddings, chunk_list)
        if median_similarity is None:
            return self.spectral_pval
        if median_similarity >= self.adjacent_similarity_stable:
            return self.spectral_pval_stable
        if median_similarity <= self.adjacent_similarity_strong_break:
            return self.spectral_pval_unstable
        return self.spectral_pval

    def _estimate_speaker_upper_bound(
        self,
        sample_count: int,
        embeddings: np.ndarray | None = None,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> int | None:
        if not self.enable_adaptive_clustering:
            return None
        if embeddings is None or embeddings.size == 0 or sample_count <= 1:
            return None
        strong_breaks = self._count_adjacent_strong_breaks(embeddings, chunk_list)
        if strong_breaks is None:
            return None
        estimated_upper = max(1, min(sample_count, strong_breaks + 1))
        relaxed_upper = min(sample_count, max(estimated_upper + 1, int(np.ceil(sample_count / 6))))
        return max(1, relaxed_upper)

    def _adjacent_similarity_median(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> float | None:
        similarities = self._adjacent_similarities(embeddings, chunk_list)
        if not similarities:
            return None
        return float(np.median(np.asarray(similarities, dtype=np.float32)))

    def _count_adjacent_strong_breaks(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> int | None:
        similarities = self._adjacent_similarities(embeddings, chunk_list)
        if not similarities:
            return None
        return int(sum(1 for score in similarities if score <= self.adjacent_similarity_strong_break))

    def _adjacent_similarities(
        self,
        embeddings: np.ndarray,
        chunk_list: list[tuple[float, float]] | None = None,
    ) -> list[float]:
        if embeddings.shape[0] <= 1:
            return []
        similarities: list[float] = []
        for index in range(1, embeddings.shape[0]):
            if chunk_list is not None:
                previous_end = float(chunk_list[index - 1][1])
                current_start = float(chunk_list[index][0])
                if current_start - previous_end > 0.8:
                    continue
            similarities.append(
                self._cosine_between(
                    np.asarray(embeddings[index - 1], dtype=np.float32),
                    np.asarray(embeddings[index], dtype=np.float32),
                )
            )
        return similarities

    def _merge_minor_clusters(self, labels: np.ndarray, embeddings: np.ndarray, min_cluster_size: int) -> np.ndarray:
        unique_labels = np.unique(labels)
        sizes = np.array([(labels == label).sum() for label in unique_labels])
        minor = unique_labels[sizes <= min_cluster_size]
        major = unique_labels[sizes > min_cluster_size]
        if minor.size == 0:
            return labels.astype(int)
        if major.size == 0:
            return np.zeros_like(labels, dtype=int)

        from sklearn.metrics.pairwise import cosine_similarity

        major_centers = np.stack([embeddings[labels == label].mean(axis=0) for label in major])
        merged = labels.copy()
        for index, label in enumerate(labels):
            if label not in minor:
                continue
            score = cosine_similarity(embeddings[index][np.newaxis, :], major_centers)
            merged[index] = int(major[int(score.argmax())])
        return merged.astype(int)

    def _merge_similar_speakers(
        self,
        labels: np.ndarray,
        embeddings: np.ndarray,
        cosine_threshold: float,
    ) -> np.ndarray:
        from sklearn.metrics.pairwise import cosine_similarity

        merged = labels.copy()
        while True:
            speaker_ids = np.unique(merged)
            if speaker_ids.size <= 1:
                return self._arrange_labels(merged)
            centers = np.stack([embeddings[merged == speaker_id].mean(axis=0) for speaker_id in speaker_ids])
            affinity = cosine_similarity(centers, centers)
            affinity = np.triu(affinity, 1)
            best_pair = np.unravel_index(int(np.argmax(affinity)), affinity.shape)
            if affinity[best_pair] < cosine_threshold:
                return self._arrange_labels(merged)
            left, right = speaker_ids[np.array(best_pair)]
            merged[merged == right] = left

    def _arrange_labels(self, labels: np.ndarray) -> np.ndarray:
        unique_labels = np.unique(labels)
        remapped = labels.copy()
        for new_label, old_label in enumerate(unique_labels):
            remapped[labels == old_label] = new_label
        return remapped.astype(int)

    def _refine_tail_labels(
        self,
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        if (
            labels.size == 0
            or embeddings.size == 0
            or self.num_speakers is not None
            or self.max_speakers is not None
        ):
            return labels.astype(int)

        speaker_ids = np.unique(labels)
        if speaker_ids.size <= 4:
            return labels.astype(int)

        total_duration = sum(max(0.0, end - start) for start, end in chunk_list)
        if total_duration <= 0:
            return labels.astype(int)

        durations: dict[int, float] = {}
        counts: dict[int, int] = {}
        centers: dict[int, np.ndarray] = {}
        for speaker_id in speaker_ids.astype(int):
            indices = np.where(labels == speaker_id)[0]
            durations[speaker_id] = sum(max(0.0, chunk_list[index][1] - chunk_list[index][0]) for index in indices)
            counts[speaker_id] = int(indices.size)
            centers[speaker_id] = np.asarray(embeddings[indices].mean(axis=0), dtype=np.float32)

        tiny_duration_s = max(45.0, total_duration * 0.005)
        tiny_speakers = {
            speaker_id
            for speaker_id in speaker_ids.astype(int)
            if durations.get(speaker_id, 0.0) <= tiny_duration_s and counts.get(speaker_id, 0) <= 8
        }
        if not tiny_speakers:
            return labels.astype(int)

        refined = labels.copy().astype(int)
        for index, speaker_id in enumerate(labels.astype(int)):
            if speaker_id not in tiny_speakers:
                continue
            current_center = centers.get(speaker_id)
            if current_center is None:
                continue
            candidate_ids = self._tail_merge_candidate_ids(refined, index, tiny_speakers)
            best_speaker: int | None = None
            best_score = -1.0
            for candidate_id in candidate_ids:
                candidate_center = centers.get(candidate_id)
                if candidate_center is None:
                    continue
                cosine = self._cosine_between(current_center, candidate_center)
                if cosine < self.tail_merge_cosine_threshold:
                    continue
                score = cosine + (0.08 if self._is_adjacent_speaker(refined, index, candidate_id) else 0.0)
                if score > best_score:
                    best_score = score
                    best_speaker = candidate_id
            if best_speaker is not None:
                refined[index] = best_speaker
        return self._arrange_labels(refined)

    def _reassign_local_label_noise(
        self,
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        if labels.size < 3 or embeddings.size == 0:
            return labels.astype(int)
        if self.num_speakers is not None:
            return labels.astype(int)

        refined = labels.copy().astype(int)
        for _ in range(2):
            centers = self._speaker_centers(refined, embeddings)
            speaker_durations = self._speaker_durations(chunk_list, refined)
            updated = refined.copy()
            changed = False
            for start_index, end_index in self._contiguous_label_runs(refined):
                current_label = int(refined[start_index])
                run_duration = sum(
                    max(0.0, chunk_list[index][1] - chunk_list[index][0])
                    for index in range(start_index, end_index + 1)
                )
                left_label = int(refined[start_index - 1]) if start_index > 0 else None
                right_label = int(refined[end_index + 1]) if end_index + 1 < refined.shape[0] else None
                is_temporal_bridge = (
                    left_label is not None
                    and right_label is not None
                    and left_label == right_label
                    and left_label != current_label
                )
                candidate_label = self._pick_reassignment_candidate(
                    left_label,
                    right_label,
                    current_label,
                    speaker_durations,
                    run_duration,
                )
                if candidate_label is None:
                    continue
                if run_duration > 3.2:
                    continue
                run_embedding = np.asarray(embeddings[start_index:end_index + 1].mean(axis=0), dtype=np.float32)
                current_center = centers.get(current_label)
                candidate_center = centers.get(candidate_label)
                if current_center is None or candidate_center is None:
                    continue
                current_score = self._cosine_between(run_embedding, current_center)
                candidate_score = self._cosine_between(run_embedding, candidate_center)
                if candidate_score < self.local_reassign_cosine_threshold:
                    continue
                margin = -0.01 if is_temporal_bridge else self.local_reassign_margin
                if candidate_score + margin < current_score:
                    continue
                updated[start_index:end_index + 1] = candidate_label
                changed = True
            refined = self._arrange_labels(updated)
            if not changed:
                break
        return refined.astype(int)

    def _reassign_chunk_label_runs(
        self,
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        if labels.size < 3 or embeddings.size == 0:
            return labels.astype(int)
        if self.num_speakers is not None:
            return labels.astype(int)

        refined = labels.copy().astype(int)
        for _ in range(2):
            centers = self._speaker_centers(refined, embeddings)
            speaker_durations = self._speaker_durations(chunk_list, refined)
            updated = refined.copy()
            changed = False
            for start_index, end_index in self._contiguous_label_runs(refined):
                left_label = int(refined[start_index - 1]) if start_index > 0 else None
                right_label = int(refined[end_index + 1]) if end_index + 1 < refined.shape[0] else None
                if left_label is None or right_label is None:
                    continue

                current_label = int(refined[start_index])
                run_duration = sum(
                    max(0.0, chunk_list[index][1] - chunk_list[index][0])
                    for index in range(start_index, end_index + 1)
                )
                if run_duration > self.chunk_run_reassign_max_s:
                    continue

                current_total = float(speaker_durations.get(current_label, 0.0))
                is_bridge = left_label == right_label and left_label != current_label
                if not is_bridge and current_total > max(5.0, run_duration * 2.5):
                    continue

                run_embedding = np.asarray(embeddings[start_index:end_index + 1].mean(axis=0), dtype=np.float32)
                current_center = centers.get(current_label)
                if current_center is None:
                    continue
                current_score = self._cosine_between(run_embedding, current_center)
                effective_current_score = current_score
                if is_bridge and current_total <= max(3.5, run_duration * 1.5):
                    effective_current_score = min(effective_current_score, 0.0)
                candidate_labels = []
                for candidate in (left_label, right_label):
                    if candidate != current_label and candidate not in candidate_labels:
                        candidate_labels.append(candidate)
                best_candidate: int | None = None
                best_score = effective_current_score
                margin = self.chunk_run_bridge_margin if is_bridge else self.chunk_run_reassign_margin
                for candidate_label in candidate_labels:
                    candidate_center = centers.get(int(candidate_label))
                    if candidate_center is None:
                        continue
                    candidate_score = self._cosine_between(run_embedding, candidate_center)
                    if candidate_score + margin < effective_current_score:
                        continue
                    if best_candidate is None or candidate_score > best_score:
                        best_candidate = int(candidate_label)
                        best_score = candidate_score
                if best_candidate is None:
                    continue
                updated[start_index:end_index + 1] = best_candidate
                changed = True
            refined = self._arrange_labels(updated)
            if not changed:
                break
        return refined.astype(int)

    def _contiguous_label_runs(self, labels: np.ndarray) -> list[tuple[int, int]]:
        runs: list[tuple[int, int]] = []
        if labels.size == 0:
            return runs
        start_index = 0
        for index in range(1, labels.shape[0]):
            if int(labels[index]) == int(labels[index - 1]):
                continue
            runs.append((start_index, index - 1))
            start_index = index
        runs.append((start_index, labels.shape[0] - 1))
        return runs

    def _speaker_centers(self, labels: np.ndarray, embeddings: np.ndarray) -> dict[int, np.ndarray]:
        centers: dict[int, np.ndarray] = {}
        for speaker_id in np.unique(labels).astype(int):
            indices = np.where(labels == speaker_id)[0]
            if indices.size == 0:
                continue
            centers[speaker_id] = np.asarray(embeddings[indices].mean(axis=0), dtype=np.float32)
        return centers

    def _pick_reassignment_candidate(
        self,
        left_label: int | None,
        right_label: int | None,
        current_label: int,
        speaker_durations: dict[int, float],
        run_duration: float,
    ) -> int | None:
        if left_label is not None and right_label is not None and left_label == right_label and left_label != current_label:
            return left_label
        current_total = float(speaker_durations.get(current_label, 0.0))
        if current_total <= max(4.5, run_duration * 2.2):
            candidates = [label for label in (left_label, right_label) if label is not None and label != current_label]
            if len(candidates) == 1:
                return int(candidates[0])
        return None

    def _speaker_durations(self, chunk_list: list[tuple[float, float]], labels: np.ndarray) -> dict[int, float]:
        durations: dict[int, float] = {}
        for index, speaker_id in enumerate(labels.astype(int)):
            start, end = chunk_list[index]
            durations[speaker_id] = durations.get(speaker_id, 0.0) + max(0.0, end - start)
        return durations

    def _tail_merge_candidate_ids(self, labels: np.ndarray, index: int, tiny_speakers: set[int]) -> list[int]:
        candidates: list[int] = []
        for offset in (1, 2, 3):
            left_index = index - offset
            right_index = index + offset
            if left_index >= 0:
                candidate = int(labels[left_index])
                if candidate not in tiny_speakers and candidate not in candidates:
                    candidates.append(candidate)
            if right_index < labels.shape[0]:
                candidate = int(labels[right_index])
                if candidate not in tiny_speakers and candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _is_adjacent_speaker(self, labels: np.ndarray, index: int, speaker_id: int) -> bool:
        left_match = index > 0 and int(labels[index - 1]) == speaker_id
        right_match = index + 1 < labels.shape[0] and int(labels[index + 1]) == speaker_id
        return left_match or right_match

    def _cosine_between(self, left: np.ndarray, right: np.ndarray) -> float:
        left_norm = np.linalg.norm(left)
        right_norm = np.linalg.norm(right)
        if left_norm == 0 or right_norm == 0:
            return -1.0
        return float(np.dot(left, right) / (left_norm * right_norm))

    def _compress_segments(self, seg_list: list[list[float | int]]) -> list[tuple[int, int, int]]:
        if not seg_list:
            return []

        merged: list[list[float | int]] = []
        for index, item in enumerate(seg_list):
            seg_start, seg_end, speaker_id = item
            if index == 0:
                merged.append([seg_start, seg_end, speaker_id])
                continue
            if speaker_id == merged[-1][2]:
                if float(seg_start) > float(merged[-1][1]):
                    merged.append([seg_start, seg_end, speaker_id])
                else:
                    merged[-1][1] = seg_end
                continue
            if float(seg_start) < float(merged[-1][1]):
                pivot = (float(merged[-1][1]) + float(seg_start)) / 2.0
                merged[-1][1] = pivot
                seg_start = pivot
            merged.append([seg_start, seg_end, speaker_id])

        return [
            (int(float(seg_start) * 1000), int(float(seg_end) * 1000), int(speaker_id))
            for seg_start, seg_end, speaker_id in merged
        ]

    def _decode_framewise_segments(
        self,
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
        vad_segments: list[list[float]],
    ) -> list[tuple[int, int, int]]:
        if not chunk_list or labels.size == 0 or embeddings.size == 0 or not vad_segments:
            return []

        centers = self._speaker_centers(labels, embeddings)
        if not centers:
            return []

        decoded_segments: list[list[float | int]] = []
        step_s = max(0.1, float(self.frame_decode_step_s))
        for vad_start, vad_end in vad_segments:
            if vad_end <= vad_start:
                continue
            frame_labels = self._decode_vad_frames(
                vad_start,
                vad_end,
                chunk_list,
                labels,
                embeddings,
                centers,
                step_s,
            )
            if not frame_labels:
                continue
            current_label = frame_labels[0][2]
            current_start = frame_labels[0][0]
            current_end = frame_labels[0][1]
            for frame_start, frame_end, speaker_id in frame_labels[1:]:
                if speaker_id == current_label and frame_start <= current_end + 1e-6:
                    current_end = frame_end
                    continue
                decoded_segments.append([current_start, current_end, current_label])
                current_start, current_end, current_label = frame_start, frame_end, speaker_id
            decoded_segments.append([current_start, current_end, current_label])

        return self._compress_segments(decoded_segments)

    def _decode_vad_frames(
        self,
        vad_start: float,
        vad_end: float,
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
        centers: dict[int, np.ndarray],
        step_s: float,
    ) -> list[tuple[float, float, int]]:
        frame_items: list[tuple[float, float, int]] = []
        previous_label: int | None = None
        cursor = vad_start
        while cursor < vad_end - 1e-6:
            frame_start = cursor
            frame_end = min(vad_end, cursor + step_s)
            overlap_indices = self._chunk_indices_for_window(chunk_list, frame_start, frame_end)
            if not overlap_indices:
                cursor = frame_end
                continue
            speaker_scores = self._speaker_scores_for_window(
                overlap_indices,
                chunk_list,
                labels,
                embeddings,
                centers,
                frame_start,
                frame_end,
            )
            if not speaker_scores:
                cursor = frame_end
                continue
            ordered = sorted(speaker_scores.items(), key=lambda item: item[1], reverse=True)
            best_label, best_score = ordered[0]
            best_vote = self._frame_label_vote(
                overlap_indices,
                chunk_list,
                labels,
                int(best_label),
                frame_start,
                frame_end,
            )
            estimated_count = self._estimate_frame_speaker_count(
                overlap_indices,
                chunk_list,
                labels,
                frame_start,
                frame_end,
            )
            if (
                previous_label is not None
                and previous_label in speaker_scores
                and (
                    speaker_scores[previous_label] + self.frame_decode_stickiness >= best_score
                    or self._frame_label_vote(
                        overlap_indices,
                        chunk_list,
                        labels,
                        int(previous_label),
                        frame_start,
                        frame_end,
                    ) + self.frame_vote_margin >= best_vote
                )
            ):
                best_label = previous_label
                best_score = speaker_scores[previous_label]
                best_vote = self._frame_label_vote(
                    overlap_indices,
                    chunk_list,
                    labels,
                    int(previous_label),
                    frame_start,
                    frame_end,
                )
            elif (
                estimated_count <= 1
                and previous_label is not None
                and previous_label in speaker_scores
            ):
                previous_vote = self._frame_label_vote(
                    overlap_indices,
                    chunk_list,
                    labels,
                    int(previous_label),
                    frame_start,
                    frame_end,
                )
                previous_score = speaker_scores[previous_label]
                if (
                    int(best_label) != int(previous_label)
                    and best_vote <= previous_vote + self.frame_single_speaker_switch_margin
                    and best_score <= previous_score + self.frame_decode_stickiness
                ):
                    best_label = previous_label
                    best_score = previous_score
            previous_label = int(best_label)
            frame_items.append((frame_start, frame_end, int(best_label)))
            cursor = frame_end
        repaired = self._repair_frame_sequence(frame_items, step_s)
        return self._reassign_frame_runs(repaired, chunk_list, embeddings, centers)

    def _chunk_indices_for_window(
        self,
        chunk_list: list[tuple[float, float]],
        frame_start: float,
        frame_end: float,
    ) -> list[int]:
        indices: list[int] = []
        for index, (chunk_start, chunk_end) in enumerate(chunk_list):
            if chunk_end <= frame_start or chunk_start >= frame_end:
                continue
            indices.append(index)
        return indices

    def _speaker_scores_for_window(
        self,
        overlap_indices: list[int],
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        embeddings: np.ndarray,
        centers: dict[int, np.ndarray],
        frame_start: float,
        frame_end: float,
    ) -> dict[int, float]:
        scores: dict[int, float] = {}
        label_votes: dict[int, float] = {}
        for index in overlap_indices:
            chunk_start, chunk_end = chunk_list[index]
            overlap = max(0.0, min(chunk_end, frame_end) - max(chunk_start, frame_start))
            if overlap <= 0:
                continue
            chunk_embedding = embeddings[index]
            assigned_label = int(labels[index])
            label_votes[assigned_label] = label_votes.get(assigned_label, 0.0) + overlap
            for speaker_id, center in centers.items():
                cosine = self._cosine_between(chunk_embedding, center)
                if cosine <= 0:
                    continue
                scores[int(speaker_id)] = scores.get(int(speaker_id), 0.0) + overlap * cosine
        for speaker_id, vote in label_votes.items():
            scores[speaker_id] = scores.get(speaker_id, 0.0) + vote * self.frame_label_vote_boost
        return scores

    def _frame_label_vote(
        self,
        overlap_indices: list[int],
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        speaker_id: int,
        frame_start: float,
        frame_end: float,
    ) -> float:
        vote = 0.0
        for index in overlap_indices:
            if int(labels[index]) != int(speaker_id):
                continue
            chunk_start, chunk_end = chunk_list[index]
            vote += max(0.0, min(chunk_end, frame_end) - max(chunk_start, frame_start))
        return vote

    def _estimate_frame_speaker_count(
        self,
        overlap_indices: list[int],
        chunk_list: list[tuple[float, float]],
        labels: np.ndarray,
        frame_start: float,
        frame_end: float,
    ) -> int:
        if not overlap_indices:
            return 0
        votes: dict[int, float] = {}
        frame_duration = max(1e-6, frame_end - frame_start)
        for index in overlap_indices:
            chunk_start, chunk_end = chunk_list[index]
            overlap = max(0.0, min(chunk_end, frame_end) - max(chunk_start, frame_start))
            if overlap <= 0:
                continue
            label = int(labels[index])
            votes[label] = votes.get(label, 0.0) + overlap
        if not votes:
            return 0
        ordered = sorted(votes.values(), reverse=True)
        if len(ordered) == 1:
            return 1
        if ordered[1] / frame_duration >= self.frame_single_speaker_vote_ratio:
            return 2
        return 1

    def _repair_frame_sequence(
        self,
        frame_items: list[tuple[float, float, int]],
        step_s: float,
    ) -> list[tuple[float, float, int]]:
        if len(frame_items) <= 2:
            return frame_items

        labels = [int(item[2]) for item in frame_items]
        max_bridge_frames = max(1, int(round(0.75 / max(step_s, 1e-3))))
        for _ in range(2):
            changed = False
            runs = self._frame_runs(labels)
            for run_start, run_end in runs:
                left_label = labels[run_start - 1] if run_start > 0 else None
                right_label = labels[run_end + 1] if run_end + 1 < len(labels) else None
                if left_label is None or right_label is None or left_label != right_label:
                    continue
                if (run_end - run_start + 1) > max_bridge_frames:
                    continue
                if labels[run_start] == left_label:
                    continue
                for index in range(run_start, run_end + 1):
                    labels[index] = left_label
                changed = True
            if not changed:
                break

        repaired = [
            (frame_start, frame_end, labels[index])
            for index, (frame_start, frame_end, _) in enumerate(frame_items)
        ]
        return repaired

    def _reassign_frame_runs(
        self,
        frame_items: list[tuple[float, float, int]],
        chunk_list: list[tuple[float, float]],
        embeddings: np.ndarray,
        centers: dict[int, np.ndarray],
    ) -> list[tuple[float, float, int]]:
        if len(frame_items) < 3 or embeddings.size == 0:
            return frame_items

        labels = [int(item[2]) for item in frame_items]
        updated = labels[:]
        changed = False
        for run_start, run_end in self._frame_runs(labels):
            current_label = labels[run_start]
            left_label = labels[run_start - 1] if run_start > 0 else None
            right_label = labels[run_end + 1] if run_end + 1 < len(labels) else None
            if left_label is None or right_label is None:
                continue
            candidate_labels = [
                label
                for label in (left_label, right_label)
                if label is not None and label != current_label
            ]
            if not candidate_labels:
                continue

            run_start_s = frame_items[run_start][0]
            run_end_s = frame_items[run_end][1]
            run_duration_s = max(0.0, run_end_s - run_start_s)
            if run_duration_s > self.frame_run_reassign_max_s:
                continue

            overlap_indices = self._chunk_indices_for_window(chunk_list, run_start_s, run_end_s)
            if not overlap_indices:
                continue

            run_embedding = np.asarray(embeddings[overlap_indices].mean(axis=0), dtype=np.float32)
            current_center = centers.get(int(current_label))
            if current_center is None:
                continue
            current_score = self._cosine_between(run_embedding, current_center)
            is_bridge = (
                left_label is not None
                and right_label is not None
                and left_label == right_label
                and left_label != current_label
            )
            margin = self.frame_run_bridge_margin if is_bridge else self.frame_run_reassign_margin

            best_candidate: int | None = None
            best_score = current_score
            for candidate_label in candidate_labels:
                candidate_center = centers.get(int(candidate_label))
                if candidate_center is None:
                    continue
                candidate_score = self._cosine_between(run_embedding, candidate_center)
                if candidate_score + margin < current_score:
                    continue
                if best_candidate is None or candidate_score > best_score:
                    best_candidate = int(candidate_label)
                    best_score = candidate_score

            if best_candidate is None:
                continue

            for index in range(run_start, run_end + 1):
                updated[index] = best_candidate
            changed = True

        if not changed:
            return frame_items

        return [
            (frame_start, frame_end, updated[index])
            for index, (frame_start, frame_end, _) in enumerate(frame_items)
        ]

    def _frame_runs(self, labels: list[int]) -> list[tuple[int, int]]:
        if not labels:
            return []
        runs: list[tuple[int, int]] = []
        start_index = 0
        for index in range(1, len(labels)):
            if labels[index] == labels[index - 1]:
                continue
            runs.append((start_index, index - 1))
            start_index = index
        runs.append((start_index, len(labels) - 1))
        return runs

    def _postprocess(self, chunk_list: list, labels: np.ndarray) -> list[tuple[int, int, int]]:
        """将 chunk 级标签合并为稳定的 speaker 段。"""
        if not chunk_list:
            return []

        normalized = [[float(item[0]), float(item[1]), int(labels[index]) if index < len(labels) else 0] for index, item in enumerate(chunk_list)]
        return self._compress_segments(normalized)

    def _smooth_segments(self, segments: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
        if not segments:
            return []

        merged: list[list[int]] = [[start, end, speaker] for start, end, speaker in segments if end > start]
        if not merged:
            return []

        gap_tolerance_ms = 200
        isolated_duration_ms = 600
        edge_duration_ms = 500

        collapsed: list[list[int]] = [merged[0][:]]
        for start, end, speaker in merged[1:]:
            previous = collapsed[-1]
            if speaker == previous[2] and start - previous[1] <= gap_tolerance_ms:
                previous[1] = max(previous[1], end)
                continue
            collapsed.append([start, end, speaker])

        index = 0
        while index < len(collapsed):
            current = collapsed[index]
            duration = current[1] - current[0]
            prev_seg = collapsed[index - 1] if index > 0 else None
            next_seg = collapsed[index + 1] if index + 1 < len(collapsed) else None

            if (
                prev_seg is not None
                and next_seg is not None
                and duration <= isolated_duration_ms
                and prev_seg[2] == next_seg[2]
                and self._can_remove_speaker(collapsed, index)
            ):
                prev_seg[1] = next_seg[1]
                collapsed.pop(index + 1)
                collapsed.pop(index)
                index = max(0, index - 1)
                continue

            if (
                prev_seg is None
                and next_seg is not None
                and duration <= edge_duration_ms
                and self._can_remove_speaker(collapsed, index)
            ):
                next_seg[0] = current[0]
                collapsed.pop(index)
                continue

            if (
                next_seg is None
                and prev_seg is not None
                and duration <= edge_duration_ms
                and self._can_remove_speaker(collapsed, index)
            ):
                prev_seg[1] = current[1]
                collapsed.pop(index)
                index = max(0, index - 1)
                continue

            index += 1

        collapsed = self._enforce_speaker_upper_bound(collapsed)
        collapsed = self._merge_tiny_tail_speakers(collapsed)
        normalized: list[tuple[int, int, int]] = []
        for start, end, speaker in collapsed:
            if normalized and normalized[-1][2] == speaker and start - normalized[-1][1] <= gap_tolerance_ms:
                prev_start, prev_end, prev_speaker = normalized[-1]
                normalized[-1] = (prev_start, max(prev_end, end), prev_speaker)
                continue
            normalized.append((start, end, speaker))
        return normalized

    def _speaker_count_bounds(self) -> tuple[int, int | None]:
        if self.num_speakers is not None:
            target = max(1, int(self.num_speakers))
            return target, target
        minimum = max(1, int(self.min_speakers or 1))
        maximum = int(self.max_speakers) if self.max_speakers is not None else None
        if maximum is not None:
            maximum = max(minimum, maximum)
        return minimum, maximum

    def _can_remove_speaker(self, segments: list[list[int]], index: int) -> bool:
        minimum, _ = self._speaker_count_bounds()
        speaker = segments[index][2]
        unique_speakers = {item[2] for item in segments}
        if speaker not in unique_speakers:
            return True
        remaining = unique_speakers - {speaker}
        return len(remaining) >= minimum

    def _enforce_speaker_upper_bound(self, segments: list[list[int]]) -> list[list[int]]:
        _, maximum = self._speaker_count_bounds()
        if maximum is None:
            return segments

        collapsed = [item[:] for item in segments]
        while len({item[2] for item in collapsed}) > maximum:
            durations: dict[int, int] = {}
            for start, end, speaker in collapsed:
                durations[speaker] = durations.get(speaker, 0) + max(0, end - start)
            weakest_speaker = min(durations, key=durations.get)
            reassigned = False
            for index, item in enumerate(collapsed):
                if item[2] != weakest_speaker:
                    continue
                neighbor = self._dominant_neighbor_speaker(collapsed, index)
                if neighbor is None:
                    continue
                item[2] = neighbor
                reassigned = True
            if not reassigned:
                break
            collapsed = self._merge_adjacent_ms_segments(collapsed)
        return collapsed

    def _dominant_neighbor_speaker(self, segments: list[list[int]], index: int) -> int | None:
        current = segments[index]
        current_duration = max(0, current[1] - current[0])
        prev_seg = segments[index - 1] if index > 0 else None
        next_seg = segments[index + 1] if index + 1 < len(segments) else None
        candidates: list[tuple[int, int]] = []
        if prev_seg is not None:
            candidates.append((prev_seg[2], max(0, prev_seg[1] - prev_seg[0])))
        if next_seg is not None:
            candidates.append((next_seg[2], max(0, next_seg[1] - next_seg[0])))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[1], item[0] == current[2], current_duration), reverse=True)
        return candidates[0][0]

    def _merge_adjacent_ms_segments(self, segments: list[list[int]]) -> list[list[int]]:
        if not segments:
            return []
        merged: list[list[int]] = [segments[0][:]]
        for start, end, speaker in segments[1:]:
            previous = merged[-1]
            if speaker == previous[2] and start <= previous[1]:
                previous[1] = max(previous[1], end)
                continue
            if speaker == previous[2] and start - previous[1] <= 200:
                previous[1] = max(previous[1], end)
                continue
            merged.append([start, end, speaker])
        return merged

    def _merge_tiny_tail_speakers(self, segments: list[list[int]]) -> list[list[int]]:
        if not segments or self.num_speakers is not None or self.max_speakers is not None:
            return segments

        unique_speakers = {item[2] for item in segments}
        if len(unique_speakers) <= 4:
            return segments

        total_duration = sum(max(0, end - start) for start, end, _ in segments)
        if total_duration <= 0:
            return segments

        durations: dict[int, int] = {}
        counts: dict[int, int] = {}
        for start, end, speaker in segments:
            durations[speaker] = durations.get(speaker, 0) + max(0, end - start)
            counts[speaker] = counts.get(speaker, 0) + 1

        tiny_speakers = {
            speaker
            for speaker, duration in durations.items()
            if duration <= max(45000, int(total_duration * 0.005)) and counts.get(speaker, 0) <= 5
        }
        if not tiny_speakers:
            return segments

        collapsed = [item[:] for item in segments]
        for index, item in enumerate(collapsed):
            if item[2] not in tiny_speakers:
                continue
            neighbor = self._dominant_neighbor_speaker(collapsed, index)
            if neighbor is None or neighbor in tiny_speakers:
                continue
            item[2] = neighbor
        return self._merge_adjacent_ms_segments(collapsed)

    def _build_chunk_list(self, vad_segments: list[list[float]]) -> list[tuple[float, float]]:
        chunk_list: list[tuple[float, float]] = []
        window_s = 1.5
        shift_s = 0.75
        min_chunk_s = 0.8

        for seg_start, seg_end in vad_segments:
            duration = seg_end - seg_start
            if duration <= 0:
                continue
            if duration <= window_s:
                chunk_list.append((seg_start, seg_end))
                continue

            cursor = seg_start
            while cursor < seg_end:
                chunk_end = min(cursor + window_s, seg_end)
                if chunk_end - cursor >= min_chunk_s:
                    chunk_list.append((cursor, chunk_end))
                if chunk_end >= seg_end:
                    break
                cursor += shift_s

        return chunk_list

    def diarize(self, asset: AudioAsset) -> list[Segment]:
        require_available_model(self.availability, model_label=self.display_name, purpose="说话人分离")
        if not self._ensure_backend():
            raise RuntimeError(f"{self.display_name} 未能完成 CUDA 推理后端初始化。")

        try:
            audio, sr = self._load_audio_raw(asset.path)
            # Step 1: VAD 检测语音段落
            vad_segments = self._run_vad(audio, sr)
            self._vad_segments_cache = vad_segments
            if not vad_segments:
                raise RuntimeError("3D-Speaker 未检测到有效语音段，无法生成稳定的说话人分离结果。")

            chunk_list = self._build_chunk_list(vad_segments)
            if not chunk_list:
                raise RuntimeError("3D-Speaker 未生成有效聚类窗口，无法继续高精度分离。")

            embeddings = self._extract_embeddings(audio, chunk_list, sr)
            if len(embeddings) == 0:
                raise RuntimeError("3D-Speaker 未产出有效说话人嵌入。")

            labels = self._cluster_embeddings(embeddings, chunk_list)
            if len(labels) == 0:
                raise RuntimeError("3D-Speaker 未产出有效说话人标签。")
            labels = self._reassign_local_label_noise(chunk_list, labels, embeddings)
            labels = self._refine_tail_labels(chunk_list, labels, embeddings)

            ms_segments = self._decode_framewise_segments(chunk_list, labels, embeddings, vad_segments)
            if not ms_segments:
                ms_segments = self._postprocess(chunk_list, labels)
            ms_segments = self._smooth_segments(ms_segments)
            if not ms_segments:
                raise RuntimeError("3D-Speaker 说话人后处理失败，未得到稳定分段。")

            # 转换为 Segment 对象
            return [
                Segment(
                    start_ms=int(s[0]),
                    end_ms=int(s[1]),
                    text="",
                    speaker=f"SPEAKER_{int(s[2]):02d}",
                    confidence=0.92,
                )
                for s in ms_segments
            ]

        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("3D-Speaker CUDA 高精度分离执行失败。") from exc

    def _fallback_diarize(self, asset: AudioAsset) -> list[Segment]:
        """后备占位说话人分离（基于音频能量分析）。"""
        try:
            import librosa
            import soundfile as sf

            suffix = Path(asset.path).suffix.lower()
            if suffix == ".wav":
                audio, sr = sf.read(asset.path, dtype="float32", always_2d=False)
            else:
                audio, sr = librosa.load(asset.path, sr=None, mono=True)

            if getattr(audio, "ndim", 1) > 1:
                audio = audio.mean(axis=1)
            if sr != 16000:
                audio = librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sr, target_sr=16000)
                sr = 16000

            # 基于能量的简单 VAD
            vad_segments = self._energy_vad(audio, sr)
            if not vad_segments:
                duration_ms = int(len(audio) / sr * 1000)
                return [Segment(start_ms=0, end_ms=duration_ms, text="", speaker="SPEAKER_00", confidence=0.80)]

            segments = []
            for start_s, end_s in vad_segments:
                segments.append(Segment(
                    start_ms=int(start_s * 1000),
                    end_ms=int(end_s * 1000),
                    text="",
                    speaker="SPEAKER_00",
                    confidence=0.82,
                ))
            return segments

        except Exception:
            # 完全失败时的最小返回
            seed = int(hashlib.sha1(asset.path.encode("utf-8")).hexdigest()[:6], 16)
            first = 2200 + seed % 700
            second = first + 2200 + seed % 900
            third = second + 2000 + seed % 1100
            return [
                Segment(start_ms=0, end_ms=first, text="", speaker="SPEAKER_00", confidence=0.91),
                Segment(start_ms=first, end_ms=second, text="", speaker="SPEAKER_01", confidence=0.88),
                Segment(start_ms=second, end_ms=third, text="", speaker="SPEAKER_00", confidence=0.90),
            ]


class ThreeDSpeakerVoiceprintAdapter(VoiceprintAdapter):
    """3D-Speaker 说话人验证适配器，基于 CAM++ 说话人嵌入向量相似度。"""

    key = "3dspeaker-embedding"
    display_name = "3D-Speaker Embedding"
    provider = "3dspeaker"

    def __init__(self, model_name: str = "models/3D-Speaker/campplus") -> None:
        self.model_name = resolve_model_reference(model_name)
        self._profile_vectors: dict[str, np.ndarray] = {}
        self._profile_assets: dict[str, str] = {}
        self._sv_model = None

    @property
    def availability(self) -> str:
        has_torch = importlib.util.find_spec("torch") is not None
        has_modelscope = importlib.util.find_spec("modelscope") is not None
        has_local_model = _has_model_artifacts(self.model_name)
        if not has_local_model:
            return "unavailable"
        return "available" if has_torch and has_modelscope and has_cuda_runtime() else "unavailable"

    def _ensure_sv_pipeline(self):
        if self._sv_model is not None:
            return self._sv_model
        if not _has_model_artifacts(self.model_name):
            return None
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks

            self._sv_model = pipeline(
                task=Tasks.speaker_verification,
                model=self.model_name,
            )
            return self._sv_model
        except Exception:
            return None

    def _run_sv_score(self, sv_pipeline, enroll_path: str, probe_path: str) -> float:
        with tempfile.TemporaryDirectory() as tmpdir:
            normalized_enroll = _normalize_audio_for_sv(enroll_path, Path(tmpdir) / "enroll.wav")
            normalized_probe = _normalize_audio_for_sv(probe_path, Path(tmpdir) / "probe.wav")
            result = sv_pipeline([normalized_enroll, normalized_probe])
            _clear_cuda_cache()
            if isinstance(result, dict):
                return float(result.get("score", 0.0))
            return 0.0

    def enroll(self, asset: AudioAsset, profile_id: str) -> dict:
        require_available_model(self.availability, model_label=self.display_name, purpose="声纹注册")
        self._profile_assets[profile_id] = asset.path
        sv_pipeline = self._ensure_sv_pipeline()
        if sv_pipeline is None:
            raise RuntimeError("3D-Speaker CAM++ CUDA 声纹推理管道初始化失败。")
        return {
            "profile_id": profile_id,
            "asset": asset.path,
            "model_key": self.key,
            "model_name": self.model_name,
            "status": "enrolled",
            "embedding_ref": f"embedding:{profile_id}:{Path(asset.path).stem}",
        }

    def verify(self, asset: AudioAsset, profile_id: str, threshold: float) -> VoiceprintVerificationResult:
        require_available_model(self.availability, model_label=self.display_name, purpose="声纹验证")
        sv_pipeline = self._ensure_sv_pipeline()
        enrolled_asset = self._profile_assets.get(profile_id)
        if sv_pipeline is None or enrolled_asset is None:
            raise RuntimeError("3D-Speaker CAM++ CUDA 声纹验证未就绪，或档案尚未完成真实注册。")
        score = round(self._run_sv_score(sv_pipeline, enrolled_asset, asset.path), 5)
        return VoiceprintVerificationResult(
            profile_id=profile_id,
            score=score,
            threshold=threshold,
            matched=score >= threshold,
        )

    def identify(self, asset: AudioAsset, top_k: int) -> VoiceprintIdentificationResult:
        require_available_model(self.availability, model_label=self.display_name, purpose="声纹识别")
        sv_pipeline = self._ensure_sv_pipeline()
        if sv_pipeline is None:
            raise RuntimeError("3D-Speaker CAM++ CUDA 声纹识别管道未就绪。")
        known_profiles = self._profile_assets
        if not known_profiles:
            return VoiceprintIdentificationResult(candidates=[], matched=False)
        candidates = []
        for index, (profile_id, value) in enumerate(known_profiles.items(), start=1):
            score = round(self._run_sv_score(sv_pipeline, str(value), asset.path), 5)
            candidates.append(
                VoiceprintIdentificationCandidate(
                    profile_id=profile_id,
                    display_name=profile_id,
                    score=score,
                    rank=index,
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        reranked = [candidate.model_copy(update={"rank": idx + 1}) for idx, candidate in enumerate(candidates[:top_k])]
        _clear_cuda_cache()
        return VoiceprintIdentificationResult(candidates=reranked, matched=bool(reranked))

    def _ensure_sv_model(self):
        return None

    def _extract_embedding_from_result(self, result) -> np.ndarray | None:
        if not result:
            return None
        payload = result[0] if isinstance(result, list) else result
        if isinstance(payload, dict):
            for key in ("spk_embedding", "embedding", "emb", "vector"):
                value = payload.get(key)
                if value is not None:
                    if hasattr(value, "cpu"):
                        value = value.cpu().numpy()
                    return np.asarray(value, dtype=np.float32).flatten()
        return None

    def _embedding(self, asset: AudioAsset) -> np.ndarray:
        import librosa
        import soundfile as sf

        suffix = Path(asset.path).suffix.lower()
        if suffix == ".wav":
            audio, sample_rate = sf.read(asset.path, dtype="float32", always_2d=False)
            if getattr(audio, "ndim", 1) > 1:
                audio = audio.mean(axis=1)
        else:
            audio, sample_rate = librosa.load(asset.path, sr=None, mono=True)
        if sample_rate != asset.sample_rate:
            audio = librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sample_rate, target_sr=asset.sample_rate)
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0:
            return np.zeros(8, dtype=np.float32)
        frame = max(asset.sample_rate, 1)
        usable = audio[: (audio.size // frame) * frame] if audio.size >= frame else audio
        if usable.size >= frame:
            chunks = usable.reshape(-1, frame)
            energy = np.sqrt(np.mean(np.square(chunks), axis=1))
        else:
            energy = np.array([np.sqrt(np.mean(np.square(audio)))], dtype=np.float32)
        centroid = np.abs(np.fft.rfft(audio[: min(audio.size, asset.sample_rate * 3)])).astype(np.float32)
        fallback = np.array([
            float(np.mean(audio)),
            float(np.std(audio)),
            float(np.max(np.abs(audio))),
            float(np.mean(energy)),
            float(np.std(energy)),
            float(np.percentile(energy, 90)),
            float(np.mean(centroid[: max(1, centroid.size // 8)])),
            float(np.mean(centroid[max(1, centroid.size // 8): max(2, centroid.size // 4)])) if centroid.size > 2 else 0.0,
        ], dtype=np.float32)
        norm = np.linalg.norm(fallback)
        return fallback if norm == 0 else fallback / norm

    def _similarity(self, left: np.ndarray, right: np.ndarray) -> float:
        score = float(np.clip(np.dot(left, right), -1.0, 1.0))
        return round((score + 1.0) / 2.0, 3)


def _has_model_artifacts(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.exists():
        return False
    if candidate.is_file():
        return candidate.name != ".gitkeep"
    return any(item.is_file() and item.name != ".gitkeep" for item in candidate.rglob("*"))


def _normalize_audio_for_sv(source_path: str | Path, target_path: Path, sample_rate: int = 16000) -> str:
    import librosa
    import soundfile as sf

    source = Path(source_path)
    try:
        audio, sr = sf.read(source, dtype="float32", always_2d=False)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        audio = np.asarray(audio, dtype=np.float32)
    except Exception:
        audio, sr = librosa.load(str(source), sr=None, mono=True)
        audio = np.asarray(audio, dtype=np.float32)
    if sr != sample_rate:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=sample_rate)
    sf.write(target_path, audio, sample_rate)
    return str(target_path)


def _find_reference_3dspeaker_root() -> Path | None:
    candidates = [
        Path("F:/1work/音频识别/3D-Speaker"),
        Path(__file__).resolve().parents[5].parent / "3D-Speaker",
    ]
    for candidate in candidates:
        if (candidate / "speakerlab").exists():
            return candidate
    return None


def _clear_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return
