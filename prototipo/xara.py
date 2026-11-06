#!/usr/bin/env python3
"""XARA - prototipo v0.4. Uso: `python xara.py`; el primer equipo que arranca es el coordinador."""
import argparse
import collections
import csv
import importlib
import io
import json
import os
import platform
import queue
import random
import shutil
import site
import socket
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.4"
HTTP_PORT = 8765
DISCOVERY_PORT = 8766
RPC_PORT = 50052
LLM_PORT = 8081
DISCOVERY_MSG = b"XARA_DISCOVER"
LEASE_S = float(os.environ.get("XARA_LEASE_S", 300))   # tarea sin respuesta vuelve a la cola
HEARTBEAT_S = 2.0
NODE_TIMEOUT_S = 10.0
MARGEN_RAM_GB = float(os.environ.get("XARA_MARGEN_GB", 1.0))  # memoria que se deja libre por equipo
# No se usa /releases/latest: la última publicación puede no traer ejecutables para Windows.
LLAMA_VERSIONES = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30"
# Misma familia en los tres tamaños para que P3, P3b y P4 sean comparables (variables del documento, 3.2).
MODELO_PEQUENO = "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
MODELO_GRANDE = "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q5_K_M.gguf"
# P3b: ≈7,4 GB. Supera lo útil de la PC (medido en P3: 6,6 GB) y cabe en la suma con la laptop (≈8,4 GB útiles).
# Q4_K_M (8,4 GB) dejaría a la laptop sin margen.
MODELO_CAPACIDAD = "https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q3_K_L.gguf"

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, "datos")
MOTORES = os.path.join(BASE, "motores")
MODELOS = os.path.join(BASE, "modelos")
FOTOS = os.path.join(BASE, "fotos")
COORD_GUARDADO = os.path.join(DATOS, "coordinador.txt")
CODIGO_ACTUALIZADO = 3  # iniciar_xara.bat vuelve a abrir XARA cuando termina con este código
# Los ejecutables de llama.cpp para Windows dependen de este paquete y un Windows recién instalado no lo trae.
VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
IS_WIN = sys.platform == "win32"
SIN_VENTANA = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW: los procesos hijos no abren consola

try:
    import psutil
except ImportError:
    psutil = None


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=SIN_VENTANA).stdout.strip()
    except Exception:
        return ""


def _ram():
    if psutil:
        vm = psutil.virtual_memory()
        return vm.total, vm.available
    if IS_WIN:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "aev")]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.tp, ms.ap
    try:
        info = dict(l.split(":", 1) for l in open("/proc/meminfo"))
        kb = lambda k: int(info[k].split()[0]) * 1024
        return kb("MemTotal"), kb("MemAvailable")
    except Exception:
        return 0, 0


class CpuMeter:
    def __init__(self):
        self.prev = self._times()

    def _times(self):
        if psutil:
            return None
        if IS_WIN:
            import ctypes
            ft = [ctypes.c_ulonglong() for _ in range(3)]
            ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
            idle, kernel, user = (f.value for f in ft)
            return idle, kernel + user
        try:
            v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
            return v[3] + v[4], sum(v)
        except Exception:
            return None

    def percent(self):
        if psutil:
            return psutil.cpu_percent(interval=None)
        cur = self._times()
        if not cur or not self.prev:
            return None
        di, dt = cur[0] - self.prev[0], cur[1] - self.prev[1]
        self.prev = cur
        return round(100 * (1 - di / dt), 1) if dt > 0 else None


def _gpus():
    if IS_WIN:
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json"])
        try:
            data = json.loads(out)
            return [{"nombre": g.get("Name"), "vram_gb": round((g.get("AdapterRAM") or 0) / 2**30, 1)}
                    for g in (data if isinstance(data, list) else [data])]
        except Exception:
            return []
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    return [{"nombre": l} for l in out.splitlines()] if out else []


def _cpu_name():
    if IS_WIN:
        return _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]) \
            or platform.processor()
    try:
        for l in open("/proc/cpuinfo"):
            if l.startswith("model name"):
                return l.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor()


def _avx2():
    if IS_WIN:
        try:
            import ctypes
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
        except Exception:
            return None
    try:
        return " avx2" in open("/proc/cpuinfo").read()
    except Exception:
        return None


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def hilos_ia():
    """Hilos para llama.cpp: núcleos físicos (los hilos extra no aceleran y compiten entre sí)."""
    return int(os.environ.get("XARA_HILOS_IA", 0)) or (psutil.cpu_count(logical=False) if psutil else None) \
        or os.cpu_count() or 2


def find_exe(*names):
    wanted = {n + (".exe" if IS_WIN else "") for n in names}
    for root, _, files in os.walk(MOTORES, followlinks=True):
        for f in files:
            if f in wanted:
                return os.path.join(root, f)
    return None


def motores():
    return {"rpc": find_exe("rpc-server", "ggml-rpc-server"),
            "bench": find_exe("llama-bench"),
            "server": find_exe("llama-server")}


def version_llama():
    """Nombre de la carpeta de motores/ donde está llama.cpp (instalar la nombra con la versión, por ejemplo b6123)."""
    exe = find_exe("rpc-server", "ggml-rpc-server")
    return os.path.relpath(exe, MOTORES).split(os.sep)[0] if exe else None


def modelos():
    os.makedirs(MODELOS, exist_ok=True)
    return {f: round(os.path.getsize(os.path.join(MODELOS, f)) / 2**30, 3)
            for f in sorted(os.listdir(MODELOS)) if f.endswith(".gguf")}


