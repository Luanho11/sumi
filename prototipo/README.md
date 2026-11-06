# XARA · prototipo v0.4 (referencia técnica)

Guía para usuarios sin conocimientos técnicos: [GUIA.md](GUIA.md). Diseño y justificación: `../xara_documentacion.docx`.

## Archivos

| Archivo | Función |
|---|---|
| `xara.py` | Coordinador, nodo, pruebas automáticas, base de datos y API HTTP (Python 3.10+, solo biblioteca estándar; `psutil` opcional; P5 instala `pillow` con pip si falta) |
| `panel.html` | Panel web servido por el coordinador en `http://localhost:8765` |
| `iniciar_xara.bat` | Busca Python (`py -3` o `python`), instala `psutil` y ejecuta `xara.py`; lo vuelve a abrir si termina con el código 3 (se actualizó) |
| `instalar_ia.bat` | Busca Python igual que el anterior y ejecuta `xara.py instalar` |
| `abrir_cortafuegos.bat` | Abre TCP 8765, UDP 8766 y TCP 50052 solo en el perfil de red privada |
| `prompts.txt` | 10 preguntas para la prueba P4 |
| `motores/` | Binarios de llama.cpp (`llama-bench`, `llama-server`, `rpc-server` o `ggml-rpc-server`) |
| `modelos/` | Modelos `.gguf` (solo en el coordinador; se copian a los nodos bajo demanda) |
| `fotos/` | Fotos propias para P5 con `origen=carpeta` (opcional, solo en el coordinador) |
| `datos/` | Se crea solo: `xara.db`, `informes/`, `logs/` y `coordinador.txt` (último `--coord` que funcionó; el modo auto lo prueba si el descubrimiento no responde), `fotos_prueba/` y `fotos_resultado/<prueba>/` (P5) |

Requisito en Windows: Visual C++ Redistributable x64 (`VCREDIST`); sin él, los ejecutables de llama.cpp fallan con "no se encontró VCRUNTIME140.dll". XARA avisa al arrancar si falta.

## Modos

```
python xara.py                 # auto: busca coordinador; si no hay, lo es (y además trabaja como nodo)
python xara.py coordinador     # forzar coordinador
python xara.py equipo --coord IP:8765
python xara.py info            # inventario JSON del equipo
python xara.py instalar        # descarga llama.cpp (la versión más reciente que trae win-cpu-x64) y, en el coordinador, los modelos
python xara.py prueba --prueba P2 --opciones '{"repeticiones": 5}'
```

Opciones: `--hilos N` (tareas simultáneas del nodo; por defecto, núcleos lógicos), `--puerto`.

## Variables de entorno

| Variable | Defecto | Uso |
|---|---|---|
| `XARA_LEASE_S` | 300 | Segundos sin respuesta tras los que una tarea vuelve a la cola |
| `XARA_MARGEN_GB` | 1.0 | RAM que se reserva por equipo al planificar un modelo |
| `XARA_HILOS_IA` | núcleos físicos | Hilos de llama.cpp (`-t`) |
| `XARA_RPC_PORT` / `XARA_LLM_PORT` | 50052 / 8081 | Puertos de `rpc-server` y `llama-server` del nodo |

## Protocolo

- **Descubrimiento:** difusión UDP `XARA_DISCOVER` al puerto 8766; el coordinador responde con su puerto HTTP. No cruza routers: si los equipos están en subredes distintas, usar `--coord` una vez.
- **Actualización:** antes de unirse, el equipo descarga `GET /xara.py` del coordinador; si difiere del suyo, lo reemplaza y termina con el código 3 para que `iniciar_xara.bat` lo reinicie.
- **Registro y latido:** `POST /api/registrar` (inventario) y `POST /api/latido` cada 2 s (CPU, RAM, red, batería, RTT del latido anterior). 10 s sin latido = nodo inactivo. Un 404 provoca re-registro.
- **Cola pull:** `GET /api/tarea?node=ID` entrega la siguiente tarea compatible; `POST /api/resultado` la cierra. Cada nodo tiene un hilo solo de control (`control=1`) para arrancar o parar servicios aunque los demás hilos estén ocupados.
- **Túnel RPC (P3):** si el coordinador no llega al `rpc-server` de un equipo (repetidor o segundo router con NAT), el equipo abre conexiones salientes a `GET /api/tunel?node=ID` y el coordinador las une con un puerto local que usa `llama-bench --rpc`. El relevo no tiene tiempo límite porque llama.cpp sube las capas sin respuesta. El informe lo indica en `tunel`.
- **Fotos (P5):** el equipo baja cada original con `GET /fotos/<archivo>` y sube cada versión con `POST /api/foto/<archivo>` (cuerpo binario).
- **Pruebas:** `POST /api/prueba {"prueba": "P1", "P2", "P3", "P3b", "P4" o "P5", "opciones": {...}}`; una a la vez.
- **Consulta:** `GET /api/estado`, `/api/experimentos`, `/api/informe/<id>`, `/api/csv/<tabla>`, `/modelos/<archivo>`, `/motores/<versión>.tar.gz`.

## Pruebas automáticas

