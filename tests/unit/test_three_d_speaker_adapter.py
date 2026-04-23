import numpy as np
import torch

from model_adapters.three_d_speaker_adapter import ThreeDSpeakerDiarizationAdapter


def test_smoothing_preserves_expected_speaker_count_when_exact_count_is_known():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.num_speakers = 2

    segments = [
        (0, 400, 0),
        (400, 3200, 1),
    ]

    smoothed = adapter._smooth_segments(segments)

    assert len({speaker for _, _, speaker in smoothed}) == 2
    assert smoothed[0][2] == 0
    assert smoothed[1][2] == 1


def test_smoothing_merges_smallest_speaker_when_above_max_count():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.max_speakers = 2

    segments = [
        (0, 2200, 0),
        (2200, 2600, 2),
        (2600, 5200, 1),
    ]

    smoothed = adapter._smooth_segments(segments)

    assert len({speaker for _, _, speaker in smoothed}) == 2
    assert smoothed == [(0, 2200, 0), (2200, 5200, 1)]


def test_extract_embeddings_batches_wave_chunks_for_low_vram_mode():
    class DummyFeatureExtractor:
        def __call__(self, wave):
            return wave.mean(dim=-1, keepdim=True)

    class DummyEmbeddingModel:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, features):
            self.calls += 1
            return torch.ones((features.shape[0], 2), device=features.device)

    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter._device = "cpu"
    adapter.embedding_batch_size = 2
    dummy_model = DummyEmbeddingModel()
    adapter._ensure_reference_embedding_runtime = lambda: (dummy_model, DummyFeatureExtractor())

    audio = np.zeros(5 * 16000, dtype=np.float32)
    chunk_list = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0)]

    embeddings = adapter._extract_embeddings(audio, chunk_list, 16000)

    assert embeddings.shape == (5, 2)
    assert dummy_model.calls == 3


def test_cluster_embeddings_uses_ahc_path_for_short_sequences():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.cluster_line = 40
    adapter.min_cluster_size = 0
    adapter.num_speakers = None
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.98, 0.02],
            [0.0, 1.0],
            [0.02, 0.98],
        ],
        dtype=np.float32,
    )

    labels = adapter._cluster_embeddings(embeddings)

    assert len(np.unique(labels)) == 2
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]


def test_cluster_embeddings_merges_minor_clusters_by_cosine_center():
    adapter = ThreeDSpeakerDiarizationAdapter()
    labels = np.array([0, 0, 0, 0, 0, 1], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.98, 0.02],
            [1.0, 0.0],
            [0.99, 0.01],
            [0.97, 0.03],
        ],
        dtype=np.float32,
    )

    merged = adapter._merge_minor_clusters(labels, embeddings, min_cluster_size=4)

    assert np.all(merged == 0)


def test_merge_minor_clusters_collapses_all_minor_case_to_single_speaker():
    adapter = ThreeDSpeakerDiarizationAdapter()
    labels = np.array([0, 1, 2], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [-1.0, 0.0],
        ],
        dtype=np.float32,
    )

    merged = adapter._merge_minor_clusters(labels, embeddings, min_cluster_size=4)

    assert np.all(merged == 0)


def test_smoothing_merges_tiny_tail_speaker_in_long_session_without_explicit_bounds():
    adapter = ThreeDSpeakerDiarizationAdapter()
    segments = [
        (0, 600000, 0),
        (600000, 1200000, 1),
        (1200000, 1800000, 2),
        (1800000, 2400000, 3),
        (2400000, 2415000, 4),
        (2415000, 2430000, 0),
    ]

    smoothed = adapter._smooth_segments(segments)

    assert len({speaker for _, _, speaker in smoothed}) == 4
    assert all(speaker != 4 for _, _, speaker in smoothed)


def test_refine_tail_labels_merges_short_tail_cluster_to_adjacent_similar_speaker():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 30.0),
        (30.0, 60.0),
        (60.0, 90.0),
        (90.0, 120.0),
        (120.0, 150.0),
        (150.0, 180.0),
        (180.0, 210.0),
        (210.0, 240.0),
        (240.0, 250.0),
    ]
    labels = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
            [0.02, 0.98],
            [0.0, -1.0],
            [0.01, -0.99],
            [-1.0, 0.0],
            [-0.99, 0.01],
            [-0.98, 0.02],
        ],
        dtype=np.float32,
    )

    refined = adapter._refine_tail_labels(chunk_list, labels, embeddings)

    assert len(np.unique(refined)) == 4


def test_reassign_local_label_noise_merges_short_isolated_run_between_same_neighbors():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 1.5),
        (1.5, 3.0),
        (3.0, 4.5),
        (4.5, 6.0),
        (6.0, 7.5),
    ]
    labels = np.array([0, 0, 1, 0, 0], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.98, 0.02],
            [0.96, 0.04],
            [0.99, 0.01],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )

    refined = adapter._reassign_local_label_noise(chunk_list, labels, embeddings)

    assert np.all(refined == 0)