def descargar(url, path):
    """Descarga a un archivo .part y lo renombra al final, para no dejar archivos a medias."""
    n, aviso = 0, 0
    with urllib.request.urlopen(url, timeout=60) as r, open(path + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        while chunk := r.read(1 << 20):
            f.write(chunk)
            n += len(chunk)
            if total and n * 10 // total > aviso:
                aviso = n * 10 // total
                log(f"  {os.path.basename(path)}: {aviso * 10} %")
    os.replace(path + ".part", path)
    return n


def inventory():
    total, avail = _ram()
    disks = {}
    for r in ([f"{d}:\\" for d in "CDEFG"] if IS_WIN else [BASE]):
        if os.path.exists(r):
            u = shutil.disk_usage(r)
            disks[r] = {"total_gb": round(u.total / 2**30, 1), "libre_gb": round(u.free / 2**30, 1)}
    return {
        "host": socket.gethostname(), "ip": local_ip(),
        "so": f"{platform.system()} {platform.release()}",
        "cpu": _cpu_name(), "nucleos_logicos": os.cpu_count(),
        "nucleos_fisicos": psutil.cpu_count(logical=False) if psutil else None,
        "avx2": _avx2(),
        "ram_total_gb": round(total / 2**30, 2), "ram_libre_gb": round(avail / 2**30, 2),
        "gpus": _gpus(), "discos": disks, "python": platform.python_version(),
        "psutil": bool(psutil), "motores": {k: bool(v) for k, v in motores().items()},
        "modelos": modelos(), "xara": VERSION,
    }


def sample(cpu):
    total, avail = _ram()
    m = {"cpu_pct": cpu.percent(), "ram_usada_gb": round((total - avail) / 2**30, 2),
         "ram_libre_gb": round(avail / 2**30, 2), "red_env_mb": None, "red_rec_mb": None, "en_bateria": None}
    if psutil:
        n = psutil.net_io_counters()
        m["red_env_mb"], m["red_rec_mb"] = round(n.bytes_sent / 2**20, 2), round(n.bytes_recv / 2**20, 2)
        try:
            b = psutil.sensors_battery()
            m["en_bateria"] = None if b is None else (not b.power_plugged)
        except Exception:
            pass
    return m


def unir(a, b):
    """Copia bytes entre dos conexiones, en ambos sentidos, hasta que una se cierre."""
    def copiar(origen, destino):
        try:
            while datos := origen.recv(1 << 16):
                destino.sendall(datos)
        except OSError:
            pass
        for s in (origen, destino):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    for s in (a, b):
        s.settimeout(None)  # llama.cpp sube las capas sin esperar respuesta: un sentido puede quedar callado minutos
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # llama.cpp RPC manda muchos mensajes pequeños
    t = threading.Thread(target=copiar, args=(b, a), daemon=True)
    t.start()
    copiar(a, b)
    t.join()
    a.close()
    b.close()


def ultimas_lineas(nombre, n=15):
    try:
        with open(os.path.join(DATOS, "logs", f"{nombre}.log"), errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


class NodeServices:
    """Procesos auxiliares que un equipo arranca por orden del coordinador (llama.cpp)."""

    def __init__(self, coord_base):
        self.coord_base = coord_base
        self.procs = {}
        self.rpc_port = int(os.environ.get("XARA_RPC_PORT", RPC_PORT))
        self.llm_port = int(os.environ.get("XARA_LLM_PORT", LLM_PORT))
        self.tunel_fin = threading.Event()
        self.tunel_espera = None

    def _start(self, name, args):
        self.stop(name)
        out = open(os.path.join(DATOS, "logs", f"{name}.log"), "w")
        self.procs[name] = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT,
                                            creationflags=SIN_VENTANA)
        return self.procs[name]

    def stop(self, name):
        p = self.procs.pop(name, None)
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        return {"detenido": name}

    def rpc_start(self, params):
        if params["version"] != version_llama():
            self.fetch_llama(params["version"])
        exe = find_exe("rpc-server", "ggml-rpc-server")
        if not exe:
            raise RuntimeError("Falta llama.cpp en la carpeta motores/ de este equipo")
        port = self.rpc_port
        args = [exe, "-H", "0.0.0.0", "-p", str(port), "-t", str(hilos_ia())]
        if params.get("cache", True):
            args.append("-c")
        p = self._start("rpc", args)
        for _ in range(50):
            if p.poll() is not None:
                raise RuntimeError("rpc-server se cerró al arrancar (ver datos/logs/rpc.log)")
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                return {"ip": local_ip(), "port": port}
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("rpc-server no respondió")

    def rpc_tunel(self, params):
        """Con un repetidor en medio el coordinador no puede llegar a este equipo; entonces es el equipo quien abre las conexiones."""
        self.cerrar_tunel()
        self.tunel_fin = threading.Event()
        threading.Thread(target=self._tunel_loop, args=(params["node"], self.tunel_fin), daemon=True).start()
        return {"tunel": True}

    def _tunel_loop(self, nid, fin):
        coord = urllib.parse.urlsplit(self.coord_base)
        while not fin.is_set():
            try:
                s = socket.create_connection((coord.hostname, coord.port), 10)
                s.settimeout(None)
                self.tunel_espera = s
                s.sendall(f"GET /api/tunel?node={nid} HTTP/1.0\r\n\r\n".encode())
                recibido = b""
                while b"\r\n\r\n" not in recibido:
                    parte = s.recv(1024)
                    if not parte:
                        raise OSError("el coordinador cerró el túnel")
                    recibido += parte
                primero = recibido.split(b"\r\n\r\n", 1)[1] or s.recv(1 << 16)  # espera a que llama.cpp lo use
                if not primero:
                    raise OSError("el coordinador cerró el túnel")
                rpc = socket.create_connection(("127.0.0.1", self.rpc_port), 10)
                rpc.sendall(primero)
            except OSError:
                fin.wait(1)
                continue
            threading.Thread(target=unir, args=(s, rpc), daemon=True).start()

    def cerrar_tunel(self):
        self.tunel_fin.set()
        if self.tunel_espera:
            try:
                self.tunel_espera.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def fetch_model(self, name):
        """Descarga el modelo desde el coordinador si este equipo no lo tiene (archivos bajo demanda)."""
        path = os.path.join(MODELOS, name)
        if os.path.exists(path):
            return path, 0, 0.0
        os.makedirs(MODELOS, exist_ok=True)
        t0 = time.time()
        n = descargar(f"{self.coord_base}/modelos/{urllib.request.quote(name)}", path)
        return path, n, time.time() - t0

    def fetch_llama(self, version):
        """Copia llama.cpp del coordinador: el reparto por RPC exige la misma versión en todos los equipos."""
        carpeta = os.path.join(MOTORES, version)
        archivo = carpeta + ".tar.gz"  # tar y no zip: conserva el permiso de ejecución en Linux
        descargar(f"{self.coord_base}/motores/{urllib.request.quote(version)}.tar.gz", archivo)
        shutil.unpack_archive(archivo, carpeta)
        os.remove(archivo)
        for vieja in os.listdir(MOTORES):
            if vieja != version:
                shutil.rmtree(os.path.join(MOTORES, vieja), ignore_errors=True)
        if version_llama() != version:
            raise RuntimeError(f"No se pudo cambiar llama.cpp a la versión {version}: borra la carpeta motores de este equipo")

    def llm_start(self, params):
        exe = find_exe("llama-server")
        if not exe:
            raise RuntimeError("Falta llama-server en motores/ de este equipo")
        path, nbytes, secs = self.fetch_model(params["modelo"])
        port = self.llm_port
        t0 = time.time()
        p = self._start("llm", [exe, "-m", path, "--host", "127.0.0.1", "--port", str(port),
                                "-c", str(params.get("contexto", 2048)), "-np", "1", "-t", str(hilos_ia())])
        for _ in range(int(params.get("espera_s", 600) / 0.5)):
            if p.poll() is not None:
                raise RuntimeError("llama-server se cerró al arrancar (ver datos/logs/llm.log)")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                    if r.status == 200:
                        return {"port": port, "descarga_mb": round(nbytes / 2**20, 1),
                                "descarga_s": round(secs, 1), "carga_s": round(time.time() - t0, 1)}
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        raise RuntimeError("llama-server no quedó listo a tiempo")

    def foto(self, params):
        """Baja la foto del coordinador, la procesa y le devuelve los resultados; mide cuánto tarda cada parte."""
        t0 = time.perf_counter()
        with urllib.request.urlopen(f"{self.coord_base}/fotos/{urllib.request.quote(params['foto'])}", timeout=120) as r:
            datos = r.read()
        t1 = time.perf_counter()
        salidas = procesar_foto(datos)
        t2 = time.perf_counter()
        nombre = os.path.splitext(params["foto"])[0]
        for sufijo, contenido in salidas.items():
            req = urllib.request.Request(f"{self.coord_base}/api/foto/{urllib.request.quote(f'{nombre}_{sufijo}')}",
                                         contenido, {"Content-Type": "application/octet-stream"})
            urllib.request.urlopen(req, timeout=120).close()
        t3 = time.perf_counter()
        return {"bajar_s": round(t1 - t0, 3), "procesar_s": round(t2 - t1, 3), "subir_s": round(t3 - t2, 3),
                "mb_bajados": round(len(datos) / 2**20, 3),
                "mb_subidos": round(sum(len(c) for c in salidas.values()) / 2**20, 3)}

    def run(self, kind, params):
        if kind == "cpu":
            return task_cpu(params)
        if kind == "sleep":
            time.sleep(float(params.get("s", 1)))
            return {"s": params.get("s", 1)}
        if kind == "llm":
            return task_llm({**params, "port": self.llm_port})
        if kind == "rpc_start":
            return self.rpc_start(params)
        if kind == "rpc_tunel":
            return self.rpc_tunel(params)
        if kind == "rpc_stop":
            self.cerrar_tunel()
            return {**self.stop("rpc"), "log": ultimas_lineas("rpc")}
        if kind == "llm_start":
            return self.llm_start(params)
        if kind == "llm_stop":
            return self.stop("llm")
        if kind == "foto":
            return self.foto(params)
        if kind == "fotos_preparar":
            return preparar_pillow()
        raise ValueError(f"tipo de tarea desconocido: {kind}")


def task_cpu(params):
    """Compresión determinista de datos (representa "procesar muchos archivos")."""
    mb, rounds = int(params.get("mb", 8)), int(params.get("rounds", 3))
    raw = random.Random(str(params.get("seed", "xara"))).randbytes(mb * 2**20)
    data = raw.translate(bytes(b"abcdefghijklmnop"[i % 16] for i in range(256)))
    size = 0
    for _ in range(rounds):
        size = len(zlib.compress(data, 6))
    return {"mb": mb * rounds, "comprimido": size}


def task_llm(params):
    body = json.dumps({"prompt": params["prompt"], "n_predict": int(params.get("n_predict", 64)),
                       "temperature": 0, "seed": 42, "cache_prompt": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{params.get('port', LLM_PORT)}/completion", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.load(r)
    t = out.get("timings", {})
    return {"tokens": t.get("predicted_n"), "tok_s": t.get("predicted_per_second"),
            "texto": out.get("content", "")[:200]}


def preparar_pillow():
    """P5 procesa las fotos con Pillow; un Windows recién instalado no lo trae, así que se instala solo."""
    try:
        import PIL
        return {"pillow": PIL.__version__, "instalado_ahora": False}
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "--disable-pip-version-check",
                    "pillow"], check=True, timeout=900, creationflags=SIN_VENTANA)
    site.addsitedir(site.getusersitepackages())  # la carpeta de usuario puede no existir cuando arrancó Python
    importlib.invalidate_caches()
    import PIL
    return {"pillow": PIL.__version__, "instalado_ahora": True}


def lista_fotos(carpeta):
    return sorted(f for f in os.listdir(carpeta) if f.lower().endswith((".jpg", ".jpeg", ".png")))


def generar_foto(path, semilla):
    """Foto de 12 megapíxeles (≈2,7 MB en JPEG, como la de un celular): manchas de color, formas y grano."""
    from PIL import Image, ImageDraw
    r = random.Random(semilla)
    foto = Image.frombytes("RGB", (8, 6), r.randbytes(8 * 6 * 3)).resize((4000, 3000), Image.BICUBIC)
    dibujo = ImageDraw.Draw(foto)
    for _ in range(25):
        x, y = r.randrange(4000), r.randrange(3000)
        dibujo.ellipse((x, y, x + r.randrange(100, 900), y + r.randrange(100, 900)),
                       fill=tuple(r.randrange(256) for _ in range(3)))
    grano = Image.effect_noise((4000, 3000), 40).convert("RGB")
    Image.blend(foto, grano, 0.12).save(path + ".part", "JPEG", quality=90)
    os.replace(path + ".part", path)


def procesar_foto(datos):
    """Lo que hace una tienda con cada foto antes de publicarla: versión web con marca de agua, WebP y miniatura."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
    with Image.open(io.BytesIO(datos)) as im:
        foto = ImageOps.exif_transpose(im).convert("RGB")
    foto.thumbnail((2000, 2000), Image.LANCZOS)
    foto = foto.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    ImageDraw.Draw(foto).text((30, foto.height - 80), "XARA", fill="white", font=ImageFont.load_default(48))
    mini = foto.copy()
    mini.thumbnail((400, 400), Image.LANCZOS)
    salidas = {}
    for nombre, imagen, formato, opciones in (("web.jpg", foto, "JPEG", {"quality": 85, "optimize": True, "progressive": True}),
                                              ("tienda.webp", foto, "WEBP", {"quality": 80}),
                                              ("mini.jpg", mini, "JPEG", {"quality": 80})):
        buf = io.BytesIO()
        imagen.save(buf, formato, **opciones)
        salidas[nombre] = buf.getvalue()
    return salidas


def _http(base, path, obj=None, timeout=30):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(base + path, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, (json.load(r) if r.status != 204 else None)


def discover(timeout=1.0, tries=2):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(timeout)
    for _ in range(tries):
        for target in ("255.255.255.255", "127.0.0.1"):
            try:
                s.sendto(DISCOVERY_MSG, (target, DISCOVERY_PORT))
                data, addr = s.recvfrom(1024)
                return f"{addr[0]}:{json.loads(data)['port']}"
            except (socket.timeout, OSError):
                continue
    return None


class Node:
    def __init__(self, coord, workers):
        self.base = f"http://{coord}"
        self.workers = workers
        self.id = None
        self.services = NodeServices(self.base)
        self.stop = threading.Event()

    def register(self):
        info = inventory()
        info["hilos_xara"] = self.workers
        _, r = _http(self.base, "/api/registrar", {"info": info, "node_id": self.id})
        self.id = r["node_id"]
        log(f"[equipo] conectado al coordinador {self.base} como {info['host']} ({self.id})")

    def heartbeat_loop(self):
        cpu, rtt = CpuMeter(), None
        while not self.stop.is_set():
            m = sample(cpu)
            m["latencia_ms"] = rtt
            t0 = time.perf_counter()
            try:
                _http(self.base, "/api/latido", {"node_id": self.id, "m": m}, timeout=5)
                rtt = round((time.perf_counter() - t0) * 1000, 2)
            except urllib.error.HTTPError as e:
                if e.code == 404:  # el coordinador se reinició: volver a registrarse
                    self.register()
            except (urllib.error.URLError, OSError):
                rtt = None
            self.stop.wait(HEARTBEAT_S)

    def worker_loop(self, control_only=False):
        while not self.stop.is_set():
            try:
                code, task = _http(self.base, f"/api/tarea?node={self.id}&control={int(control_only)}")
            except (urllib.error.URLError, OSError):
                time.sleep(2)
                continue
            if code == 204:
                time.sleep(0.2)
                continue
            t0 = time.perf_counter()
            try:
                out, ok, err = self.services.run(task["kind"], task["params"]), True, ""
            except Exception as e:
                out, ok, err = None, False, f"{type(e).__name__}: {e}"
            res = {"task_id": task["id"], "node_id": self.id, "ok": ok, "output": out, "error": err,
                   "t_ejec_s": round(time.perf_counter() - t0, 4)}
            for _ in range(5):
                try:
                    _http(self.base, "/api/resultado", res)
                    break
                except (urllib.error.URLError, OSError):
                    time.sleep(2)

    def run(self):
        self.register()
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        # un hilo reservado para órdenes de control (arrancar llama.cpp) aunque los demás estén ocupados
        threading.Thread(target=self.worker_loop, args=(True,), daemon=True).start()
        for _ in range(self.workers):
            threading.Thread(target=self.worker_loop, daemon=True).start()


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodos(id TEXT PRIMARY KEY, host TEXT, ip TEXT, inventario TEXT,
    primera_vez REAL, ultima_vez REAL);
CREATE TABLE IF NOT EXISTS metricas(ts REAL, nodo TEXT, host TEXT, cpu_pct REAL, ram_usada_gb REAL,
    ram_libre_gb REAL, red_env_mb REAL, red_rec_mb REAL, latencia_ms REAL, en_bateria INTEGER, experimento TEXT);
CREATE TABLE IF NOT EXISTS tareas(id TEXT, lote TEXT, experimento TEXT, tipo TEXT, nodo TEXT, host TEXT,
    ok INTEGER, t_envio REAL, t_recibido REAL, t_ejec_s REAL, reintentos INTEGER, error TEXT, salida TEXT);
CREATE TABLE IF NOT EXISTS lotes(id TEXT PRIMARY KEY, experimento TEXT, etiqueta TEXT, tipo TEXT,
    nodos TEXT, total INTEGER, ok INTEGER, fallidas INTEGER, inicio REAL, fin REAL, duracion_s REAL, por_nodo TEXT);
CREATE TABLE IF NOT EXISTS experimentos(id TEXT PRIMARY KEY, prueba TEXT, inicio REAL, fin REAL,
    estado TEXT, parametros TEXT, resumen TEXT, veredicto TEXT);
CREATE TABLE IF NOT EXISTS ia(experimento TEXT, configuracion TEXT, modelo TEXT, modelo_gb REAL,
    reparto TEXT, pp_tok_s REAL, tg_tok_s REAL, tg_desv REAL, carga_s REAL, ok INTEGER, error TEXT, ts REAL);
"""


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.executescript(SCHEMA)
        self.lock = threading.Lock()

    def exec(self, sql, args=()):
        with self.lock:
            self.c.execute(sql, args)
            self.c.commit()

    def query(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def csv(self, table):
        rows = self.query(f"SELECT * FROM {table}")
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return buf.getvalue()


class Coordinator:
    def __init__(self):
        self.db = DB(os.path.join(DATOS, "xara.db"))
        self.lock = threading.Lock()
        self.nodes = {}
        self.pending = collections.deque()
        self.leased = {}
        self.batches = {}
        self.exp = None          # experimento en curso
        self.exp_log = []
        self.tuneles = {}        # equipo -> conexiones de llama.cpp que esperan un túnel abierto por ese equipo
        self.fotos_origen = None   # carpeta que reparte P5 y carpeta donde guarda lo que devuelven los equipos
        self.fotos_destino = None

    def active_nodes(self):
        now = time.time()
        with self.lock:
            return {k: v for k, v in self.nodes.items() if now - v["ultimo"] < NODE_TIMEOUT_S}

    def register(self, data, addr):
        nid = data.get("node_id") or uuid.uuid4().hex[:8]
        info = data["info"]
        with self.lock:
            local = addr.startswith("127.") and not any(n.get("local") for k, n in self.nodes.items() if k != nid)
            self.nodes[nid] = {"info": info, "ultimo": time.time(), "m": {}, "local": local}
        self.db.exec("INSERT OR REPLACE INTO nodos VALUES(?,?,?,?,COALESCE((SELECT primera_vez FROM nodos WHERE id=?),?),?)",
                     (nid, info.get("host"), info.get("ip"), json.dumps(info), nid, time.time(), time.time()))
        log(f"[coord] equipo conectado: {info.get('host')} {info.get('ip')} ({nid})")
        return nid

    def heartbeat(self, data):
        nid = data["node_id"]
        with self.lock:
            n = self.nodes.get(nid)
            if not n:
                return False
            n["ultimo"], n["m"] = time.time(), data["m"]
            host = self.host(nid)
        m = data["m"]
        self.db.exec("INSERT INTO metricas VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (time.time(), nid, host, m.get("cpu_pct"), m.get("ram_usada_gb"), m.get("ram_libre_gb"),
                      m.get("red_env_mb"), m.get("red_rec_mb"), m.get("latencia_ms"), m.get("en_bateria"),
                      self.exp["id"] if self.exp else None))
        self.db.exec("UPDATE nodos SET ultima_vez=? WHERE id=?", (time.time(), nid))
        return True

    def submit(self, kind, params_list, nodos=None, etiqueta="", control=False):
        bid = uuid.uuid4().hex[:8]
        with self.lock:
            self.batches[bid] = {"id": bid, "kind": kind, "etiqueta": etiqueta, "total": len(params_list),
                                 "ok": 0, "fallidas": 0, "inicio": time.time(), "fin": None, "por_nodo": {},
                                 "nodos": nodos, "resultados": [], "evento": threading.Event()}
            for i, p in enumerate(params_list):
                self.pending.append({"id": f"{bid}-{i}", "batch": bid, "kind": kind, "params": p,
                                     "nodos": nodos, "control": control})
        return bid

    def next_task(self, node, control_only):
        now = time.time()
        with self.lock:
            for tid, (task, n, t0) in list(self.leased.items()):
                if now - t0 > LEASE_S:          # plazo vencido: la tarea vuelve a la cola
                    del self.leased[tid]
                    task["reintentos"] = task.get("reintentos", 0) + 1
                    self.pending.appendleft(task)
            for i, task in enumerate(self.pending):
                if task["nodos"] and node not in task["nodos"]:
                    continue
                if control_only and not task["control"]:
                    continue
                del self.pending[i]
                task["t_envio"] = now
                self.leased[task["id"]] = (task, node, now)
                return task
        return None

    def result(self, d):
        with self.lock:
            lease = self.leased.pop(d["task_id"], None)
            if lease is None:
                return
            task = lease[0]
            b = self.batches[task["batch"]]
            host = self.host(d["node_id"])
            b["ok" if d["ok"] else "fallidas"] += 1
            pn = b["por_nodo"].setdefault(host, {"tareas": 0, "t_ejec_s": 0.0})
            pn["tareas"] += 1
            pn["t_ejec_s"] = round(pn["t_ejec_s"] + d["t_ejec_s"], 3)
            b["resultados"].append(d)
            done = b["ok"] + b["fallidas"] == b["total"]
            if done:
                b["fin"] = time.time()
                b["duracion_s"] = round(b["fin"] - b["inicio"], 3)
        exp = self.exp["id"] if self.exp else None
        self.db.exec("INSERT INTO tareas VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (task["id"], task["batch"], exp, task["kind"], d["node_id"], host, int(d["ok"]),
                      task["t_envio"], time.time(), d["t_ejec_s"], task.get("reintentos", 0), d.get("error", ""),
                      json.dumps(d.get("output"), ensure_ascii=False)[:500]))
        if done:
            self.db.exec("INSERT OR REPLACE INTO lotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (b["id"], exp, b["etiqueta"], b["kind"], json.dumps(b["nodos"]), b["total"], b["ok"],
                          b["fallidas"], b["inicio"], b["fin"], b["duracion_s"], json.dumps(b["por_nodo"])))
            b["evento"].set()

    def run_batch(self, kind, params_list, nodos=None, etiqueta="", control=False, timeout=None):
        bid = self.submit(kind, params_list, nodos, etiqueta, control)
        b = self.batches[bid]
        if not b["evento"].wait(timeout):
            raise TimeoutError(f"el lote {etiqueta} no terminó a tiempo")
        return b

    def control(self, node, kind, params=None, timeout=900):
        b = self.run_batch(kind, [params or {}], nodos=[node], etiqueta=f"control:{kind}", control=True,
                           timeout=timeout)
        r = b["resultados"][0]
        if not r["ok"]:
            raise RuntimeError(f"{self.host(node)}: {r['error']}")
        return r["output"]

    def host(self, nid):
        """Nombre del equipo; si dos equipos se llaman igual, se añade parte de su id."""
        h = self.nodes.get(nid, {}).get("info", {}).get("host", nid)
        if sum(1 for n in self.nodes.values() if n["info"].get("host") == h) > 1:
            h = f"{h}-{nid[:4]}"
        return h

    def start_experiment(self, prueba, opciones):
        if self.exp and self.exp["estado"] == "en curso":
            raise RuntimeError("Ya hay una prueba en curso")
        fn = {"P1": exp_p1, "P2": exp_p2, "P3": exp_p3, "P3b": exp_p3, "P4": exp_p4, "P5": exp_p5}.get(prueba)
        if not fn:
            raise ValueError("Prueba desconocida")
        eid = time.strftime("%Y%m%d-%H%M%S") + "-" + prueba
        self.exp = {"id": eid, "prueba": prueba, "estado": "en curso", "inicio": time.time(), "paso": "iniciando"}
        self.exp_log = []
        self.db.exec("INSERT INTO experimentos VALUES(?,?,?,?,?,?,?,?)",
                     (eid, prueba, time.time(), None, "en curso", json.dumps(opciones), None, None))

        def runner():
            try:
                resumen, veredicto = fn(self, **opciones)
                estado = "terminado"
            except Exception as e:
                resumen, veredicto, estado = {"error": f"{type(e).__name__}: {e}"}, "Inválido", "error"
                self.step(f"ERROR: {e}")
            self.exp["estado"] = estado
            self.db.exec("UPDATE experimentos SET fin=?, estado=?, resumen=?, veredicto=? WHERE id=?",
                         (time.time(), estado, json.dumps(resumen, ensure_ascii=False), veredicto, eid))
            write_report(self, eid)
            self.step(f"Terminado: {veredicto}")

        threading.Thread(target=runner, daemon=True).start()
        return eid

    def step(self, text):
        log(f"[prueba] {text}")
        if self.exp:
            self.exp["paso"] = text
        self.exp_log.append(time.strftime("%H:%M:%S ") + text)


