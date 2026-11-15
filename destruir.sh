#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(id -u)" -ne 0 ]; then echo 'Ejecuta: sudo bash destruir.sh' >&2; exit 1; fi
echo 'ATENCION: esto elimina los contenedores del laboratorio Grupo 2.'
echo 'Los archivos docs/ y evidencias/ no se borran.'
read -r -p 'Escribe SI para continuar: ' respuesta
[ "$respuesta" = SI ] || { echo 'Cancelado'; exit 0; }
containerlab destroy -t netlab.clab.yml
for sw in sw-a sw-b; do ip link show "$sw" >/dev/null 2>&1 && ip link del "$sw" || true; done
echo 'Laboratorio Grupo 2 detenido y bridges eliminados.'