| Prueba | Opciones (defecto) | Qué mide | Veredicto |
|---|---|---|---|
| P1 | `tareas=20, segundos=0.5` | Éxito del ciclo enviar→ejecutar→devolver, latencia, AVX2 y MB/s de un núcleo por equipo (zlib, 16 MB) | H-01: ≥ 95 % éxito |
| P2 | `tareas=24, mb=8, rondas=3, repeticiones=3` | Lote zlib determinista: cada nodo solo y todos juntos; repetición 0 descartada | H-02: S ≥ 1,3 y E ≥ 0,8; H-04: desviación de cuota ≤ 10 % |
| P3 y P3b | `modelo, repeticiones=3, n_prompt=64, n_gen=32, timeout_s=1800` | Plan por RAM libre (si no cabe ni entre todos, se detiene con un aviso; si no cabe en el coordinador, no mide el coordinador solo y el informe lo resume en `capacidad`); el equipo con otra versión de llama.cpp copia la del coordinador (`GET /motores/<versión>.tar.gz`), porque RPC exige la misma; `llama-bench` solo en coordinador y luego `--rpc` con `-ts` proporcional y sin mapear el archivo (`-lm none`, o `-mmp 0` en versiones viejas de llama.cpp): con mapeo, el coordinador retiene el modelo entero en memoria (medido: 1017 MB contra 77 MB con un modelo de 0,95 GB). Si el reparto falla, guarda las últimas líneas de cada `rpc.log` en `rpc_log` | H-03: solo < 0,5 tok/s (o no cabe) y repartido ≥ 1,5 tok/s. P3b es la misma prueba con el modelo de 14B |
| P4 | `modelo, n_predict=48, repeticiones=3` | `llama-server` en cada nodo (modelo copiado bajo demanda), preguntas de `prompts.txt` repartidas | H-02 aplicado a preguntas por minuto |
| P5 | `origen="prueba"` o `"carpeta"`, `fotos=120, repeticiones=3` | Una tarea por foto: bajar del coordinador, reducir a 2000 px con Lanczos, enfoque, marca de agua, JPEG q85 + WebP q80 + miniatura 400 px, subir. Las fotos de prueba son JPEG de 12 MP (≈2,7 MB) generados con semilla fija. `por_foto_s` separa bajar, procesar y subir por equipo | H-02 aplicado a fotos por minuto |

## Datos registrados (SQLite `datos/xara.db`)

`nodos` (inventario), `metricas` (cada 2 s, por nodo y prueba), `tareas`, `lotes`, `experimentos` (opciones, resumen JSON, veredicto), `ia` (resultados de llama-bench). Cada tabla se exporta a CSV desde el panel.

## Modelos que descarga `instalar`

Qwen2.5-Instruct de bartowski en Hugging Face: 1.5B Q4_K_M (≈1 GB, P4), 7B Q5_K_M (≈5,4 GB, P3) y 14B Q3_K_L (≈7,9 GB en disco, 7,4 GB en memoria, P3b). Misma familia para que las pruebas sean comparables. El 7B cupo en la PC sola en el P3 real, así que no prueba capacidad. El 14B se eligió con la RAM útil medida en ese P3 (PC 6,6 GB, laptop 1,7 GB, con 1 GB de margen cada una): supera lo útil de la PC y deja ≈1 GB de holgura en la suma. Q4_K_M (8,4 GB) no dejaría holgura y Q3_K_M (6,8 GB) casi cabe en la PC sola. Las URL están en `MODELO_PEQUENO`, `MODELO_GRANDE` y `MODELO_CAPACIDAD`; la del 14B no se pudo comprobar desde el entorno de desarrollo.

## Verificación realizada

En Linux, con coordinador y un segundo nodo simulados en la misma máquina, llama.cpp compilado desde el código fuente (commit 3d65c90) y un modelo de prueba de 80 MB con pesos aleatorios. P1 a P5 terminaron con informe y CSV, y el reparto por RPC funcionó. P3b se probó con un modelo aleatorio de 0,95 GB, `XARA_MARGEN_GB` ajustado para que no cupiera en un nodo pero sí en los dos, y el puerto RPC del segundo nodo bloqueado con iptables para forzar el túnel: terminó con capacidad "Lograda". También se probó el aviso de "no cabe ni entre todos". P5 se probó con un nodo en otro Python sin Pillow (lo instaló solo con pip) y con fotos propias cuyo nombre tiene espacios y ñ. Con dos nodos en la misma máquina, P4 junto sale lento si cada `llama-server` usa todos los núcleos (se compiten); con `XARA_HILOS_IA=2` sale normal. `instalar` se probó contra un servidor local que imita GitHub y Hugging Face, porque desde el entorno de desarrollo esos sitios están bloqueados. **Falta probarlo en las dos máquinas Windows reales, con descargas reales y con un modelo real.** Los números obtenidos en la máquina virtual no son representativos.

## Seguridad

No hay autenticación ni cifrado, y los equipos ejecutan el `xara.py` que les entrega el coordinador. `rpc-server` de llama.cpp tampoco es seguro en redes abiertas. Úsalo solo en la red doméstica, con el perfil de red privada.