def _nodes_or_fail(c, minimo=1):
    nodes = c.active_nodes()
    if len(nodes) < minimo:
        raise RuntimeError(f"Se necesitan al menos {minimo} equipos conectados")
    return nodes


def _cv(xs):
    return round(100 * statistics.pstdev(xs) / statistics.mean(xs), 1) if len(xs) > 1 and statistics.mean(xs) else 0.0


def _speedup(c, kind, make_params, nodes, reps, etiqueta):
    """Ejecuta el mismo lote en cada equipo solo y luego en todos. Calcula aceleración y eficiencia."""
    dur = collections.defaultdict(list)
    cuotas = collections.defaultdict(list)
    configs = [(nid, [nid]) for nid in nodes] + [("todos", list(nodes))]
    for rep in range(reps + 1):                       # la repetición 0 es de calentamiento y se descarta
        for name, allowed in configs:
            label = f"{etiqueta}:{'todos' if name == 'todos' else c.host(name)}:r{rep}"
            c.step(f"Lote {label}")
            b = c.run_batch(kind, make_params(), nodos=allowed, etiqueta=label, timeout=3600)
            if b["fallidas"]:
                raise RuntimeError(f"{b['fallidas']} tareas fallaron en {label}")
            if rep == 0:
                continue
            dur[name].append(b["duracion_s"])
            if name == "todos":
                for host, v in b["por_nodo"].items():
                    cuotas[host].append(v["tareas"] / b["total"])
    med = {k: statistics.median(v) for k, v in dur.items()}
    singles = {c.host(n): med[n] for n in nodes}
    n_tasks = len(make_params())
    x = {h: n_tasks / t for h, t in singles.items()}            # rendimiento individual (tareas/s)
    best = min(singles.values())
    s = best / med["todos"]
    s_ideal = sum(x.values()) / max(x.values())
    e = s / s_ideal
    esperada = {h: x[h] / sum(x.values()) for h in x}
    real = {h: statistics.mean(cuotas.get(h, [0])) for h in x}
    desvio = max(abs(real[h] - esperada[h]) for h in x)
    return {
        "duracion_mediana_s": {**singles, "todos": med["todos"]},
        "aceleracion": round(s, 3), "aceleracion_ideal": round(s_ideal, 3), "eficiencia": round(e, 3),
        "cuota_esperada": {h: round(v, 3) for h, v in esperada.items()},
        "cuota_real": {h: round(v, 3) for h, v in real.items()},
        "desvio_cuota_max": round(desvio, 3), "variacion_pct": _cv(dur["todos"]), "repeticiones": reps,
    }


