#!/usr/bin/env bash
set -euo pipefail
# VLAN 10 Administracion; VLAN 20 Ventas. SW-A: a1 trunk, a2/a3 access.
for p in a1 a2 a3; do ip link show dev "$p" >/dev/null; done
bridge vlan add dev a1 vid 10 2>/dev/null || true
bridge vlan add dev a1 vid 20 2>/dev/null || true
bridge vlan add dev a2 vid 10 pvid untagged 2>/dev/null || true
bridge vlan add dev a3 vid 20 pvid untagged 2>/dev/null || true
for p in a1 a2 a3; do bridge vlan del dev "$p" vid 1 2>/dev/null || true; done
ip link set sw-a type bridge vlan_filtering 1
bridge vlan show dev a1
bridge vlan show dev a2
bridge vlan show dev a3
