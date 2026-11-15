4. Cómo configurar y ejecutar el monitor
Toda la topología esperada (nodos, subredes VLSM, VLANs 10 y 20, rutas OSPF, reglas NAT y puertos TCP) se define en el archivo declarativo monitor.json. Para adaptar el monitor a nuevos nodos o servicios, basta con editar monitor.json sin alterar el código fuente de Python.

Modos de ejecución:

Ejecución estándar en consola:
python3 netlab_monitor.py

Ejecución detallada (Verbose):
python3 netlab_monitor.py -v

Exportación de reportes en Texto y JSON (Nivel Avanzado):
python3 netlab_monitor.py -o evidencias/reportes_monitor/reporte_normal.txt --json-out evidencias/reportes_monitor/reporte_normal.json