def _veredicto_h2(r):
    if r["variacion_pct"] > 15:
        return "No concluyente"
    if r["aceleracion"] >= 1.3 and r["eficiencia"] >= 0.8:
        return "Favorable"
    if r["aceleracion"] < 1.1:
        return "Desfavorable"
    return "Técnicamente viable"


def exp_p1(c, tareas=20, segundos=0.5):
    nodes = _nodes_or_fail(c, 2)
    c.step(f"Enviando {tareas} tareas de prueba a {len(nodes)} equipos")
    t0 = time.time()
    b = c.run_batch("sleep", [{"s": segundos}] * tareas, etiqueta="P1", timeout=600)
    exito = 100 * b["ok"] / b["total"]
    velocidad = {}
    for nid, n in nodes.items():
        c.step(f"Midiendo la velocidad de un núcleo de {c.host(nid)}")
        t = c.run_batch("cpu", [{"mb": 8, "rounds": 2, "seed": "P1"}], nodos=[nid],
                        etiqueta=f"P1:velocidad:{c.host(nid)}", timeout=600)["resultados"][0]
        velocidad[c.host(nid)] = {"avx2": n["info"].get("avx2"),
                                  "mb_s_por_nucleo": round(t["output"]["mb"] / t["t_ejec_s"], 1) if t["ok"] else None}
    # se consulta al final porque el lote suele durar menos que un latido y aún no habría mediciones
    lat = c.db.query("SELECT host, AVG(latencia_ms) m, MAX(latencia_ms) x FROM metricas WHERE ts>=? "
                     "AND latencia_ms IS NOT NULL GROUP BY host", (t0,))
    res = {"exito_pct": exito, "por_equipo": b["por_nodo"], "duracion_s": b["duracion_s"],
           "latencia_ms": {r["host"]: {"media": round(r["m"], 2), "max": round(r["x"], 2)} for r in lat},
           "equipos_que_participaron": len(b["por_nodo"]), "velocidad_cpu": velocidad}
    ver = "Favorable" if exito >= 95 and len(b["por_nodo"]) >= 2 else ("Desfavorable" if exito < 80 else "Técnicamente viable")
    return res, ver


