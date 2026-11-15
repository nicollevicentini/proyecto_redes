#!/usr/bin/env bash
set -euo pipefail
P=clab-netlab-g2
net() {
  local pid
  pid=$(docker inspect -f '{{.State.Pid}}' "$P-$1")
  shift
  nsenter -t "$pid" -n "$@"
}
for r in r1 r2 r3; do net "$r" sysctl -w net.ipv4.ip_forward=1; done
# Regla solo hacia la interfaz externa de R1; evita duplicados.
if ! net r1 iptables -t nat -C POSTROUTING -s 172.16.2.0/24 -o eth4 -j MASQUERADE 2>/dev/null; then
  net r1 iptables -t nat -A POSTROUTING -s 172.16.2.0/24 -o eth4 -j MASQUERADE
fi
net r1 iptables -t nat -L POSTROUTING -n -v
