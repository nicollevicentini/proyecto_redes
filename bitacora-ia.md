# Bitácora de Uso de Inteligencia Artificial (Parte 2 - Monitor y Diagnóstico)

## 1. Registro de Prompts y Generación Iterativa
Durante el desarrollo del sistema de monitoreo para el Grupo 2 se utilizó un flujo iterativo dividido en 5 etapas:
1. **Etapa 1 (Modelado JSON y Esqueleto):** Estructuración de `monitor.json` con el direccionamiento VLSM del Grupo 2 (`172.16.2.0/27`, `172.16.2.32/28`, `172.16.2.48/29`, enlaces `/30` y red externa `203.0.113.0/30`) y creación del esqueleto CLI con `argparse`.
2. **Etapa 2 (Verificaciones 1, 2 y 3):** Programación del motor `ejecutar_docker_exec()` y las funciones de Inventario, Interfaces/VLANs (`ip -br a`, `ip -d link`) y Rutas (`ip route`).
3. **Etapa 3 (Verificaciones 4 y 5):** Implementación de pruebas ICMP/traceroute y validación de puertos TCP 80 y 5000 con `socket` y `ss -tln`.
4. **Etapa 4 (Verificaciones 6, 7 y 8):** Consultas a FRRouting (`vtysh`), verificación de `iptables MASQUERADE` en R1 y lógica de reporte jerárquico con exportación JSON.
5. **Etapa 5 (Documentación y Pruebas de Falla/Cambio):** Parametrización del Cambio B (`srv-extra`) y validación de diagnóstico ante la Falla B (`ip_forward=0`).

## 2. Código Aceptado de la IA
* La estructura declarativa de `monitor.json` que independiza los datos de la lógica del script.
* El uso exclusivo de las 6 librerías estándar autorizadas (`subprocess`, `socket`, `os`, `json`, `argparse`, `datetime`) y el uso de `raise SystemExit(codigo)` para devolver códigos de estado al sistema operativo sin necesidad de importar la librería `sys`.
* El parser de nombres de interfaces que limpia el sufijo `@ifX` generado por los pares `veth` de Docker/Containerlab al leer `ip -br a`.

## 3. Correcciones Realizadas y Respuesta de Defensa

### ¿Qué propuso la IA que tuvimos que corregir o rechazar y por qué?
1. **Rechazo de validación ingenua en `subprocess` (Prevención de Falsos Positivos):**
   * **Problema inicial:** En una implementación básica, iterar con un ciclo `for linea in proceso.stdout.splitlines():` sobre la salida de `docker exec` provoca que, si el contenedor está apagado o el comando falla, `stdout` quede vacío, el ciclo no se ejecute ninguna vez y la función retorne `OK` por no haber entrado a ninguna condición de error.
   * **Corrección aplicada:** Se diseñó la función centralizada `ejecutar_docker_exec()` que verifica primero `proceso.returncode != 0` y además exige que `len(stdout.strip()) > 0` antes de evaluar cualquier dato. Si falla `docker exec`, la prueba retorna `FAIL` de forma inmediata.

2. **Corrección del alcance del socket TCP desde el Host hacia Contenedores (`verificar_servicios`):**
   * **Problema inicial:** La propuesta inicial abría `socket.connect_ex((ip_srv, puerto))` únicamente desde el sistema operativo anfitrión (Ubuntu VM). Sin embargo, el host principal de Ubuntu no siempre tiene rutas estáticas hacia la subred interna `172.16.2.48/29` de Containerlab, lo que arrojaba error `ENETUNREACH` aunque el servidor funcionara correctamente.
   * **Corrección aplicada:** Se mantuvo la prueba con `socket` nativo de Python, pero se añadió una verificación previa con `ss -tln` en el servidor y un respaldo de conexión TCP desde los contenedores clientes (`PC-Admin` / `PC-Ventas`) dentro del namespace de red de la topología.

3. **Ajuste en el orden de diagnóstico para la Falla B (`ip_forward=0`):**
   * **Problema inicial:** Si se evalúa primero OSPF/Rutas como única causa de fallas de Capa 3, al apagar `net.ipv4.ip_forward` en `R2` las rutas OSPF y las adyacencias siguen en estado `Full` (ya que los paquetes Hello OSPF son multicast de enlace local y no requieren forwarding a través del router), lo que podía confundir al clasificador.
   * **Corrección aplicada:** Se ajustó `diagnosticar_falla_raiz()` siguiendo la secuencia estricta `Enlace/VLAN → IP/Gateway → Rutas/OSPF → NAT → Servicios`, permitiendo que cuando `3_rutas` y `6_ospf` están en `OK` pero `4_conectividad` da `FAIL`, el monitor dictamine con exactitud una falla en la capa **`IP/Gateway`** por bloqueo de reenvío de paquetes.