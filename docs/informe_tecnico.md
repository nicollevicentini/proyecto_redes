# INFORME TÉCNICO: DESPLIEGUE, MONITOREO Y DIAGNÓSTICO AUTOMATIZADO DE RED (NETLAB-G2)

**Proyecto:** Automatización de Redes y Pruebas Continuas  
**Topología:** `netlab-g2` (Containerlab)  
**Grupo:** Grupo 2  
**Integrantes:** Alex Camacaro, Nicolle Vicentini  
**Fecha:** Noviembre de 2026  
**Repositorio GitHub:** `https://github.com/nicollevicentini/proyecto_redes`

---

## 1. RESUMEN 

El presente informe detalla la implementación, verificación y automatización del entorno de red virtualizado **`netlab-g2`**, desplegado mediante **Containerlab** sobre Ubuntu Server. El laboratorio integra una arquitectura multiservicio con segmentación por VLANs (IEEE 802.1Q), enrutamiento dinámico interior **OSPF** sobre routers FRRouting, traducción de direcciones de red (**NAT/MASQUERADE**) para acceso al nodo externo y servicios de red en capa de aplicación (HTTP y socket TCP persistente).

Para garantizar la observabilidad continua de la infraestructura, se implementó una herramienta de auditoría automatizada en Python (`netlab_monitor.py`) guiada por un esquema declarativo (`monitor.json`). El monitor realiza una evaluación integral en 8 dimensiones de red e incorpora un **modelo de diagnóstico jerárquico por capas** (Enlace/VLAN $\rightarrow$ Direccionamiento $\rightarrow$ Enrutamiento OSPF $\rightarrow$ NAT $\rightarrow$ Servicios) que aísla de forma determinista la causa raíz ante eventos de degradación o caída de enlaces.

---

## 2. ARQUITECTURA DE RED Y DIRECCIONAMIENTO VLSM

### 2.1 Esquema de Subredes VLSM
La topología utiliza el bloque base privado `172.16.2.0/24` subdividido mediante VLSM para maximizar la eficiencia en el uso de direcciones, junto con un segmento público de simulación externa `203.0.113.0/29`.

| Subred | Máscara | Rango Útil | Uso / Segmento | Gateways / Nodos Asignados |
| :--- | :---: | :---: | :--- | :--- |
| `172.16.2.0/27` | `/27` (255.255.255.224) | `172.16.2.1 - 172.16.2.30` | VLAN 10 (Administración) | R2: `172.16.2.1` / PC-Admin: `172.16.2.2` |
| `172.16.2.32/28` | `/28` (255.255.255.240) | `172.16.2.33 - 172.16.2.46` | VLAN 20 (Ventas) | R2: `172.16.2.33` / PC-Ventas: `172.16.2.34` |
| `172.16.2.48/29` | `/29` (255.255.255.248) | `172.16.2.49 - 172.16.2.54` | LAN Servidores (DMZ) | R1: `172.16.2.49` / SRV-Web: `172.16.2.50` / SRV-Datos: `172.16.2.51` |
| `172.16.2.56/30` | `/30` (255.255.255.252) | `172.16.2.57 - 172.16.2.58` | Transporte WAN R1 - R2 | R1 (eth2): `172.16.2.57` / R2 (eth2): `172.16.2.58` |
| `172.16.2.60/30` | `/30` (255.255.255.252) | `172.16.2.61 - 172.16.2.62` | Transporte WAN R2 - R3 | R2 (eth3): `172.16.2.61` / R3 (eth1): `172.16.2.62` |
| `172.16.2.64/30` | `/30` (255.255.255.252) | `172.16.2.65 - 172.16.2.66` | Transporte WAN R1 - R3 | R1 (eth3): `172.16.2.65` / R3 (eth2): `172.16.2.66` |
| `203.0.113.0/29` | `/29` (255.255.255.248) | `203.0.113.1 - 203.0.113.6` | WAN Salida Externa | R1 (eth4): `203.0.113.1` / Externo (eth1): `203.0.113.2` |

### 2.2 Inventario de Nodos y Contenedores

Todos los contenedores se generan bajo el prefijo de proyecto `clab-netlab-g2-*`:

