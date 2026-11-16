#!/usr/bin/env bash
set -euo pipefail
P=clab-netlab-g2
# nginx:alpine inicia HTTP por defecto.
# OpenBSD netcat, servicio TCP 5000; evita levantar otro proceso si ya escucha.
if ! docker exec "$P-srv-datos" sh -c "ss -ltn | grep -q ':5000'"; then
  docker exec -d "$P-srv-datos" nc -l -k 5000
fi
docker exec "$P-srv-datos" ss -ltn

# Cambio B Grupo 2: servidor adicional TCP 6000
if ! docker exec "$P-srv-extra" sh -c "ss -ltn | grep -q ':6000'"; then
  docker exec -d "$P-srv-extra" nc -l -k 6000
fi
docker exec "$P-srv-extra" ss -ltn
