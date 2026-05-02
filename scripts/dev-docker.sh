#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT/infra/compose/docker-compose.yml"

echo "Starting Docker Compose stack..."
echo "Compose file: $COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d --build "$@"

cat <<EOF

Services are starting. Useful URLs:
  API health:    http://127.0.0.1:8000/api/v1/health
  Web:           http://127.0.0.1:5173
  MinIO console: http://127.0.0.1:9001

Follow API/worker logs:
  docker compose -f infra/compose/docker-compose.yml logs -f api worker
EOF