1. **`clab-netlab-g2-r1`** (Imagen: `quay.io/frrouting/frr:containerlab-10.7.1`): Router de borde hacia la red externa, enrutador OSPF (Router-ID: `1.1.1.1`) y pasarela NAT hacia el host externo.
2. **`clab-netlab-g2-r2`** (Imagen: `quay.io/frrouting/frr:containerlab-10.7.1`): Router de distribución de acceso LAN, encargado del enrutamiento inter-VLAN (subinterfaces `eth1.10` y `eth1.20`) y vecino OSPF (Router-ID: `2.2.2.2`).
3. **`clab-netlab-g2-r3`** (Imagen: `quay.io/frrouting/frr:containerlab-10.7.1`): Router de tránsito WAN central, cerrando el anillo de conectividad en triángulo (Router-ID: `3.3.3.3`).
4. **`clab-netlab-g2-pc-admin`** (Imagen: `nicolaka/netshoot:latest`): Cliente de gestión en VLAN 10 (`172.16.2.2/27`).
5. **`clab-netlab-g2-pc-ventas`** (Imagen: `nicolaka/netshoot:latest`): Cliente corporativo en VLAN 20 (`172.16.2.34/28`).
6. **`clab-netlab-g2-srv-web`** (Imagen: `nginx:alpine`): Servidor web corporativo HTTP en puerto 80 (`172.16.2.50/29`).
7. **`clab-netlab-g2-srv-datos`** (Imagen: `nicolaka/netshoot:latest`): Servidor de datos backend con listener TCP en puerto 5000 (`172.16.2.51/29`).
8. **`clab-netlab-g2-externo`** (Imagen: `nicolaka/netshoot:latest`): Simulación de host en Internet (`203.0.113.2/29`) sin rutas directas hacia los segmentos `172.16.2.0/24`.

---

## 3. CONFIGURACIONES CLAVE DE LA INFRAESTRUCTURA

### 3.1 Segmentación VLAN (IEEE 802.1Q) en `sw-a` y R2
El switch `sw-a` opera como un puente Linux con filtrado VLAN activo (`vlan_filtering 1`). El puerto `a1` hacia R2 está configurado en modo troncal (transporta etiquetas para VLAN 10 y 20). Los puertos `a2` y `a3` operan en modo acceso sin etiquetado con PVID 10 y 20 respectivamente. En R2, la encapsulación 802.1Q se gestiona mediante subinterfaces lógicas de Linux:
* `eth1.10`: IP `172.16.2.1/27` (Default Gateway VLAN 10).
* `eth1.20`: IP `172.16.2.33/28` (Default Gateway VLAN 20).

### 3.2 Protocolo de Enrutamiento Dinámico OSPF
La comunicación entre routers se realiza mediante el demonio `ospfd` de FRRouting en el Área 0 backbone:
* Anuncio global: `network 172.16.2.0/24 area 0`.
* Política de interfaces pasivas: Se aplica `passive-interface default` por seguridad, reactivando OSPF explícitamente solo en los enlaces de tránsito punto a punto (`no passive-interface eth2`, `no passive-interface eth3` en R1/R2; `eth1`/`eth2` en R3).
* En R1 se anuncia adicionalmente el segmento externo `203.0.113.0/29 area 0` con su interfaz pasiva.
* Convergencia lograda: Enlace en triángulo totalmente adyacente con 2 vecinos en estado `Full/DR` o `Full/Backup` por cada router.

### 3.3 Traducción de Direcciones (NAT / MASQUERADE)
Para permitir que los clientes internos alcancen el nodo exterior sin que éste requiera rutas de retorno privadas:
1. Reenvío habilitado en el kernel: `net.ipv4.ip_forward = 1` en todos los routers.
2. Regla de enmascaramiento inyectada en R1 sobre la tabla NAT:
   ```bash
   iptables -t nat -A POSTROUTING -s 172.16.2.0/24 -o eth4 -j MASQUERADE
   ```
Todo el tráfico que egresa por `eth4` hacia `203.0.113.2` sustituye su IP de origen por la interfaz pública de R1 (`203.0.113.1`).

---

## 4. CÓMO CONFIGURAR Y EJECUTAR EL MONITOR

Toda la topología esperada (nodos, subredes VLSM, VLANs 10 y 20, rutas OSPF, reglas NAT y puertos TCP) se define en el archivo declarativo `monitor.json`. Para adaptar el monitor a nuevos nodos o servicios, basta con editar `monitor.json` sin alterar el código fuente de Python.

### Modos de ejecución en terminal:

1. **Ejecución estándar en consola:**
   ```bash
   python3 netlab_monitor.py
   ```

2. **Ejecución detallada (Modo Verbose):**
   ```bash
   python3 netlab_monitor.py -v
   ```

3. **Exportación de reportes automáticos en Texto y JSON:**
   ```bash
   python3 netlab_monitor.py -v -o evidencias/reportes_monitor/reporte_base
   ```
   *(El argumento `-o` recibe el prefijo y genera automáticamente tanto `reporte_base.txt` como `reporte_base.json`)*.

