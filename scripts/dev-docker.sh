#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT/infra/compose/docker-compose.yml"

echo "Starting Docker Compose stack..."
echo "Compose file: $COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d --build "$@"

starts_all=true
starts_api=false
starts_worker=false
starts_web=false
starts_minio=false

if [ "$#" -gt 0 ]; then
  starts_all=false
  for service in "$@"; do
    service_lower="$(printf '%s' "$service" | tr '[:upper:]' '[:lower:]')"
    case "$service_lower" in
      api) starts_api=true ;;
      worker) starts_worker=true ;;
      web) starts_web=true ;;
      minio) starts_minio=true ;;
    esac
  done
fi

if [ "$starts_all" = true ]; then
  starts_api=true
  starts_worker=true
  starts_web=true
  starts_minio=true
fi

if [ "$starts_api" = true ] || [ "$starts_worker" = true ]; then
  starts_minio=true
fi

cat <<EOF
Services are starting. Useful URLs:
EOF

if [ "$starts_api" = true ]; then
  echo "  API health:    http://127.0.0.1:8000/api/v1/health"
fi

if [ "$starts_web" = true ]; then
  echo "  Web:           http://127.0.0.1:5173"
else
  echo "  Web:           not requested. Start it with: ./scripts/dev-docker.sh web"
fi

if [ "$starts_minio" = true ]; then
  echo "  MinIO console: http://127.0.0.1:9001"
fi

if [ "$starts_api" = true ] || [ "$starts_worker" = true ]; then
  cat <<EOF

Follow API/worker logs:
  docker compose -f infra/compose/docker-compose.yml logs -f api worker
EOF
fi
