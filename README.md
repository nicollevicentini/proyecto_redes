# Netlab Monitor - Automatización y Diagnóstico en Containerlab (Grupo 2)

## 1. ¿Qué hace este proyecto?
Este repositorio contiene la topología de red corporativa del **Grupo 2** desplegada sobre **Containerlab** y la herramienta de monitoreo automatizado `netlab_monitor.py`. El sistema valida el estado operativo de la red de extremo a extremo realizando **8 verificaciones automatizadas** y emitiendo un diagnóstico jerárquico por capas (`Enlace/VLAN → IP/Gateway → Rutas/OSPF → NAT → Servicios`).

## 2. Requisitos del Sistema
* **Sistema Operativo:** Ubuntu Server / Linux con soporte para namespaces de red.
* **Motor de contenedores:** Docker CE y Containerlab instalados.
* **Intérprete:** Python 3.8 o superior.
* **Librerías de Python:** Exclusivamente librerías estándar (`subprocess`, `socket`, `os`, `json`, `argparse`, `datetime`). No requiere instalación de paquetes externos con `pip`.

## 3. Cómo desplegar el laboratorio
Desde el directorio raíz del proyecto, desplegar la topología de Containerlab y aplicar la configuración de red:
```bash
cd ~/containerlab/proyecto
sudo containerlab deploy -t netlab.clab.yml