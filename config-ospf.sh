#!/usr/bin/env bash
set -euo pipefail
P=clab-netlab-g2
for n in 1 2 3; do
  case "$n" in
    1) a=eth2; b=eth3 ;;
    2) a=eth2; b=eth3 ;;
    3) a=eth1; b=eth2 ;;
  esac
  docker exec "$P-r$n" vtysh \
    -c 'configure terminal' \
    -c 'router ospf' \
    -c "ospf router-id $n.$n.$n.$n" \
    -c 'network 172.16.2.0/24 area 0' \
    -c 'passive-interface default' \
    -c "no passive-interface $a" \
    -c "no passive-interface $b" \
    -c 'end' -c 'write memory'
done
# R1 anuncia la red externa, sin buscar vecinos en ella.
docker exec "$P-r1" vtysh -c 'configure terminal' \
  -c 'router ospf' -c 'network 203.0.113.0/29 area 0' \
  -c 'end' -c 'write memory'
echo 'OSPF configurado; esperar unos segundos para vecindades FULL.'