---

## 5. RESULTADOS DE VERIFICACIÓN Y EVIDENCIAS

### 5.1 Reporte Operativo Base (100% de Pruebas Superadas)
A continuación se transcribe la salida real del monitor ejecutado sobre el laboratorio completamente aprovisionado:

```text
======================================================================
  INICIANDO NETLAB MONITOR GRUPO 2 - GRUPO 2
  Fecha y hora de ejecución: 2026-11-15 19:35:10
  Archivo de configuración : monitor.json
  Nodos cargados en JSON   : 8
======================================================================

[1/8] Ejecutando Verificación 1: Inventario de Nodos e IPs...
  -> [OK]   Nodo R1 [clab-netlab-g2-r1]: OK (Activo con IP 172.16.2.49)
  -> [OK]   Nodo R2 [clab-netlab-g2-r2]: OK (Activo con IP 172.16.2.1)
  -> [OK]   Nodo R3 [clab-netlab-g2-r3]: OK (Activo con IP 172.16.2.62)
  -> [OK]   Nodo PC-Admin [clab-netlab-g2-pc-admin]: OK (Activo con IP 172.16.2.2)
  -> [OK]   Nodo PC-Ventas [clab-netlab-g2-pc-ventas]: OK (Activo con IP 172.16.2.34)
  -> [OK]   Nodo SRV-Web [clab-netlab-g2-srv-web]: OK (Activo con IP 172.16.2.50)
  -> [OK]   Nodo SRV-Datos [clab-netlab-g2-srv-datos]: OK (Activo con IP 172.16.2.51)
  -> [OK]   Nodo Externo [clab-netlab-g2-externo]: OK (Activo con IP 203.0.113.2)
  Resultado Inventario: OK | Disponibles: 8 | Faltantes: 0

[2/8] Ejecutando Verificación 2: Interfaces y VLANs...
  -> [OK]   R1 [eth1]: OK (Estado UP, IP 172.16.2.49/29)
  -> [OK]   R1 [eth2]: OK (Estado UP, IP 172.16.2.57/30)
  -> [OK]   R1 [eth3]: OK (Estado UP, IP 172.16.2.65/30)
  -> [OK]   R1 [eth4]: OK (Estado UP, IP 203.0.113.1/29)
  -> [OK]   R2 [eth1]: OK (Estado UP, Trunk 802.1Q sin IP)
  -> [OK]   R2 [eth1.10]: OK (Estado UP, IP 172.16.2.1/27, VLAN 10)
  -> [OK]   R2 [eth1.20]: OK (Estado UP, IP 172.16.2.33/28, VLAN 20)
  -> [OK]   R2 [eth2]: OK (Estado UP, IP 172.16.2.58/30)
  -> [OK]   R2 [eth3]: OK (Estado UP, IP 172.16.2.61/30)
  -> [OK]   R3 [eth1]: OK (Estado UP, IP 172.16.2.62/30)
  -> [OK]   R3 [eth2]: OK (Estado UP, IP 172.16.2.66/30)
  -> [OK]   PC-Admin [eth1]: OK (Estado UP, IP 172.16.2.2/27)
  -> [OK]   PC-Ventas [eth1]: OK (Estado UP, IP 172.16.2.34/28)
  -> [OK]   SRV-Web [eth1]: OK (Estado UP, IP 172.16.2.50/29)
  -> [OK]   SRV-Datos [eth1]: OK (Estado UP, IP 172.16.2.51/29)
  -> [OK]   Externo [eth1]: OK (Estado UP, IP 203.0.113.2/29)
  Resultado Interfaces/VLANs: OK | Fallas: 0

[3/8] Ejecutando Verificación 3: Tablas de Enrutamiento (ip route)...
  -> [OK]   R1: OK - Ruta 172.16.2.48/29 (CONECTADA) presente
  -> [OK]   R1: OK - Ruta 172.16.2.56/30 (CONECTADA) presente
  -> [OK]   R1: OK - Ruta 172.16.2.64/30 (CONECTADA) presente
  -> [OK]   R1: OK - Ruta 203.0.113.0/29 (CONECTADA) presente
  -> [OK]   R1: OK - Ruta 172.16.2.0/27 (OSPF) presente
  -> [OK]   R1: OK - Ruta 172.16.2.32/28 (OSPF) presente
  -> [OK]   R1: OK - Ruta 172.16.2.60/30 (OSPF) presente
  -> [OK]   R2: OK - Ruta 172.16.2.0/27 (CONECTADA) presente
  -> [OK]   R2: OK - Ruta 172.16.2.32/28 (CONECTADA) presente
  -> [OK]   R2: OK - Ruta 172.16.2.56/30 (CONECTADA) presente
  -> [OK]   R2: OK - Ruta 172.16.2.60/30 (CONECTADA) presente
  -> [OK]   R2: OK - Ruta 172.16.2.48/29 (OSPF) presente
  -> [OK]   R2: OK - Ruta 172.16.2.64/30 (OSPF) presente
  -> [OK]   R2: OK - Ruta 203.0.113.0/29 (OSPF) presente
  -> [OK]   R3: OK - Ruta 172.16.2.60/30 (CONECTADA) presente
  -> [OK]   R3: OK - Ruta 172.16.2.64/30 (CONECTADA) presente
  -> [OK]   R3: OK - Ruta 172.16.2.0/27 (OSPF) presente
  -> [OK]   R3: OK - Ruta 172.16.2.32/28 (OSPF) presente
  -> [OK]   R3: OK - Ruta 172.16.2.48/29 (OSPF) presente
  -> [OK]   R3: OK - Ruta 172.16.2.56/30 (OSPF) presente
  -> [OK]   R3: OK - Ruta 203.0.113.0/29 (OSPF) presente
  Resultado Rutas: OK | Fallas: 0

[4/8] Ejecutando Verificación 4: Conectividad (Ping y Traceroute)...
  -> [OK]   PC-Admin a Gateway R2 (VLAN 10): OK (0% pérdida, RTT avg: 0.045 ms, 1 saltos)
  -> [OK]   PC-Admin a PC-Ventas (Inter-VLAN): OK (0% pérdida, RTT avg: 0.068 ms, 2 saltos)
  -> [OK]   PC-Admin a SRV-Web (HTTP): OK (0% pérdida, RTT avg: 0.125 ms, 3 saltos)
  -> [OK]   PC-Admin a SRV-Datos (TCP 5000): OK (0% pérdida, RTT avg: 0.072 ms, 3 saltos)
  -> [OK]   PC-Admin a Nodo Externo (via NAT): OK (0% pérdida, RTT avg: 0.110 ms, 3 saltos)
  -> [OK]   PC-Ventas a SRV-Web: OK (0% pérdida, RTT avg: 0.082 ms, 3 saltos)
  -> [OK]   PC-Ventas a Nodo Externo (via NAT): OK (0% pérdida, RTT avg: 0.089 ms, 3 saltos)
  Resultado Conectividad: OK | Fallas: 0/7

[5/8] Ejecutando Verificación 5: Disponibilidad de Servicios TCP...
  -> [OK]   Servicio Web HTTP Nginx (172.16.2.50:80): OK (HTTP 200 OK)
  -> [OK]   Servicio de Datos Backend TCP 5000 (172.16.2.51:5000): OK (Activo y accesible vía TCP)
  Resultado Servicios: OK | Fallas: 0/2

[6/8] Ejecutando Verificación 6: Adyacencias OSPF (FRRouting)...
  -> [OK]   R1: OK (2 vecinos en Full -> 2.2.2.2 (Full/DR), 3.3.3.3 (Full/DR))
  -> [OK]   R2: OK (2 vecinos en Full -> 1.1.1.1 (Full/Backup), 3.3.3.3 (Full/DR))
  -> [OK]   R3: OK (2 vecinos en Full -> 2.2.2.2 (Full/Backup), 1.1.1.1 (Full/Backup))
  Resultado OSPF: OK | Routers con fallas: 0/3

[7/8] Ejecutando Verificación 7: Validación de NAT (MASQUERADE)...
  -> [OK]   R1: OK - Regla MASQUERADE y reenvío IPv4 activos en POSTROUTING para eth4
  -> [OK]   Traducción NAT: OK - Nodo Externo recibió tráfico con la IP pública de R1 (203.0.113.1)
  Resultado NAT: OK | Fallas detectadas: 0

======================================================================
INFORME TÉCNICO DE MONITOREO Y DIAGNÓSTICO - GRUPO 2
Fecha/Hora: 2026-11-15 19:35:10 | Topología: netlab-g2
======================================================================

RESUMEN DE LAS 8 VERIFICACIONES:
----------------------------------------------------------------------
  [ OK ]  1. Inventario de Nodos
  [ OK ]  2. Interfaces y VLANs (802.1Q)
  [ OK ]  3. Tablas de Enrutamiento Kernel
  [ OK ]  4. Conectividad ICMP y Latencia
  [ OK ]  5. Servicios de Red (TCP 80, 5000)
  [ OK ]  6. Adyacencias OSPF (FRRouting)
  [ OK ]  7. Regla NAT MASQUERADE e IP Origen
  [ OK ]  8. Diagnóstico Jerárquico Multicapa
----------------------------------------------------------------------
DIAGNÓSTICO JERÁRQUICO POR CAPAS (Enlace/VLAN -> IP/Gateway -> Rutas/OSPF -> NAT -> Servicios):
  -> Estado General  : OPERATIVO AL 100% (OK)
  -> Capa Probable   : Ninguna (Todas las capas saludables)
  -> Explicación     : Los 8 nodos, enlaces VLAN 802.1Q, vecindades OSPF, traducción NAT y servicios TCP operan sin errores.
======================================================================
```

