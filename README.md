# SUMI — Sistemas Unificados de Máquinas Interconectadas

Prototipo de computación distribuida para conectar equipos de una red local, repartir cargas compatibles y medir cuándo trabajar en conjunto aporta una mejora. El proyecto también experimenta con inferencia de modelos grandes usando `llama.cpp` y su modo RPC.

> SUMI no añade RAM física al sistema operativo ni convierte dos computadoras en una sola PC. Permite que ciertos trabajos preparados para distribución usen CPU y memoria de varios nodos.

## Qué incluye

- Coordinador y nodos con descubrimiento automático en la red local.
- Pruebas de procesamiento por CPU y procesamiento de imágenes repartido entre equipos.
- Experimentos de inferencia con `llama.cpp` y RPC para evaluar modelos que no caben en la memoria disponible de un solo nodo.
- Panel web local, métricas de CPU, RAM y red, resultados persistidos en SQLite y exportación a CSV.
- Guía para instalar y ejecutar el prototipo en Windows.

## Tecnologías

- Python 3.10 o superior; biblioteca estándar y `psutil` opcional.
- `llama.cpp` para los experimentos de inferencia distribuida.
- HTML y JavaScript para el panel local.

## Inicio rápido en Windows

1. Conecta los equipos al mismo router y configura la red como **Privada**.
2. Instala Python en cada equipo.
3. En la carpeta `prototipo`, ejecuta `iniciar_xara.bat`. El primer equipo que inicia actúa como coordinador; los demás se unen como nodos.
4. Abre `http://localhost:8765` en el equipo coordinador.

La interfaz y los scripts de esta versión todavía conservan el nombre **XARA**. La guía de usuario está en [`GUIA.pdf`](GUIA.pdf) y [`prototipo/GUIA.md`](prototipo/GUIA.md); el alcance técnico y las pruebas están documentados en [`xara_documentacion.pdf`](xara_documentacion.pdf) y [`prototipo/README.md`](prototipo/README.md).

## Estado y límites

Prototipo v0.4. La documentación registra pruebas en Linux con dos nodos simulados; todavía falta validar el funcionamiento en dos equipos Windows reales, con descargas y modelos reales. Los resultados medidos en máquinas virtuales no representan el rendimiento de los equipos del usuario.

## Seguridad

El protocolo local de esta versión no usa autenticación ni cifrado. Úsalo solamente en una red privada y de confianza; no expongas sus puertos a Internet ni a redes públicas. Los nodos ejecutan el código que reciben del coordinador.
