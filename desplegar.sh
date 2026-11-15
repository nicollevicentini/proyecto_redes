#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(id -u)" -ne 0 ]; then echo 'Ejecuta: sudo bash desplegar.sh' >&2; exit 1; fi
for sw in sw-a sw-b; do
  ip link show "$sw" >/dev/null 2>&1 || ip link add "$sw" type bridge
  ip link set "$sw" up
done
containerlab deploy -t netlab.clab.yml
# Esperar a que FRRouting y nginx arranquen.
sleep 5
bash config-vlans.sh
bash config-ip.sh
bash config-ospf.sh
bash config-nat.sh
bash config-servicios.sh
sleep 10
echo '=== Vecinos OSPF de R1 ==='
docker exec clab-netlab-g2-r1 vtysh -c 'show ip ospf neighbor'
echo '=== HTTP ==='
docker exec clab-netlab-g2-pc-admin curl -s -o /dev/null -w 'HTTP: %{http_code}\n' http://172.16.2.50
echo '=== TCP 5000 ==='
docker exec clab-netlab-g2-pc-admin nc -zv -w 2 172.16.2.51 5000
echo '=== Salida externa ==='
docker exec clab-netlab-g2-pc-admin ping -c 2 203.0.113.2
echo 'Despliegue y comprobaciones finalizados.'