def test_reassign_local_label_noise_merges_tiny_global_weak_run_to_single_neighbor():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 1.5),
        (1.5, 3.0),
        (3.0, 4.2),
        (4.2, 5.7),
        (5.7, 7.2),
    ]
    labels = np.array([0, 0, 1, 0, 0], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.97, 0.03],
            [1.0, 0.0],
            [0.98, 0.02],
        ],
        dtype=np.float32,
    )

    refined = adapter._reassign_local_label_noise(chunk_list, labels, embeddings)

    assert np.all(refined == 0)


def test_decode_framewise_segments_prefers_temporally_consistent_speaker():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.frame_decode_step_s = 0.5
    chunk_list = [
        (0.0, 1.5),
        (0.75, 2.25),
        (1.5, 3.0),
    ]
    labels = np.array([0, 1, 0], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.96, 0.04],
            [0.99, 0.01],
        ],
        dtype=np.float32,
    )
    vad_segments = [[0.0, 3.0]]

    decoded = adapter._decode_framewise_segments(chunk_list, labels, embeddings, vad_segments)

    assert decoded[0][2] == 0
    assert all(speaker == 0 for _, _, speaker in decoded)


def test_decode_framewise_segments_repairs_single_frame_bridge_after_vote_decode():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.frame_decode_step_s = 0.25
    frame_items = [
        (0.0, 0.25, 0),
        (0.25, 0.5, 0),
        (0.5, 0.75, 1),
        (0.75, 1.0, 0),
        (1.0, 1.25, 0),
    ]

    repaired = adapter._repair_frame_sequence(frame_items, adapter.frame_decode_step_s)

    assert all(speaker == 0 for _, _, speaker in repaired)


def test_estimate_frame_speaker_count_keeps_single_speaker_when_secondary_vote_is_weak():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 1.5),
        (0.0, 0.18),
    ]
    labels = np.array([0, 1], dtype=int)

    count = adapter._estimate_frame_speaker_count(
        [0, 1],
        chunk_list,
        labels,
        0.0,
        0.5,
    )

    assert count == 1


def test_reassign_frame_runs_absorbs_short_bridge_with_matching_neighbors():
    adapter = ThreeDSpeakerDiarizationAdapter()
    frame_items = [
        (0.0, 0.25, 0),
        (0.25, 0.5, 0),
        (0.5, 0.75, 1),
        (0.75, 1.0, 1),
        (1.0, 1.25, 0),
        (1.25, 1.5, 0),
    ]
    chunk_list = [
        (0.0, 0.75),
        (0.5, 1.25),
        (0.75, 1.5),
    ]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.995, 0.005],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )
    centers = {
        0: np.array([1.0, 0.0], dtype=np.float32),
        1: np.array([0.0, 1.0], dtype=np.float32),
    }

    reassigned = adapter._reassign_frame_runs(frame_items, chunk_list, embeddings, centers)

    assert all(speaker == 0 for _, _, speaker in reassigned)


def test_reassign_frame_runs_keeps_long_non_bridge_run():
    adapter = ThreeDSpeakerDiarizationAdapter()
    adapter.frame_run_reassign_max_s = 1.0
    frame_items = [
        (0.0, 0.5, 0),
        (0.5, 1.0, 1),
        (1.0, 1.5, 1),
        (1.5, 2.0, 1),
        (2.0, 2.5, 0),
    ]
    chunk_list = [
        (0.0, 1.0),
        (0.5, 2.0),
        (1.5, 2.5),
    ]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.1, 0.99],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )
    centers = {
        0: np.array([1.0, 0.0], dtype=np.float32),
        1: np.array([0.0, 1.0], dtype=np.float32),
    }

    reassigned = adapter._reassign_frame_runs(frame_items, chunk_list, embeddings, centers)

    assert [speaker for _, _, speaker in reassigned] == [0, 1, 1, 1, 0]


def test_reassign_chunk_label_runs_absorbs_short_bridge_cluster_run():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 1.5),
        (0.75, 2.25),
        (1.5, 3.0),
    ]
    labels = np.array([0, 1, 0], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.99, 0.01],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )

    refined = adapter._reassign_chunk_label_runs(chunk_list, labels, embeddings)

    assert np.all(refined == 0)


def test_reassign_chunk_label_runs_keeps_stable_middle_speaker_when_embedding_matches():
    adapter = ThreeDSpeakerDiarizationAdapter()
    chunk_list = [
        (0.0, 1.5),
        (0.75, 2.25),
        (1.5, 3.0),
    ]
    labels = np.array([0, 1, 0], dtype=int)
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )

    refined = adapter._reassign_chunk_label_runs(chunk_list, labels, embeddings)

    assert np.array_equal(refined, labels)
