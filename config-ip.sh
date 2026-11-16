#!/usr/bin/env bash
set -euo pipefail
P=clab-netlab-g2
# Ejecuta herramientas del host dentro de la red del contenedor.
# Evita depender de iproute2 dentro de nginx:alpine.
net() {
  local nodo="$1"; shift
  local pid
  pid=$(docker inspect -f '{{.State.Pid}}' "$P-$nodo")
  if [ "$pid" -le 0 ]; then echo "No esta ejecutandose: $P-$nodo" >&2; exit 1; fi
  nsenter -t "$pid" -n "$@"
}
# VLANs de R2 (idempotente)
net r2 ip link set eth1 up
net r2 ip link show eth1.10 >/dev/null 2>&1 || net r2 ip link add link eth1 name eth1.10 type vlan id 10
net r2 ip link show eth1.20 >/dev/null 2>&1 || net r2 ip link add link eth1 name eth1.20 type vlan id 20
net r2 ip addr replace 172.16.2.1/27 dev eth1.10
net r2 ip addr replace 172.16.2.33/28 dev eth1.20
net r2 ip link set eth1.10 up
net r2 ip link set eth1.20 up
# Redes LAN y WAN
net r1 ip addr replace 172.16.2.49/29 dev eth1
net r1 ip addr replace 172.16.2.57/30 dev eth2
net r2 ip addr replace 172.16.2.58/30 dev eth2
net r2 ip addr replace 172.16.2.61/30 dev eth3
net r3 ip addr replace 172.16.2.62/30 dev eth1
net r1 ip addr replace 172.16.2.65/30 dev eth3
net r3 ip addr replace 172.16.2.66/30 dev eth2
net r1 ip addr replace 203.0.113.1/29 dev eth4
# Hosts y gateways
net pc-admin ip addr replace 172.16.2.2/27 dev eth1
net pc-admin ip route replace default via 172.16.2.1 dev eth1
net pc-ventas ip addr replace 172.16.2.34/28 dev eth1
net pc-ventas ip route replace default via 172.16.2.33 dev eth1
net srv-web ip addr replace 172.16.2.50/29 dev eth1
net srv-web ip route replace default via 172.16.2.49 dev eth1
net srv-datos ip addr replace 172.16.2.51/29 dev eth1
net srv-datos ip route replace default via 172.16.2.49 dev eth1
net srv-extra ip addr replace 172.16.2.52/29 dev eth1
net srv-extra ip route replace default via 172.16.2.49 dev eth1
net externo ip addr replace 203.0.113.2/29 dev eth1
net externo ip route replace default via 203.0.113.1 dev eth1
# Habilitar interfaces por seguridad
for iface in eth1 eth2 eth3 eth4; do net r1 ip link set "$iface" up; done
for iface in eth1 eth2 eth3; do net r2 ip link set "$iface" up; done
for iface in eth1 eth2; do net r3 ip link set "$iface" up; done
for nodo in pc-admin pc-ventas srv-web srv-datos srv-extra externo; do net "$nodo" ip link set eth1 up; done
echo 'Direcciones IP configuradas.'
