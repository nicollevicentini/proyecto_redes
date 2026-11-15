#!/usr/bin/env bash
set -euo pipefail
P=clab-netlab-g2
# nginx:alpine inicia HTTP por defecto.
# OpenBSD netcat, servicio TCP 5000; evita levantar otro proceso si ya escucha.
if ! docker exec "$P-srv-datos" sh -c "ss -ltn | grep -q ':5000'"; then
  docker exec -d "$P-srv-datos" nc -l -k 5000
fi
docker exec "$P-srv-datos" ss -ltn