---

## 6. ANÁLISIS DE RESILIENCIA Y DIAGNÓSTICO JERÁRQUICO

Para comprobar el motor de diagnóstico en condiciones anómalas, se provocó una perturbación controlada bajando la subinterfaz lógica de la VLAN 10 en R2 (`eth1.10 down`).

### 6.1 Reporte de Detección de Falla (`reporte_falla_vlan.txt`)
Al ejecutar el monitor tras la desconexión:
```text
[2/8] Ejecutando Verificación 2: Interfaces y VLANs...
  -> [FAIL] R2 [eth1.10]: FAIL (Interfaz en estado DOWN)
  Resultado Interfaces/VLANs: FAIL | Fallas: 1

[4/8] Ejecutando Verificación 4: Conectividad (Ping y Traceroute)...
  -> [FAIL] PC-Admin a Gateway R2 (VLAN 10): FAIL (100% pérdida)
  -> [FAIL] PC-Admin a PC-Ventas (Inter-VLAN): FAIL (100% pérdida)
  -> [FAIL] PC-Admin a SRV-Web (HTTP): FAIL (100% pérdida)
  Resultado Conectividad: FAIL | Fallas: 5/7

RESUMEN DE LAS 8 VERIFICACIONES:
----------------------------------------------------------------------
  [ OK ]  1. Inventario de Nodos
  [FAIL]  2. Interfaces y VLANs (802.1Q)
  [ OK ]  3. Tablas de Enrutamiento Kernel
  [FAIL]  4. Conectividad ICMP y Latencia
  [ OK ]  5. Servicios de Red (TCP 80, 5000)
  [ OK ]  6. Adyacencias OSPF (FRRouting)
  [ OK ]  7. Regla NAT MASQUERADE e IP Origen
  [FAIL]  8. Diagnóstico Jerárquico Multicapa
----------------------------------------------------------------------
DIAGNÓSTICO JERÁRQUICO POR CAPAS:
  -> Estado General  : DEGRADADO / CON FALLAS (FAIL)
  -> Capa Probable   : Enlace/VLAN o Direccionamiento IP
  -> Explicación     : Contenedores inactivos, interfaces en estado DOWN o etiquetado VLAN 802.1Q incorrecto.
```

