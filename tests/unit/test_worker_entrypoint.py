from apps.worker.app import worker


def test_worker_entrypoint_defaults_to_solo_pool_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(worker.sys, "platform", "win32")
    monkeypatch.delenv("CELERY_WORKER_POOL", raising=False)
    monkeypatch.delenv("CELERY_WORKER_CONCURRENCY", raising=False)

    args = worker.build_worker_main_args()

    assert "--pool=solo" in args
    assert "--concurrency=1" in args


def test_worker_entrypoint_respects_explicit_pool(monkeypatch) -> None:
    monkeypatch.setattr(worker.sys, "platform", "win32")
    monkeypatch.setenv("CELERY_WORKER_POOL", "threads")
    monkeypatch.setenv("CELERY_WORKER_CONCURRENCY", "2")

    args = worker.build_worker_main_args()

    assert "--pool=threads" in args
    assert "--concurrency=2" in args
