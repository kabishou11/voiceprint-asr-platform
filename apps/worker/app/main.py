from .worker_runtime import get_worker


def run() -> list[str]:
    worker = get_worker()
    capabilities = worker.describe_capabilities()
    for capability in capabilities:
        print(capability)
    return capabilities


if __name__ == "__main__":
    run()