def exp_p2(c, tareas=24, mb=8, rondas=3, repeticiones=3):
    nodes = _nodes_or_fail(c, 2)
    make = lambda: [{"mb": mb, "rounds": rondas, "seed": f"t{i}"} for i in range(tareas)]
    r = _speedup(c, "cpu", make, nodes, repeticiones, "P2")
    v2 = _veredicto_h2(r)
    v4 = "Favorable" if r["desvio_cuota_max"] <= 0.10 else ("Desfavorable" if r["desvio_cuota_max"] > 0.30 else "Técnicamente viable")
    r["veredicto_H02"], r["veredicto_H04"] = v2, v4
    return r, v2


def _plan_modelo(c, modelo_gb, local):
    """Decide la técnica según memoria libre (criterio de exo: total suficiente, reparto proporcional)."""
    nodes = c.active_nodes()
    libre = {nid: max(0.0, (n["m"].get("ram_libre_gb") or n["info"]["ram_libre_gb"]) - MARGEN_RAM_GB)
             for nid, n in nodes.items()}
    if libre.get(local, 0) >= modelo_gb:
        tecnica = "un solo equipo"
    elif sum(libre.values()) >= modelo_gb:
        tecnica = "repartir por capas"
    else:
        tecnica = "no cabe"
    total = sum(libre.values()) or 1
    reparto = {nid: round(v / total, 3) for nid, v in libre.items()}
    return tecnica, libre, reparto