### 6.2 Comportamiento del Diagnóstico Jerárquico
1. **Aislamiento de Causa Raíz:** A pesar de que los clientes experimentaron un fallo de conectividad hacia la web y hacia el host exterior, el monitor **no culpó erróneamente a NAT ni a los servidores HTTP**. El algoritmo evaluó de abajo hacia arriba en la pila protocolar y determinó que el fallo se originó en la **Capa de Enlace / Subinterfaz VLAN**.
2. **Restauración:** Al ejecutar `docker exec clab-netlab-g2-r2 ip link set eth1.10 up`, la interfaz recuperó el estado `UP` y el monitor volvió a reportar `OPERATIVO AL 100% (OK)` en menos de un segundo.

---

## 7. CONCLUSIONES

1. **Aprovisionamiento Reproducible:** La orquestación combinada de Containerlab y scripts bash permitió desplegar una topología compleja de 8 nodos con VLANs y OSPF en menos de 15 segundos de forma limpia y determinista.
2. **Efectividad del Enfoque Declarativo:** La separación entre la lógica del monitor (`netlab_monitor.py`) y la especificación de red (`monitor.json`) evitó modificar el código ante variaciones de nombres de contenedor o cambios de máscaras.
3. **Observabilidad por Capas:** La automatización no solo verifica la salud binaria (UP/DOWN) de los nodos, sino que valida la funcionalidad de extremo a extremo: convergencia de protocolos de estado de enlace (OSPF), traducción dinámica de paquetes (NAT) y transporte de aplicación en sockets TCP.