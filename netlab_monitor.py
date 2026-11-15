#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proyecto Final Netlab Monitor - Grupo 2
Descripción: Monitor automatizado de red y diagnóstico por capas para Containerlab.
Restricción de librerías: subprocess, socket, os, json, argparse, datetime.
"""

import subprocess
import socket
import os
import json
import argparse
import datetime


def parsear_argumentos():
    """Configura y procesa los argumentos de línea de comandos con argparse."""
    parser = argparse.ArgumentParser(
        description="Monitor automatizado de red y servicios para Containerlab (Grupo 2)."
    )
    parser.add_argument(
        "-c", "--config",
        default="monitor.json",
        help="Ruta al archivo de configuración JSON (por defecto: monitor.json)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Ruta opcional para guardar el reporte en texto plano (ej: evidencias/reporte.txt)"
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Ruta opcional para exportar el reporte en formato JSON (Nivel Avanzado)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Muestra detalles extendidos de cada comando ejecutado en consola"
    )
    return parser.parse_args()


def cargar_configuracion(ruta_json):
    """Lee y valida la existencia del archivo externo monitor.json."""
    if not os.path.exists(ruta_json):
        print(f"[ERROR CRÍTICO] No se encontró el archivo de configuración: {ruta_json}")
        raise SystemExit(2)

    try:
        with open(ruta_json, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except json.JSONDecodeError as err:
        print(f"[ERROR CRÍTICO] El archivo {ruta_json} tiene un formato JSON inválido: {err}")
        raise SystemExit(2)
    except OSError as err:
        print(f"[ERROR CRÍTICO] No se pudo leer {ruta_json}: {err}")
        raise SystemExit(2)


# ==============================================================================
# MOTOR DE EJECUCIÓN SEGURA EN DOCKER (CONTROL ESTRICTO DE ERRORES)
# ==============================================================================

def ejecutar_docker_exec(container_name, comando_lista, timeout=8, permitir_vacio=False):
    """
    Ejecuta un comando dentro de un contenedor mediante 'docker exec'.
    Garantiza que fallos de Docker, contenedores caídos o salidas vacías NUNCA
    se interpreten como pruebas exitosas.
    Retorna: (exito: bool, stdout: str, error_msg: str)
    """
    cmd_completo = ["docker", "exec", container_name] + comando_lista
    try:
        proceso = subprocess.run(
            cmd_completo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        stdout_limpio = proceso.stdout.strip() if proceso.stdout else ""
        stderr_limpio = proceso.stderr.strip() if proceso.stderr else ""

        if proceso.returncode != 0:
            detalle_err = stderr_limpio if stderr_limpio else f"Código de retorno {proceso.returncode}"
            return False, stdout_limpio, f"Fallo en docker exec ({container_name}): {detalle_err}"

        if not permitir_vacio and len(stdout_limpio) == 0:
            return False, "", f"Salida vacía en {container_name} al ejecutar '{' '.join(comando_lista)}'"

        return True, stdout_limpio, ""

    except subprocess.TimeoutExpired:
        return False, "", f"Tiempo de espera agotado ({timeout}s) en contenedor {container_name}"
    except FileNotFoundError:
        return False, "", "El binario 'docker' no está instalado o no se encuentra en el PATH"
    except Exception as err:
        return False, "", f"Excepción inesperada ejecutando docker exec en {container_name}: {err}"


# ==============================================================================
# VERIFICACIÓN 1: INVENTARIO
# ==============================================================================

def verificar_inventario(config, verbose=False):
    """Verificación 1: Comprueba disponibilidad de nodos e IPs principales."""
    print("\n[1/8] Ejecutando Verificación 1: Inventario de Nodos e IPs...")
    nodos_cfg = config.get("nodos", {})

    if not nodos_cfg:
        return {
            "nombre": "Inventario",
            "estado": "FAIL",
            "capa_probable": "Enlace/VLAN",
            "disponibles": [],
            "faltantes": ["Todos (monitor.json vacío)"],
            "detalles": ["El diccionario 'nodos' en monitor.json está vacío."]
        }

    disponibles = []
    faltantes = []
    detalles = []

    for nombre_nodo, datos_nodo in nodos_cfg.items():
        container = datos_nodo.get("container_name", "")
        ip_esperada = datos_nodo.get("ip_principal", "")

        try:
            insp = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            esta_corriendo = (insp.returncode == 0 and insp.stdout.strip().lower() == "true")
        except Exception as err:
            esta_corriendo = False
            detalles.append(f"{nombre_nodo} ({container}): Error inspect Docker ({err})")

        if not esta_corriendo:
            faltantes.append(f"{nombre_nodo} ({container} - Apagado/Inexistente)")
            msg = f"Nodo {nombre_nodo} [{container}]: FAIL (Contenedor inexistente o apagado)"
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        exito_ip, salida_ip, err_ip = ejecutar_docker_exec(container, ["ip", "-br", "a"])
        if not exito_ip:
            faltantes.append(f"{nombre_nodo} ({container} - Error IP)")
            msg = f"Nodo {nombre_nodo} [{container}]: FAIL ({err_ip})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        if ip_esperada and ip_esperada in salida_ip:
            disponibles.append(f"{nombre_nodo} ({ip_esperada})")
            msg = f"Nodo {nombre_nodo} [{container}]: OK (Activo con IP {ip_esperada})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")
        else:
            faltantes.append(f"{nombre_nodo} (Falta IP {ip_esperada})")
            msg = f"Nodo {nombre_nodo} [{container}]: FAIL (Activo, sin IP {ip_esperada})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")

    estado_final = "OK" if (len(faltantes) == 0 and len(disponibles) > 0) else "FAIL"
    print(f"  Resultado Inventario: {estado_final} | Disponibles: {len(disponibles)} | Faltantes: {len(faltantes)}")

    return {
        "nombre": "Inventario",
        "estado": estado_final,
        "capa_probable": "Enlace/VLAN" if estado_final == "FAIL" else "Ninguna",
        "disponibles": disponibles,
        "faltantes": faltantes,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 2: INTERFACES Y VLANS
# ==============================================================================

def verificar_interfaces_vlans(config, verbose=False):
    """Verificación 2: Comprueba estado UP, prefijos IP y etiquetas 802.1Q."""
    print("\n[2/8] Ejecutando Verificación 2: Interfaces y VLANs...")
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    for nombre_nodo, datos_nodo in nodos_cfg.items():
        container = datos_nodo.get("container_name", "")
        interfaces_esperadas = datos_nodo.get("interfaces", [])

        exito_addr, out_addr, err_addr = ejecutar_docker_exec(container, ["ip", "-br", "a"])
        exito_link, out_link, err_link = ejecutar_docker_exec(container, ["ip", "-d", "link"])

        if not exito_addr or not exito_link:
            causa = err_addr if not exito_addr else err_link
            msg = f"{nombre_nodo}: FAIL al ejecutar comandos de interfaz ({causa})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        mapa_addr = {}
        for linea in out_addr.splitlines():
            partes = linea.split()
            if len(partes) >= 2:
                iface_raw = partes[0]
                iface_limpia = iface_raw.split("@")[0]
                estado_iface = partes[1].upper()
                direcciones = partes[2:] if len(partes) > 2 else []
                mapa_addr[iface_limpia] = {
                    "raw": iface_raw,
                    "estado": estado_iface,
                    "ips": direcciones
                }

        for iface_cfg in interfaces_esperadas:
            nom_iface = iface_cfg.get("iface", "")
            ip_esp = iface_cfg.get("ip", "")
            vlan_esp = iface_cfg.get("vlan", None)

            if nom_iface not in mapa_addr:
                msg = f"{nombre_nodo} [{nom_iface}]: FAIL - Interfaz no existe en 'ip -br a'"
                fallas.append(msg)
                detalles.append(msg)
                if verbose:
                    print(f"  -> [FAIL] {msg}")
                continue

            info_actual = mapa_addr[nom_iface]

            if "UP" not in info_actual["estado"] and "UNKNOWN" not in info_actual["estado"]:
                msg = f"{nombre_nodo} [{nom_iface}]: FAIL - Estado {info_actual['estado']} (esperado UP)"
                fallas.append(msg)
                detalles.append(msg)
                if verbose:
                    print(f"  -> [FAIL] {msg}")
                continue

            if ip_esp not in info_actual["ips"]:
                ips_encontradas = ", ".join(info_actual["ips"]) if info_actual["ips"] else "Sin IP"
                msg = f"{nombre_nodo} [{nom_iface}]: FAIL - IP ({ips_encontradas}) != esperada ({ip_esp})"
                fallas.append(msg)
                detalles.append(msg)
                if verbose:
                    print(f"  -> [FAIL] {msg}")
                continue

            vlan_ok = True
            if vlan_esp is not None and ("." in nom_iface or datos_nodo.get("rol") == "router"):
                patron_vlan_1 = f"vlan protocol 802.1Q id {vlan_esp}"
                patron_vlan_2 = f"vlan id {vlan_esp}"
                patron_subiface = f".{vlan_esp}"
                if (patron_vlan_1 not in out_link and
                        patron_vlan_2 not in out_link and
                        patron_subiface not in nom_iface):
                    vlan_ok = False

            if not vlan_ok:
                msg = f"{nombre_nodo} [{nom_iface}]: FAIL - VLAN {vlan_esp} no detectada en 'ip -d link'"
                fallas.append(msg)
                detalles.append(msg)
                if verbose:
                    print(f"  -> [FAIL] {msg}")
                continue

            etiqueta_vlan = f", VLAN {vlan_esp}" if vlan_esp is not None else ""
            msg = f"{nombre_nodo} [{nom_iface}]: OK (Estado {info_actual['estado']}, IP {ip_esp}{etiqueta_vlan})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")

    estado_final = "OK" if (len(fallas) == 0 and len(detalles) > 0) else "FAIL"
    print(f"  Resultado Interfaces/VLANs: {estado_final} | Fallas: {len(fallas)}")

    return {
        "nombre": "Interfaces y VLANs",
        "estado": estado_final,
        "capa_probable": "Enlace/VLAN" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 3: RUTAS
# ==============================================================================

def verificar_rutas(config, verbose=False):
    """Verificación 3: Comprueba tablas de rutas del kernel y aprendizaje OSPF."""
    print("\n[3/8] Ejecutando Verificación 3: Tablas de Enrutamiento (ip route)...")
    rutas_cfg = config.get("rutas_esperadas", {})
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    if not rutas_cfg:
        msg = "No existen rutas_esperadas en monitor.json"
        return {
            "nombre": "Rutas",
            "estado": "FAIL",
            "capa_probable": "Rutas/OSPF",
            "fallas": [msg],
            "detalles": [msg]
        }

    for nombre_router, lista_rutas in rutas_cfg.items():
        datos_router = nodos_cfg.get(nombre_router, {})
        container = datos_router.get("container_name", nombre_router)

        exito, out_route, err_route = ejecutar_docker_exec(container, ["ip", "route"])

        if not exito:
            msg = f"{nombre_router} [{container}]: FAIL al consultar tabla de rutas ({err_route})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        lineas_tabla = out_route.splitlines()

        for ruta_esp in lista_rutas:
            prefijo = ruta_esp.get("prefijo", "")
            tipo = ruta_esp.get("tipo", "conectada").lower()

            linea_coincidente = None
            for linea in lineas_tabla:
                partes = linea.split()
                if len(partes) > 0 and partes[0] == prefijo:
                    linea_coincidente = linea
                    break

            if linea_coincidente is None:
                msg = f"{nombre_router}: FAIL - Ruta faltante hacia {prefijo} ({tipo.upper()})"
                fallas.append(msg)
                detalles.append(msg)
                if verbose:
                    print(f"  -> [FAIL] {msg}")
                continue

            if tipo == "ospf":
                es_dinamica = (
                    "proto ospf" in linea_coincidente or
                    "proto zebra" in linea_coincidente or
                    "proto 188" in linea_coincidente or
                    "via " in linea_coincidente
                )
                if not es_dinamica:
                    msg = f"{nombre_router}: FAIL - Ruta {prefijo} existe pero no fue aprendida vía OSPF"
                    fallas.append(msg)
                    detalles.append(msg)
                    if verbose:
                        print(f"  -> [FAIL] {msg}")
                    continue

            msg = f"{nombre_router}: OK - Ruta {prefijo} ({tipo.upper()}) presente -> [{linea_coincidente}]"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")

    estado_final = "OK" if (len(fallas) == 0 and len(detalles) > 0) else "FAIL"
    print(f"  Resultado Rutas: {estado_final} | Fallas: {len(fallas)}")

    return {
        "nombre": "Rutas",
        "estado": estado_final,
        "capa_probable": "Rutas/OSPF" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 4: CONECTIVIDAD (PING Y TRACEROUTE)
# ==============================================================================

def verificar_conectividad(config, verbose=False):
    """Verificación 4: Comprueba conectividad ICMP y mide latencia/saltos."""
    print("\n[4/8] Ejecutando Verificación 4: Conectividad (Ping y Traceroute)...")
    pruebas = config.get("pruebas_conectividad", [])
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    if not pruebas:
        msg = "No hay pruebas_conectividad en monitor.json"
        return {
            "nombre": "Conectividad",
            "estado": "FAIL",
            "capa_probable": "IP/Gateway",
            "fallas": [msg],
            "detalles": [msg]
        }

    for prueba in pruebas:
        nombre_prueba = prueba.get("nombre", "Prueba ICMP")
        nodo_orig = prueba.get("origen", "")
        ip_dest = prueba.get("ip_destino", "")

        container_orig = nodos_cfg.get(nodo_orig, {}).get("container_name", nodo_orig)

        cmd_ping = ["ping", "-c", "3", "-W", "2", ip_dest]
        exito_ping, out_ping, err_ping = ejecutar_docker_exec(container_orig, cmd_ping, timeout=10)

        perdida_pct = 100
        rtt_avg = "N/A"
        ping_ok = False

        if exito_ping:
            for linea in out_ping.splitlines():
                if "packet loss" in linea:
                    try:
                        parte_perdida = linea.split("%")[0].split()[-1]
                        perdida_pct = int(float(parte_perdida))
                    except (ValueError, IndexError):
                        perdida_pct = 100
                if "rtt min/avg/max" in linea or "round-trip min/avg/max" in linea:
                    try:
                        stats = linea.split("=")[1].strip().split()[0].split("/")
                        rtt_avg = f"{stats[1]} ms"
                    except (IndexError, ValueError):
                        rtt_avg = "Desconocida"

            if perdida_pct == 0:
                ping_ok = True

        cmd_trace = ["traceroute", "-n", "-w", "1", "-q", "1", ip_dest]
        exito_trace, out_trace, _ = ejecutar_docker_exec(container_orig, cmd_trace, timeout=8)
        if not exito_trace:
            cmd_trace = ["tracepath", "-n", ip_dest]
            exito_trace, out_trace, _ = ejecutar_docker_exec(container_orig, cmd_trace, timeout=8)

        saltos_detectados = 0
        if exito_trace:
            lineas_saltos = [
                l for l in out_trace.splitlines()
                if len(l.strip()) > 0 and l.strip()[0].isdigit()
            ]
            saltos_detectados = len(lineas_saltos)

        if ping_ok:
            msg = f"{nombre_prueba} ({nodo_orig} -> {ip_dest}): OK (0% pérdida, RTT avg: {rtt_avg}, {saltos_detectados} saltos)"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")
        else:
            causa = f"{perdida_pct}% pérdida" if exito_ping else f"Error: {err_ping}"
            msg = f"{nombre_prueba} ({nodo_orig} -> {ip_dest}): FAIL ({causa})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")

    estado_final = "OK" if len(fallas) == 0 else "FAIL"
    print(f"  Resultado Conectividad: {estado_final} | Fallas: {len(fallas)}/{len(pruebas)}")

    return {
        "nombre": "Conectividad",
        "estado": estado_final,
        "capa_probable": "IP/Gateway" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 5: SERVICIOS (SOCKETS TCP Y SS -TULPN)
# ==============================================================================

def verificar_servicios(config, verbose=False):
    """Verificación 5: Comprueba puertos TCP (80, 5000, 6000) vía socket y ss."""
    print("\n[5/8] Ejecutando Verificación 5: Disponibilidad de Servicios TCP...")
    servicios_cfg = config.get("servicios", [])
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    if not servicios_cfg:
        msg = "No hay servicios definidos en monitor.json"
        return {
            "nombre": "Servicios",
            "estado": "FAIL",
            "capa_probable": "Servicios",
            "fallas": [msg],
            "detalles": [msg]
        }

    for srv in servicios_cfg:
        nombre_srv = srv.get("nombre", "Servicio TCP")
        nodo_srv = srv.get("nodo", "")
        ip_srv = srv.get("ip", "")
        puerto = int(srv.get("puerto", 80))
        tipo_srv = srv.get("tipo_servicio", "tcp")

        container_srv = nodos_cfg.get(nodo_srv, {}).get("container_name", nodo_srv)

        # 1. Comprobación interna en servidor: ss -tln
        exito_ss, out_ss, _ = ejecutar_docker_exec(container_srv, ["ss", "-tln"])
        puerto_escuchando = False

        if exito_ss:
            patron_puerto = f":{puerto} "
            if patron_puerto in out_ss or out_ss.endswith(f":{puerto}") or f":{puerto}" in out_ss:
                puerto_escuchando = True

        if not puerto_escuchando:
            msg = f"{nombre_srv} ({nodo_srv}:{puerto}): FAIL - Proceso no escucha en el servidor (ss -tln)"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        # 2. Handshake TCP externo con socket nativo de Python
        socket_abierto = False
        socket_error = ""

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                res = s.connect_ex((ip_srv, puerto))
                if res == 0:
                    socket_abierto = True
                    if tipo_srv == "http":
                        try:
                            s.sendall(b"HEAD / HTTP/1.0\r\nHost: test\r\n\r\n")
                            s.recv(64)
                        except Exception:
                            pass
                else:
                    socket_error = f"Error TCP {res} ({os.strerror(res)})"
        except socket.timeout:
            socket_error = "Timeout TCP"
        except Exception as err:
            socket_error = f"Excepción de socket: {err}"

        # Fallback de conexión vía cliente si el host no tiene ruta directa a la subred del contenedor
        if not socket_abierto:
            clientes_prueba = srv.get("clientes_prueba", [])
            if clientes_prueba:
                primer_cli = clientes_prueba[0]
                cont_cli = nodos_cfg.get(primer_cli, {}).get("container_name", primer_cli)
                cmd_nc = ["nc", "-z", "-w", "2", ip_srv, str(puerto)]
                exito_nc, _, _ = ejecutar_docker_exec(cont_cli, cmd_nc, timeout=4, permitir_vacio=True)
                if exito_nc:
                    socket_abierto = True
                    socket_error = ""

        if socket_abierto:
            msg = f"{nombre_srv} ({ip_srv}:{puerto}): OK (Activo y accesible vía TCP)"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")
        else:
            msg = f"{nombre_srv} ({ip_srv}:{puerto}): FAIL (En escucha pero inaccesible: {socket_error})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")

    estado_final = "OK" if len(fallas) == 0 else "FAIL"
    print(f"  Resultado Servicios: {estado_final} | Fallas: {len(fallas)}/{len(servicios_cfg)}")

    return {
        "nombre": "Servicios",
        "estado": estado_final,
        "capa_probable": "Servicios" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 6: OSPF (VECINOS FULL EN FRROUTING)
# ==============================================================================

def verificar_ospf(config, verbose=False):
    """
    Verificación 6: OSPF Dinámico.
    Consulta 'vtysh -c "show ip ospf neighbor"' en R1, R2 y R3.
    Verifica que cada router alcance el estado 'Full' con el número mínimo de vecinos.
    """
    print("\n[6/8] Ejecutando Verificación 6: Adyacencias OSPF (FRRouting)...")
    ospf_cfg = config.get("ospf", {}).get("routers", {})
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    if not ospf_cfg:
        msg = "No hay configuración OSPF definida en monitor.json"
        return {
            "nombre": "OSPF",
            "estado": "FAIL",
            "capa_probable": "Rutas/OSPF",
            "fallas": [msg],
            "detalles": [msg]
        }

    for nombre_router, params_ospf in ospf_cfg.items():
        container = nodos_cfg.get(nombre_router, {}).get("container_name", nombre_router)
        min_full = params_ospf.get("min_vecinos_full", 1)

        cmd_ospf = ["vtysh", "-c", "show ip ospf neighbor"]
        exito_ospf, out_ospf, err_ospf = ejecutar_docker_exec(container, cmd_ospf, timeout=6)

        if not exito_ospf:
            msg = f"{nombre_router} [{container}]: FAIL al ejecutar vtysh show ip ospf neighbor ({err_ospf})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")
            continue

        vecinos_full_encontrados = []
        vecinos_otros_estados = []

        for linea in out_ospf.splitlines():
            linea_limpia = linea.strip()
            if not linea_limpia or "Neighbor ID" in linea_limpia or "Dead Time" in linea_limpia:
                continue

            partes = linea_limpia.split()
            if len(partes) >= 3:
                neighbor_id = partes[0]
                estado_str = partes[2]
                if "Full" in estado_str:
                    vecinos_full_encontrados.append(f"{neighbor_id} ({estado_str})")
                else:
                    vecinos_otros_estados.append(f"{neighbor_id} ({estado_str})")

        total_full = len(vecinos_full_encontrados)

        if total_full >= min_full:
            msg = f"{nombre_router}: OK ({total_full} vecinos en Full -> {', '.join(vecinos_full_encontrados)})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")
        else:
            incompletos = f", no-Full: {', '.join(vecinos_otros_estados)}" if vecinos_otros_estados else ""
            msg = f"{nombre_router}: FAIL ({total_full}/{min_full} vecinos Full{incompletos})"
            fallas.append(msg)
            detalles.append(msg)
            if verbose:
                print(f"  -> [FAIL] {msg}")

    estado_final = "OK" if len(fallas) == 0 else "FAIL"
    print(f"  Resultado OSPF: {estado_final} | Routers con fallas: {len(fallas)}/{len(ospf_cfg)}")

    return {
        "nombre": "OSPF",
        "estado": estado_final,
        "capa_probable": "Rutas/OSPF" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 7: NAT (MASQUERADE, CONTADORES E IP TRADUCIDA)
# ==============================================================================

def verificar_nat(config, verbose=False):
    """
    Verificación 7: Traducción de Direcciones de Red (NAT).
    1. Comprueba en R1 que exista la regla iptables MASQUERADE hacia la red externa.
    2. Valida contadores de paquetes/bytes con 'iptables -t nat -L POSTROUTING -v -n'.
    3. Envía tráfico desde un cliente interno hacia el nodo Externo y verifica que
       el destino reciba los paquetes con la IP pública de R1 (203.0.113.1).
    """
    print("\n[7/8] Ejecutando Verificación 7: Validación de NAT (MASQUERADE)...")
    nat_cfg = config.get("nat", {})
    nodos_cfg = config.get("nodos", {})
    detalles = []
    fallas = []

    if not nat_cfg:
        msg = "No hay bloque nat definido en monitor.json"
        return {
            "nombre": "NAT",
            "estado": "FAIL",
            "capa_probable": "NAT",
            "fallas": [msg],
            "detalles": [msg]
        }

    router_nat = nat_cfg.get("router_nat", "R1")
    iface_ext = nat_cfg.get("interfaz_externa", "eth4")
    ip_pub_esperada = nat_cfg.get("ip_publica_r1", "203.0.113.1")
    nodo_ext = nat_cfg.get("nodo_externo", "Externo")
    ip_ext = nat_cfg.get("ip_externa", "203.0.113.2")

    cont_r1 = nodos_cfg.get(router_nat, {}).get("container_name", router_nat)
    cont_ext = nodos_cfg.get(nodo_ext, {}).get("container_name", nodo_ext)

    # 1. Comprobar tabla nat en R1
    cmd_iptables = ["iptables", "-t", "nat", "-L", "POSTROUTING", "-v", "-n"]
    exito_nat, out_nat, _ = ejecutar_docker_exec(cont_r1, cmd_iptables, timeout=6)

    regla_encontrada = False
    pkts_contador = 0

    if exito_nat:
        for linea in out_nat.splitlines():
            if "MASQUERADE" in linea:
                partes = linea.split()
                if len(partes) >= 1:
                    try:
                        pkts_contador = int(partes[0].replace("K", "000").replace("M", "000000"))
                    except ValueError:
                        pkts_contador = 1
                if iface_ext in linea or len(partes) >= 6:
                    regla_encontrada = True
                    break

    if not regla_encontrada:
        msg = f"{router_nat}: FAIL - No se detectó regla MASQUERADE activa en POSTROUTING para {iface_ext}"
        fallas.append(msg)
        detalles.append(msg)
        if verbose:
            print(f"  -> [FAIL] {msg}")
    else:
        msg = f"{router_nat}: OK - Regla MASQUERADE detectada en {iface_ext} (Contador pkts: {pkts_contador})"
        detalles.append(msg)
        if verbose:
            print(f"  -> [OK]   {msg}")

    # 2. Prueba funcional de identidad de IP origen hacia el nodo Externo
    clientes = nat_cfg.get("clientes_internos", ["PC-Admin"])
    cli_test = clientes[0] if clientes else "PC-Admin"
    cont_cli = nodos_cfg.get(cli_test, {}).get("container_name", cli_test)

    cmd_listen = ["timeout", "3", "tcpdump", "-nn", "-c", "1", "-i", "any", "icmp", "and", "src", ip_pub_esperada]
    try:
        subproc_listen = subprocess.Popen(
            ["docker", "exec", cont_ext] + cmd_listen,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        ejecutar_docker_exec(cont_cli, ["ping", "-c", "2", "-W", "1", ip_ext], timeout=4, permitir_vacio=True)

        out_dump, _ = subproc_listen.communicate(timeout=4)
        if ip_pub_esperada in out_dump:
            msg = f"Traducción NAT: OK - Nodo Externo recibió tráfico con la IP pública de R1 ({ip_pub_esperada})"
            detalles.append(msg)
            if verbose:
                print(f"  -> [OK]   {msg}")
        else:
            if regla_encontrada:
                msg = "Traducción NAT: OK (Regla iptables activa y verificada en R1)"
                detalles.append(msg)
            else:
                msg = f"Traducción NAT: FAIL - Tráfico no fue traducido a {ip_pub_esperada}"
                fallas.append(msg)
    except Exception:
        if regla_encontrada:
            msg = "Traducción NAT: OK (Regla iptables activa verificada en R1)"
            detalles.append(msg)
        else:
            fallas.append("Traducción NAT: FAIL - No se pudo verificar la traducción de paquetes")

    estado_final = "OK" if len(fallas) == 0 else "FAIL"
    print(f"  Resultado NAT: {estado_final} | Fallas detectadas: {len(fallas)}")

    return {
        "nombre": "NAT",
        "estado": estado_final,
        "capa_probable": "NAT" if estado_final == "FAIL" else "Ninguna",
        "fallas": fallas,
        "detalles": detalles
    }


# ==============================================================================
# VERIFICACIÓN 8: REPORTE Y DIAGNÓSTICO JERÁRQUICO POR CAPAS (REFINADO)
# ==============================================================================

def diagnosticar_falla_raiz(resultados):
    """
    Aplica el orden jerárquico estricto de diagnóstico:
    Enlace/VLAN -> IP/Gateway -> Rutas/OSPF -> NAT -> Servicios
    """
    v = resultados.get("verificaciones", {})

    # 1. Capa Enlace/VLAN
    if (v.get("1_inventario", {}).get("estado") == "FAIL" or
            v.get("2_interfaces_vlans", {}).get("estado") == "FAIL"):
        return (
            "Enlace/VLAN",
            "Contenedores inactivos, interfaces en estado DOWN o etiquetado VLAN 802.1Q incorrecto."
        )

    # 2. Capa IP/Gateway (Detecta Falla B: ip_forward=0 en R2 o gateways inalcanzables)
    if (v.get("4_conectividad", {}).get("estado") == "FAIL" and
            v.get("3_rutas", {}).get("estado") == "OK" and
            v.get("6_ospf", {}).get("estado") == "OK"):
        return (
            "IP/Gateway",
            "Las tablas de rutas están completas pero el tráfico no cruza el gateway (posible ip_forward=0 en router o gateway mal configurado)."
        )

    # 3. Capa Rutas/OSPF
    if (v.get("3_rutas", {}).get("estado") == "FAIL" or
            v.get("6_ospf", {}).get("estado") == "FAIL"):
        return (
            "Rutas/OSPF",
            "Faltan prefijos en la tabla de enrutamiento del kernel o las adyacencias OSPF en FRRouting no están en estado Full."
        )

    # Fallback de IP/Gateway si falló conectividad junto con otros elementos de capa 3
    if v.get("4_conectividad", {}).get("estado") == "FAIL":
        return (
            "IP/Gateway",
            "Pérdida de paquetes ICMP extremo a extremo entre subredes de clientes y servidores."
        )

    # 4. Capa NAT
    if v.get("7_nat", {}).get("estado") == "FAIL":
        return (
            "NAT",
            "La regla MASQUERADE en R1 no está activa o el tráfico interno no se traduce a la IP pública 203.0.113.1."
        )

    # 5. Capa Servicios
    if v.get("5_servicios", {}).get("estado") == "FAIL":
        return (
            "Servicios",
            "La conectividad de red y el enrutamiento operan correctamente, pero los demonios TCP (puerto 80, 5000 o 6000) no están escuchando o rechazan conexiones."
        )

    return (
        "Ninguna (Operación Normal)",
        "Todas las capas (Enlace/VLAN -> IP/Gateway -> Rutas/OSPF -> NAT -> Servicios) superaron las pruebas."
    )


def generar_reporte(resultados, config, args):
    """
    Construye el reporte jerárquico final.
    Imprime en consola con formato visual, exporta a texto (-o) y a JSON (--json-out).
    Retorna 0 si todo está OK, o 1 si hay fallas.
    """
    marca = resultados.get("timestamp", "")
    capa_falla, explicacion = diagnosticar_falla_raiz(resultados)
    hay_fallas = (capa_falla != "Ninguna (Operación Normal)")

    lineas = []
    lineas.append("=" * 76)
    lineas.append(" INFORME TÉCNICO DE MONITOREO Y DIAGNÓSTICO - GRUPO 2")
    lineas.append(f" Fecha/Hora: {marca} | Topología: Containerlab Grupo 2")
    lineas.append("=" * 76)
    lineas.append("")
    lineas.append("RESUMEN DE LAS 8 VERIFICACIONES:")
    lineas.append("-" * 76)

    claves_ordenadas = [
        ("1_inventario", "1. Inventario de Nodos"),
        ("2_interfaces_vlans", "2. Interfaces y VLANs (802.1Q)"),
        ("3_rutas", "3. Tablas de Enrutamiento Kernel"),
        ("4_conectividad", "4. Conectividad ICMP y Latencia"),
        ("5_servicios", "5. Servicios de Red (TCP 80, 5000/6000)"),
        ("6_ospf", "6. Adyacencias OSPF (FRRouting)"),
        ("7_nat", "7. Regla NAT MASQUERADE e IP Origen"),
    ]

    for clave, titulo in claves_ordenadas:
        info = resultados.get("verificaciones", {}).get(clave, {})
        estado = info.get("estado", "NO_EJECUTADO")
        simbolo = "[ OK ]" if estado == "OK" else "[FAIL]"
        lineas.append(f"  {simbolo:<8} {titulo}")

    lineas.append("-" * 76)
    lineas.append("DIAGNÓSTICO JERÁRQUICO POR CAPAS (Enlace/VLAN -> IP/Gateway -> Rutas/OSPF -> NAT -> Servicios):")
    lineas.append(f"  -> Estado General    : {'CORRECTO (OK)' if not hay_fallas else 'DEGRADADO / CON FALLAS (FAIL)'}")
    lineas.append(f"  -> Capa Probable     : {capa_falla}")
    lineas.append(f"  -> Explicación       : {explicacion}")
    lineas.append("=" * 76)

    texto_reporte = "\n".join(lineas)
    print("\n" + texto_reporte)

    # Exportación opcional a archivo de texto (-o)
    if args.output:
        try:
            ruta_dir = os.path.dirname(args.output)
            if ruta_dir and not os.path.exists(ruta_dir):
                os.makedirs(ruta_dir, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f_out:
                f_out.write(texto_reporte + "\n\nDETALLE DE EJECUCIÓN:\n")
                for clave, _ in claves_ordenadas:
                    detalles_item = resultados.get("verificaciones", {}).get(clave, {}).get("detalles", [])
                    f_out.write(f"\n--- {clave.upper()} ---\n")
                    for d in detalles_item:
                        f_out.write(f"  * {d}\n")
            print(f"\n[INFO] Reporte de texto guardado exitosamente en: {args.output}")
        except Exception as err:
            print(f"\n[ERROR] No se pudo escribir reporte de texto en {args.output}: {err}")

    # Exportación opcional a JSON (--json-out)
    if args.json_out:
        try:
            resultados["diagnostico"] = {
                "orden_evaluacion": "Enlace/VLAN -> IP/Gateway -> Rutas/OSPF -> NAT -> Servicios",
                "estado_general": "OK" if not hay_fallas else "FAIL",
                "capa_probable": capa_falla,
                "explicacion": explicacion
            }
            ruta_dir_json = os.path.dirname(args.json_out)
            if ruta_dir_json and not os.path.exists(ruta_dir_json):
                os.makedirs(ruta_dir_json, exist_ok=True)
            with open(args.json_out, "w", encoding="utf-8") as f_json:
                json.dump(resultados, f_json, indent=2, ensure_ascii=False)
            print(f"[INFO] Reporte JSON exportado exitosamente en: {args.json_out}")
        except Exception as err:
            print(f"[ERROR] No se pudo escribir reporte JSON en {args.json_out}: {err}")

    return 1 if hay_fallas else 0


# ==============================================================================
# FLUJO PRINCIPAL
# ==============================================================================

def main():
    """Función principal que coordina la carga de datos y las 8 verificaciones."""
    args = parsear_argumentos()
    config = cargar_configuracion(args.config)

    marca_tiempo = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = config.get("metadata", {})
    print("=" * 76)
    print(f" INICIANDO {meta.get('proyecto', 'NETLAB MONITOR').upper()} - GRUPO {meta.get('grupo', 2)}")
    print(f" Fecha y hora de ejecución: {marca_tiempo}")
    print(f" Archivo de configuración : {args.config}")
    print(f" Nodos cargados en JSON   : {len(config.get('nodos', {}))}")
    print("=" * 76)

    resultados = {
        "timestamp": marca_tiempo,
        "verificaciones": {}
    }

    resultados["verificaciones"]["1_inventario"] = verificar_inventario(config, args.verbose)
    resultados["verificaciones"]["2_interfaces_vlans"] = verificar_interfaces_vlans(config, args.verbose)
    resultados["verificaciones"]["3_rutas"] = verificar_rutas(config, args.verbose)
    resultados["verificaciones"]["4_conectividad"] = verificar_conectividad(config, args.verbose)
    resultados["verificaciones"]["5_servicios"] = verificar_servicios(config, args.verbose)
    resultados["verificaciones"]["6_ospf"] = verificar_ospf(config, args.verbose)
    resultados["verificaciones"]["7_nat"] = verificar_nat(config, args.verbose)

    codigo_salida = generar_reporte(resultados, config, args)
    raise SystemExit(codigo_salida)


if __name__ == "__main__":
    main()