def _bench(exe, model, extra, reps, n_prompt, n_gen, timeout):
    args = [exe, "-m", model, "-p", str(n_prompt), "-n", str(n_gen), "-r", str(reps), "-o", "json"] + extra
    t0 = time.time()
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                       creationflags=SIN_VENTANA)
    secs = time.time() - t0
    if p.returncode != 0:
        salida = (p.stderr or p.stdout or "").strip().splitlines()
        with open(os.path.join(DATOS, "logs", "bench.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(salida))
        # en Linux, tras el error vienen líneas de depuración; interesa la línea del error
        claves = [l for l in salida if "error" in l.lower() or "abort" in l.lower()]
        raise RuntimeError((claves or salida or ["falló llama-bench"])[-1])
    data = json.loads(p.stdout[p.stdout.index("["):])
    pp = next((d for d in data if d.get("n_prompt") and not d.get("n_gen")), {})
    tg = next((d for d in data if d.get("n_gen") and not d.get("n_prompt")), {})
    return {"pp_tok_s": pp.get("avg_ts"), "tg_tok_s": tg.get("avg_ts"), "tg_desv": tg.get("stddev_ts"),
            "total_s": round(secs, 1)}


def _sin_mmap(exe):
    """Opción de llama-bench para no mapear el modelo; cambió de nombre entre versiones de llama.cpp."""
    ayuda = _run([exe, "--help"])
    if "--load-mode" in ayuda:
        return ["-lm", "none"]
    return ["-mmp", "0"] if "--mmap" in ayuda else []


def _alcanzable(ip, port):
    try:
        socket.create_connection((ip, port), 3).close()
        return True
    except OSError:
        return False


def _abrir_tunel(c, nid):
    """Puerto local para llama.cpp; cada conexión espera a que el equipo abra un túnel hacia /api/tunel."""
    srv = socket.create_server(("127.0.0.1", 0))
    c.tuneles[nid] = esperando = queue.Queue()

    def aceptar():
        try:
            while True:
                esperando.put(srv.accept()[0])
        except OSError:
            pass

    threading.Thread(target=aceptar, daemon=True).start()
    return srv


def exp_p3(c, modelo, repeticiones=3, n_prompt=64, n_gen=32, timeout_s=1800):
    nodes = _nodes_or_fail(c, 2)
    local = next((nid for nid, n in nodes.items() if n.get("local")), None)
    if local is None:
        raise RuntimeError("El coordinador debe participar también como equipo")
    exe = find_exe("llama-bench")
    version = version_llama()
    path = os.path.join(MODELOS, modelo)
    if not exe or not version or not os.path.exists(path):
        raise RuntimeError("Faltan llama.cpp o el modelo en el coordinador (carpetas motores/ y modelos/)")
    gb = os.path.getsize(path) / 2**30
    tecnica, libre, reparto = _plan_modelo(c, gb, local)
    c.step(f"Modelo {modelo} ({gb:.2f} GB). Plan automático: {tecnica}. Libre útil: "
           + ", ".join(f"{c.host(k)} {v:.1f} GB" for k, v in libre.items()))
    if tecnica == "no cabe":
        raise RuntimeError(f"El modelo ({gb:.1f} GB) no cabe ni entre todos los equipos ({sum(libre.values()):.1f} GB "
                           "útiles). Cierra los demás programas, sobre todo el navegador, y repite la prueba")
    filas = {}

    def guardar(conf, r, rep_txt, err=None):
        c.db.exec("INSERT INTO ia VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (c.exp["id"], conf, modelo, round(gb, 3), rep_txt, r.get("pp_tok_s"), r.get("tg_tok_s"),
                   r.get("tg_desv"), r.get("total_s"), int(err is None), err, time.time()))
        filas[conf] = {**r, "error": err}

    if tecnica == "repartir por capas":
        c.step("El modelo no cabe en el coordinador solo: no se mide solo, porque tendría que leerse del disco")
    else:
        c.step("Midiendo el coordinador solo (referencia)")
        try:
            guardar("solo coordinador", _bench(exe, path, [], repeticiones, n_prompt, n_gen, timeout_s), "-")
        except Exception as e:
            guardar("solo coordinador", {}, "-", f"{type(e).__name__}: {e}")

    endpoints, orden, servidores, tunel, registros = [], [], [], [], {}
    try:
        for nid in nodes:                                 # un rpc-server por equipo, incluido el coordinador
            c.step(f"Arrancando llama.cpp RPC en {c.host(nid)}")
            out = c.control(nid, "rpc_start", {"version": version})
            orden.append(nid)
            if nid == local:
                endpoints.append(f"127.0.0.1:{out['port']}")
            elif _alcanzable(out["ip"], out["port"]):
                endpoints.append(f"{out['ip']}:{out['port']}")
            else:
                c.step(f"El coordinador no llega a {c.host(nid)} ({out['ip']}), probablemente por un repetidor. "
                       "Se usa un túnel abierto desde ese equipo")
                srv = _abrir_tunel(c, nid)
                servidores.append(srv)
                c.control(nid, "rpc_tunel", {"node": nid})
                endpoints.append(f"127.0.0.1:{srv.getsockname()[1]}")
                tunel.append(c.host(nid))
        ts = "/".join(str(reparto[n]) for n in orden)
        rep_txt = ", ".join(f"{c.host(n)} {reparto[n]:.0%}" for n in orden)
        c.step(f"Midiendo el modelo repartido ({rep_txt})")
        try:
            # sin mapear el archivo, el coordinador no guarda en memoria las capas que viajan a otros equipos
            r = _bench(exe, path, ["--rpc", ",".join(endpoints), "-ngl", "99", "-ts", ts] + _sin_mmap(exe),
                       repeticiones, n_prompt, n_gen, timeout_s)
            guardar("repartido", r, rep_txt)
        except Exception as e:
            guardar("repartido", {}, rep_txt, f"{type(e).__name__}: {e}")
    except Exception as e:  # un fallo al preparar los equipos no debe borrar la medición del coordinador solo
        guardar("repartido", {}, "-", f"{type(e).__name__}: {e}")
    finally:
        for nid in orden:
            try:
                registros[c.host(nid)] = c.control(nid, "rpc_stop", timeout=60)["log"]
            except Exception:
                pass
        for srv in servidores:
            srv.close()
        c.tuneles.clear()
    if filas.get("repartido", {}).get("error"):
        filas["repartido"]["rpc_log"] = registros  # lo que escribió cada rpc-server, para saber por qué falló
    solo = filas.get("solo coordinador", {}).get("tg_tok_s") or 0
    rep = filas.get("repartido", {}).get("tg_tok_s") or 0
    if not filas.get("repartido") or filas["repartido"]["error"]:
        ver = "Inválido"
    elif rep >= 1.5 and solo < 0.5:
        ver = "Favorable"
    elif rep < 0.5 or rep < solo:
        ver = "Desfavorable"
    else:
        ver = "Técnicamente viable"
    if tecnica == "un solo equipo":
        capacidad = f"No se prueba: el modelo cabe en {c.host(local)} solo"
    elif ver == "Inválido":
        capacidad = "No lograda: el reparto falló (ver rpc_log)"
    else:
        capacidad = (f"Lograda: el modelo de {gb:.1f} GB no cabe en {c.host(local)} ({libre[local]:.1f} GB útiles) "
                     f"y corrió repartido a {rep:.2f} palabras por segundo")
    c.step(capacidad)
    return {"capacidad": capacidad, "modelo": modelo, "modelo_gb": round(gb, 3), "plan_automatico": tecnica,
            "libre_util_gb": {c.host(k): round(v, 2) for k, v in libre.items()}, "resultados": filas, "tunel": tunel,
            "nota": "H-03 favorable solo si el coordinador solo no maneja el modelo (< 0,5 tok/s)"}, ver


def exp_p4(c, modelo, n_predict=48, repeticiones=3):
    nodes = _nodes_or_fail(c, 2)
    prompts = [l.strip() for l in open(os.path.join(BASE, "prompts.txt"), encoding="utf-8") if l.strip()]
    arranque = {}
    try:
        for nid in nodes:
            c.step(f"Preparando la IA en {c.host(nid)} (copia el modelo si hace falta)")
            arranque[c.host(nid)] = c.control(nid, "llm_start", {"modelo": modelo}, timeout=3600)
        make = lambda: [{"prompt": p, "n_predict": n_predict} for p in prompts]
        r = _speedup(c, "llm", make, nodes, repeticiones, "P4")
    finally:
        for nid in nodes:
            try:
                c.control(nid, "llm_stop", timeout=60)
            except Exception:
                pass
    r["arranque"] = arranque
    return r, _veredicto_h2(r)


def exp_p5(c, origen="prueba", fotos=120, repeticiones=3):
    nodes = _nodes_or_fail(c, 2)
    for nid in nodes:
        c.step(f"Preparando {c.host(nid)} para procesar fotos (instala Pillow si falta)")
        c.control(nid, "fotos_preparar")
    if origen == "carpeta":
        carpeta = FOTOS
        nombres = lista_fotos(carpeta)
        if not nombres:
            raise RuntimeError("La carpeta fotos del coordinador no tiene fotos .jpg ni .png")
    else:
        carpeta = os.path.join(DATOS, "fotos_prueba")
        os.makedirs(carpeta, exist_ok=True)
        nombres = [f"foto_{i:03d}.jpg" for i in range(fotos)]
        faltan = [i for i, n in enumerate(nombres) if not os.path.exists(os.path.join(carpeta, n))]
        if faltan:
            c.step(f"Creando {len(faltan)} fotos de prueba de 12 megapíxeles (solo la primera vez)")
            with ThreadPoolExecutor(os.cpu_count()) as pool:
                list(pool.map(lambda i: generar_foto(os.path.join(carpeta, nombres[i]), i), faltan))
    c.fotos_origen = carpeta
    c.fotos_destino = os.path.join(DATOS, "fotos_resultado", c.exp["id"])
    os.makedirs(c.fotos_destino, exist_ok=True)
    mb = sum(os.path.getsize(os.path.join(carpeta, n)) for n in nombres) / 2**20
    c.step(f"{len(nombres)} fotos ({mb:.0f} MB): cada equipo baja una, la procesa y devuelve tres versiones")
    r = _speedup(c, "foto", lambda: [{"foto": n} for n in nombres], nodes, repeticiones, "P5")
    tiempos = collections.defaultdict(lambda: collections.defaultdict(list))
    for t in c.db.query("SELECT host, salida FROM tareas WHERE experimento=? AND tipo='foto' AND ok=1", (c.exp["id"],)):
        for k, v in json.loads(t["salida"]).items():
            tiempos[t["host"]][k].append(v)
    r["por_foto_s"] = {}
    for host, d in tiempos.items():
        medias = {k: round(statistics.mean(d[k]), 3) for k in ("bajar_s", "procesar_s", "subir_s")}
        medias["red_pct"] = round(100 * (medias["bajar_s"] + medias["subir_s"]) / (sum(medias.values()) or 1), 1)
        r["por_foto_s"][host] = medias
    r.update(fotos=len(nombres), mb_fotos=round(mb, 1), origen=origen, resultado=c.fotos_destino)
    return r, _veredicto_h2(r)


def write_report(c, eid):
    e = c.db.query("SELECT * FROM experimentos WHERE id=?", (eid,))[0]
    res = json.loads(e["resumen"] or "{}")
    nodos = c.db.query("SELECT host, ip, inventario FROM nodos WHERE id IN "
                       "(SELECT DISTINCT nodo FROM metricas WHERE experimento=?)", (eid,))
    met = c.db.query("SELECT host, ROUND(AVG(cpu_pct),1) cpu_media, ROUND(MAX(cpu_pct),1) cpu_max, "
                     "ROUND(MIN(ram_libre_gb),2) ram_libre_min, ROUND(AVG(latencia_ms),2) lat_media, "
                     "ROUND(MAX(latencia_ms),2) lat_max, MAX(red_env_mb)-MIN(red_env_mb) env_mb, "
                     "MAX(red_rec_mb)-MIN(red_rec_mb) rec_mb, MAX(en_bateria) bateria "
                     "FROM metricas WHERE experimento=? GROUP BY host", (eid,))
    L = [f"# Informe {eid}", "", f"- **Prueba:** {e['prueba']}", f"- **Estado:** {e['estado']}",
         f"- **Veredicto:** {e['veredicto']}",
         f"- **Duración:** {round((e['fin'] or time.time()) - e['inicio'], 1)} s", "", "## Equipos", ""]
    for n in nodos:
        inv = json.loads(n["inventario"])
        L.append(f"- {n['host']} ({n['ip']}): {inv.get('cpu')}, RAM {inv.get('ram_total_gb')} GB, "
                 f"AVX2 {inv.get('avx2')}, {inv.get('so')}")
    L += ["", "## Recursos medidos durante la prueba", "",
          "| Equipo | CPU media % | CPU máx % | RAM libre mín GB | Latencia media ms | Latencia máx ms | Enviado MB | Recibido MB | En batería |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m in met:
        L.append("| " + " | ".join(str(m[k]) for k in ("host", "cpu_media", "cpu_max", "ram_libre_min", "lat_media",
                                                          "lat_max", "env_mb", "rec_mb", "bateria")) + " |")
    L += ["", "## Resultado", "", "```json", json.dumps(res, ensure_ascii=False, indent=2), "```", "",
          "## Pasos", ""] + [f"- {s}" for s in c.exp_log]
    os.makedirs(os.path.join(DATOS, "informes"), exist_ok=True)
    with open(os.path.join(DATOS, "informes", f"{eid}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def make_handler(c):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj=None):
            self._send(code, json.dumps(obj if obj is not None else {}, ensure_ascii=False, default=str).encode())

        def _archivo(self, f):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(os.path.getsize(f)))
            self.end_headers()
            with open(f, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile, 1 << 20)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path, _, qs = self.path.partition("?")
            q = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            if path == "/":
                with open(os.path.join(BASE, "panel.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/xara.py":
                with open(os.path.abspath(__file__), "rb") as f:
                    return self._send(200, f.read(), "text/x-python")
            if path == "/api/tarea":
                t = c.next_task(q.get("node"), q.get("control") == "1")
                return self._json(200, t) if t else self._send(204)
            if path == "/api/tunel":
                self.send_response(200)
                self.end_headers()
                try:
                    llama = c.tuneles[q.get("node")].get(timeout=600)
                except (KeyError, queue.Empty):
                    return
                return unir(self.connection, llama)
            if path == "/api/estado":
                now = time.time()
                with c.lock:
                    nodos = [{"host": v["info"].get("host"), "ip": v["info"].get("ip"),
                              "cpu": v["info"].get("cpu"), "ram_total_gb": v["info"].get("ram_total_gb"),
                              "so": v["info"].get("so"), "motores": v["info"].get("motores"), "m": v["m"],
                              "activo": now - v["ultimo"] < NODE_TIMEOUT_S} for v in c.nodes.values()]
                return self._json(200, {"version": VERSION, "nodos": nodos, "prueba": c.exp, "pasos": c.exp_log[-12:],
                                        "modelos": modelos(), "fotos": len(lista_fotos(FOTOS)),
                                        "motores": {k: bool(v) for k, v in motores().items()}})
            if path == "/api/experimentos":
                return self._json(200, c.db.query("SELECT * FROM experimentos ORDER BY inicio DESC LIMIT 50"))
            if path.startswith("/api/informe/"):
                f = os.path.join(DATOS, "informes", os.path.basename(path) + ".md")
                if os.path.exists(f):
                    return self._send(200, open(f, "rb").read(), "text/plain; charset=utf-8")
                return self._json(404)
            if path.startswith("/api/csv/"):
                t = os.path.basename(path)
                if t in ("nodos", "metricas", "tareas", "lotes", "experimentos", "ia"):
                    return self._send(200, c.db.csv(t).encode("utf-8-sig"), "text/csv; charset=utf-8")
                return self._json(404)
            if path.startswith("/modelos/"):
                f = os.path.join(MODELOS, os.path.basename(urllib.request.unquote(path)))
                return self._archivo(f) if os.path.exists(f) else self._json(404)
            if path.startswith("/fotos/") and c.fotos_origen:
                f = os.path.join(c.fotos_origen, os.path.basename(urllib.request.unquote(path)))
                return self._archivo(f) if os.path.exists(f) else self._json(404)
            if path.startswith("/motores/"):
                version = version_llama()
                if urllib.request.unquote(path) != f"/motores/{version}.tar.gz":
                    return self._json(404)
                f = os.path.join(DATOS, f"{version}.tar.gz")
                if not os.path.exists(f):
                    os.replace(shutil.make_archive(f + ".parte", "gztar", os.path.join(MOTORES, version)), f)
                return self._archivo(f)
            self._json(404)

        def do_POST(self):
            if self.path.startswith("/api/foto/") and c.fotos_destino:
                f = os.path.join(c.fotos_destino, os.path.basename(urllib.request.unquote(self.path)))
                with open(f, "wb") as fh:
                    fh.write(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                return self._json(200)
            d = self._body()
            if self.path == "/api/registrar":
                return self._json(200, {"node_id": c.register(d, self.client_address[0])})
            if self.path == "/api/latido":
                return self._json(200 if c.heartbeat(d) else 404)
            if self.path == "/api/resultado":
                c.result(d)
                return self._json(200)
            if self.path == "/api/prueba":
                try:
                    return self._json(200, {"id": c.start_experiment(d["prueba"], d.get("opciones", {}))})
                except Exception as e:
                    return self._json(400, {"error": str(e)})
            self._json(404)
    return H


def discovery_responder(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", DISCOVERY_PORT))
    while True:
        msg, addr = s.recvfrom(1024)
        if msg == DISCOVERY_MSG:
            s.sendto(json.dumps({"xara": VERSION, "port": port}).encode(), addr)


def instalar_llama():
    if all(motores().values()):
        log("llama.cpp ya está en la carpeta motores.")
        return
    if not IS_WIN:
        log("En Linux hay que compilar llama.cpp y copiar sus ejecutables en la carpeta motores.")
        return
    with urllib.request.urlopen(LLAMA_VERSIONES, timeout=60) as r:
        versiones = json.load(r)
    for version in versiones:
        zips = [a for a in version["assets"] if "win-cpu-x64" in a["name"] and a["name"].endswith(".zip")]
        if zips:
            break
    else:
        raise RuntimeError("Ninguna de las últimas 30 versiones de llama.cpp trae el archivo win-cpu-x64")
    log(f"Descargando llama.cpp {version['tag_name']}...")
    zip_path = os.path.join(MOTORES, zips[0]["name"])
    descargar(zips[0]["browser_download_url"], zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(os.path.join(MOTORES, version["tag_name"]))
    os.remove(zip_path)
    faltan = [k for k, v in motores().items() if not v]
    if faltan:
        raise RuntimeError(f"Al zip de llama.cpp le faltan ejecutables: {', '.join(faltan)}")
    log("llama.cpp listo.")


def instalar_modelo(url, pregunta):
    path = os.path.join(MODELOS, url.rsplit("/", 1)[1])
    if os.path.exists(path):
        log(f"{os.path.basename(path)} ya está en la carpeta modelos.")
        return
    libre_gb = shutil.disk_usage(MODELOS).free / 2**30
    if input(f"{pregunta} Hay {libre_gb:.0f} GB libres en este disco. [s/n] ").strip().lower() != "s":
        return
    log(f"Descargando {os.path.basename(path)}...")
    descargar(url, path)
    log("Modelo listo.")


def falta_vcruntime():
    return IS_WIN and not os.path.exists(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vcruntime140.dll"))


def actualizar_desde(coord):
    """Cada equipo usa el mismo xara.py que el coordinador; si el suyo es distinto, lo reemplaza."""
    try:
        with urllib.request.urlopen(f"http://{coord}/xara.py", timeout=30) as r:
            nuevo = r.read()
    except (urllib.error.URLError, OSError):
        return False
    propio = os.path.abspath(__file__)
    with open(propio, "rb") as f:
        if f.read() == nuevo:
            return False
    with open(propio + ".nuevo", "wb") as f:
        f.write(nuevo)
    os.replace(propio + ".nuevo", propio)
    return True


def coordinador_guardado():
    try:
        with open(COORD_GUARDADO, encoding="utf-8") as f:
            coord = f.read().strip()
        _http(f"http://{coord}", "/api/estado", timeout=3)
        return coord
    except (OSError, ValueError):
        return None


def instalar():
    """Deja listo el paso 4 de la guía: llama.cpp en cada equipo y los modelos solo en el coordinador."""
    instalar_llama()
    if input("¿Este equipo será el coordinador (la PC)? [s/n] ").strip().lower() != "s":
        log("Listo. Los modelos se copian solos a este equipo cuando hagan falta.")
        return
    instalar_modelo(MODELO_PEQUENO, "¿Descargar el modelo pequeño para P4 (1 GB)?")
    instalar_modelo(MODELO_GRANDE, "¿Descargar el modelo grande para P3 (5,4 GB)?")
    instalar_modelo(MODELO_CAPACIDAD, "¿Descargar el modelo de 14B para P3b (7,9 GB)?")


def run_coordinator(port, workers):
    c = Coordinator()
    threading.Thread(target=discovery_responder, args=(port,), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(c))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"[coord] XARA {VERSION} listo. Panel: http://localhost:{port}  (en la red: http://{local_ip()}:{port})")
    Node(f"127.0.0.1:{port}", workers).run()


def main():
    p = argparse.ArgumentParser(description=f"XARA prototipo v{VERSION}")
    p.add_argument("modo", nargs="?", default="auto", choices=["auto", "coordinador", "equipo", "info", "prueba", "instalar"])
    p.add_argument("--coord", help="IP:PUERTO del coordinador (si no, se busca solo)")
    p.add_argument("--hilos", type=int, default=os.cpu_count() or 1, help="tareas simultáneas en este equipo")
    p.add_argument("--puerto", type=int, default=HTTP_PORT)
    p.add_argument("--prueba", help="P1, P2, P3, P3b, P4 o P5 (modo prueba)")
    p.add_argument("--opciones", default="{}", help='JSON, por ejemplo {"modelo": "x.gguf"}')
    a = p.parse_args()
    for d in (DATOS, os.path.join(DATOS, "logs"), MOTORES, MODELOS, FOTOS):
        os.makedirs(d, exist_ok=True)
    if falta_vcruntime():
        log(f"AVISO: falta Visual C++ Redistributable y llama.cpp no arrancará. Instálalo desde {VCREDIST}")
    if a.modo == "instalar":
        try:
            instalar()
        except (urllib.error.URLError, RuntimeError) as e:
            sys.exit(f"No se pudo terminar la instalación: {e}")
        return
    if a.modo == "info":
        print(json.dumps(inventory(), ensure_ascii=False, indent=2))
        return
    if a.modo == "prueba":
        base = f"http://{a.coord or discover() or f'127.0.0.1:{a.puerto}'}"
        print(_http(base, "/api/prueba", {"prueba": a.prueba, "opciones": json.loads(a.opciones)})[1])
        return
    coord = a.coord
    if a.modo == "auto" and not coord:
        log("Buscando un coordinador XARA en la red...")
        coord = discover() or coordinador_guardado()
    if a.modo == "coordinador" or (a.modo == "auto" and not coord):
        run_coordinator(a.puerto, a.hilos)
    else:
        if not coord:
            sys.exit("No se encontró coordinador. Usa --coord IP:8765")
        if actualizar_desde(coord):
            log("XARA se actualizó con la versión del coordinador. Si no se vuelve a abrir solo, ábrelo de nuevo.")
            sys.exit(CODIGO_ACTUALIZADO)
        try:
            Node(coord, a.hilos).run()
        except urllib.error.URLError as e:
            sys.exit(f"No se pudo conectar con el coordinador {coord} ({e.reason}). "
                     "Revisa que XARA esté abierto en la PC y que la IP sea la que muestra su ventana.")
        if a.coord:
            with open(COORD_GUARDADO, "w", encoding="utf-8") as f:
                f.write(a.coord)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("XARA detenido")


if __name__ == "__main__":
    main()
