import time
import tkinter as tk
from tkinter import ttk
import threading
import queue
import hashlib
from PIL import ImageGrab, Image, ImageEnhance, ImageFilter
import easyocr
from deep_translator import GoogleTranslator
import sys
import re
import keyboard
import os
import difflib
from datetime import datetime

# --- RUTAS — todo dentro de Documentos/traductor ---
_docs = os.path.join(os.path.expanduser("~"), "Documents")
CARPETA = os.path.join(_docs, "traductor")
os.makedirs(CARPETA, exist_ok=True)

CONFIG_FILE  = os.path.join(CARPETA, "config_traductor.txt")
RUTA_LOG     = os.path.join(CARPETA, "traductor_log.txt")
IMG_RAW      = os.path.join(CARPETA, "pso_raw.png")
IMG_LIMPIA   = os.path.join(CARPETA, "chat_pso_limpio.png")

# Archivos temporales que se borran al cerrar
TEMP_FILES = [IMG_RAW, IMG_LIMPIA]

# ==========================================
# AUTO-DETECCIÓN DE CS2
# ==========================================

# Rutas típicas donde Steam instala CS2 (en cualquier disco)
_CS2_SUBPATH = os.path.join(
    "steamapps", "common",
    "Counter-Strike Global Offensive", "game", "csgo", "console.log"
)

_STEAM_REGISTRY_KEYS = [
    r"SOFTWARE\Valve\Steam",
    r"SOFTWARE\WOW6432Node\Valve\Steam",
]

def _buscar_steam_via_registro():
    """Lee el registro de Windows para obtener la ruta de instalación de Steam."""
    try:
        import winreg
        for key_path in _STEAM_REGISTRY_KEYS:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                ruta, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if ruta:
                    return ruta
            except:
                continue
    except:
        pass
    return None

def _buscar_steamlibraries(steam_path):
    """
    Lee libraryfolders.vdf para encontrar todas las bibliotecas de Steam
    (Steam permite instalar juegos en discos distintos).
    """
    rutas = [steam_path]
    vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf):
        return rutas
    try:
        with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
            for linea in f:
                # Las líneas con rutas tienen forma:  "path"   "D:\SteamLibrary"
                m = re.search(r'"path"\s+"([^"]+)"', linea)
                if m:
                    p = m.group(1).replace("\\\\", "\\")
                    if os.path.isdir(p):
                        rutas.append(p)
    except:
        pass
    return rutas

def _buscar_cs2_en_discos():
    """
    Búsqueda de último recurso: recorre las raíces de todos los discos
    buscando la carpeta típica de CS2 (solo un nivel de profundidad).
    """
    import string
    for letra in string.ascii_uppercase:
        base = f"{letra}:\\"
        if not os.path.exists(base):
            continue
        # Rutas típicas de Steam en distintos discos
        for sub in ["Steam", "SteamLibrary", "Program Files\\Steam",
                    "Program Files (x86)\\Steam"]:
            candidato = os.path.join(base, sub, _CS2_SUBPATH)
            if os.path.exists(candidato):
                return candidato
    return None

def detectar_cs2():
    """
    Intenta encontrar console.log de CS2 en este orden:
    1. Registro de Windows → InstallPath de Steam
    2. Todas las bibliotecas de Steam (libraryfolders.vdf)
    3. Búsqueda manual en raíces de disco
    4. Ruta por defecto si todo falla
    """
    steam_path = _buscar_steam_via_registro()
    if steam_path:
        for lib in _buscar_steamlibraries(steam_path):
            candidato = os.path.join(lib, _CS2_SUBPATH)
            if os.path.exists(candidato):
                return candidato

    # Búsqueda en discos
    encontrado = _buscar_cs2_en_discos()
    if encontrado:
        return encontrado

    # Fallback: ruta por defecto
    return os.path.join(
        "C:\\", "Program Files (x86)", "Steam",
        "steamapps", "common",
        "Counter-Strike Global Offensive", "game", "csgo", "console.log"
    )

RUTA_LOG_CS2 = detectar_cs2()
print(f"CS2 console.log: {RUTA_LOG_CS2}")

def cargar_config():
    tecla, modo         = "F4", "PSO"
    cx1, cy1, cx2, cy2 = 10, 620, 360, 790
    win_w, win_h        = 650, 280
    win_x, win_y        = 10, 450
    zoom_o, zoom_t      = 9, 10
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            lineas = f.read().splitlines()
        try:
            if len(lineas) >= 1:  tecla            = lineas[0].strip()
            if len(lineas) >= 2:  modo             = lineas[1].strip()
            if len(lineas) >= 6:  cx1, cy1, cx2, cy2 = int(lineas[2]), int(lineas[3]), int(lineas[4]), int(lineas[5])
            if len(lineas) >= 8:  win_w, win_h     = int(lineas[6]), int(lineas[7])
            if len(lineas) >= 10: win_x, win_y     = int(lineas[8]), int(lineas[9])
            if len(lineas) >= 12: zoom_o, zoom_t   = int(lineas[10]), int(lineas[11])
        except:
            pass
    return tecla, modo, cx1, cy1, cx2, cy2, win_w, win_h, win_x, win_y, zoom_o, zoom_t

def guardar_config_completa():
    """Guarda todos los ajustes actuales en config."""
    with open(CONFIG_FILE, "w") as f:
        f.write(f"{TECLA_HOTKEY}\n{MODO_JUEGO}\n")
        f.write(f"{CHAT_X1}\n{CHAT_Y1}\n{CHAT_X2}\n{CHAT_Y2}\n")
        f.write(f"{WIN_W}\n{WIN_H}\n")
        f.write(f"{win_barra.winfo_x()}\n{win_barra.winfo_y()}\n")
        f.write(f"{tam_original['val']}\n{tam_traducido['val']}\n")

# Alias para compatibilidad con llamadas existentes
def guardar_config(tecla, modo, cx1, cy1, cx2, cy2):
    """Guarda config básica (tecla, modo, zona). Llama a guardar_config_completa cuando existan las ventanas."""
    with open(CONFIG_FILE, "w") as f:
        f.write(f"{tecla}\n{modo}\n{cx1}\n{cy1}\n{cx2}\n{cy2}\n")
        # Intentar añadir el resto si ya existen las variables de ventana
        try:
            f.write(f"{WIN_W}\n{WIN_H}\n")
            f.write(f"{win_barra.winfo_x()}\n{win_barra.winfo_y()}\n")
            f.write(f"{tam_original['val']}\n{tam_traducido['val']}\n")
        except:
            pass

def limpiar_temporales():
    """Borra imágenes temporales del OCR al cerrar."""
    for ruta in TEMP_FILES:
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
        except:
            pass

TECLA_HOTKEY, MODO_JUEGO, CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2, WIN_W_CFG, WIN_H_CFG, WIN_X_CFG, WIN_Y_CFG, ZOOM_O_CFG, ZOOM_T_CFG = cargar_config()

print("Iniciando traductor PSO...")
lector_ocr = easyocr.Reader(['tr', 'en'], gpu=False)
traductor = GoogleTranslator(source='auto', target='es')

ejecutando = True
ventana_visible = True
historial_mostrado = []
MAX_HISTORIAL = 300
cola_frames = queue.Queue(maxsize=1)
ultimo_hash = None


# ==========================================
# SISTEMA DE LOG
# ==========================================

with open(RUTA_LOG, "a", encoding="utf-8") as f:
    f.write("\n" + "=" * 60 + "\n")
    f.write(f"  SESIÓN INICIADA: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 60 + "\n\n")

def log(tipo, contenido_ocr, confianza=None, prefijo=None, original=None, traducido=None, motivo_descarte=None):
    ts = datetime.now().strftime("%H:%M:%S")
    with open(RUTA_LOG, "a", encoding="utf-8") as f:
        if tipo == "OK":
            conf_str = f"{confianza:.2f}" if confianza is not None else "N/A"
            f.write(f"[{ts}] ✓ OK  (confianza: {conf_str})\n")
            f.write(f"         OCR     : {contenido_ocr}\n")
            if prefijo:
                f.write(f"         Prefijo : {prefijo}\n")
                f.write(f"         Mensaje : {original}\n")
                f.write(f"         Trad.   : {traducido}\n")
            else:
                f.write(f"         Sistema : {original}\n")
                f.write(f"         Trad.   : {traducido}\n")
            f.write("\n")
        elif tipo == "DESCARTADO":
            conf_str = f"{confianza:.2f}" if confianza is not None else "N/A"
            f.write(f"[{ts}] ✗ DESCARTADO  (confianza: {conf_str}) — {motivo_descarte}\n")
            f.write(f"         OCR     : {contenido_ocr}\n\n")
        elif tipo == "REPETIDO":
            f.write(f"[{ts}] ~ REPETIDO\n")
            f.write(f"         OCR     : {contenido_ocr}\n\n")
        elif tipo == "FUSIONADO":
            f.write(f"[{ts}] ⟳ FUSIONADO (línea partida)\n")
            f.write(f"         Parte 1 : {motivo_descarte}\n")
            f.write(f"         Parte 2 : {contenido_ocr}\n")
            f.write(f"         Resultado: {original}\n\n")
        elif tipo == "ERROR":
            f.write(f"[{ts}] ! ERROR — {contenido_ocr}\n\n")
        elif tipo == "SISTEMA":
            f.write(f"[{ts}] · {contenido_ocr}\n\n")


# ==========================================
# FILTROS DE CALIDAD
# ==========================================

VOCALES = set("aeiouáéíóúàèìòùäëïöüAEIOUÁÉÍÓÚÀÈÌÒÙÄËÏÖÜaıiuAIİU")
SIMBOLOS = set("~`!@#$%^&*_+=[]{}|\\<>?/\"'")

def tiene_vocales(texto):
    """Al menos el 15% del texto deben ser vocales."""
    if not texto:
        return False
    vocales = sum(1 for c in texto if c in VOCALES)
    return (vocales / len(texto)) >= 0.10

def ratio_simbolos(texto):
    """Devuelve el porcentaje de caracteres que son símbolos extraños."""
    if not texto:
        return 1.0
    simbolos = sum(1 for c in texto if c in SIMBOLOS)
    return simbolos / len(texto)

def es_fragmento_valido(texto):
    """
    Filtra líneas que son basura aunque tengan confianza alta.
    Reglas:
      - Mínimo 6 caracteres
      - Al menos una vocal
      - Menos del 35% de símbolos raros
      - No solo signos de puntuación/espacios
    """
    t = texto.strip()
    if len(t) < 6:
        return False, "demasiado corta (<6 chars)"
    if not tiene_vocales(t):
        return False, "sin vocales (probable basura OCR)"
    if ratio_simbolos(t) > 0.35:
        return False, f"demasiados símbolos ({ratio_simbolos(t):.0%})"
    # Solo símbolos y números sin letras
    if not re.search(r'[a-zA-ZÇĞİÖŞÜçğışöşü]', t):
        return False, "sin letras reales"
    return True, ""

def es_linea_incompleta(texto):
    """
    Detecta fragmentos que son mitad de una línea:
    - Empieza por minúscula sin ser inicio de oración
    - Termina con paréntesis abierto o ID incompleto
    - Es muy corta y sin dos puntos
    """
    t = texto.strip()
    # Fragmento final sin sentido: solo ID + posición, sin mensaje
    if re.match(r'^[A-Za-z0-9]{2,8}\)\([A-Z]{1,3}\):?\s*$', t):
        return True
    # Empieza por minúscula y es corta → probablemente es el final de algo
    if t and t[0].islower() and len(t) < 20 and ':' not in t:
        return True
    return False


# ==========================================
# POSTPROCESADO OCR
# ==========================================

CORRECCIONES_OCR = [
    (r'\bAIIM\b',   'AIM'),
    (r'\bAlIM\b',   'AIM'),
    (r'SONFİ',      'CONFİ'),
    (r'SONFI',      'CONFI'),
    (r'CONFl',      'CONFI'),
    (r'\b0\b',      'O'),
    (r'(?<=[A-ZÇĞİÖŞÜa-zçğışöşü])1(?=[A-ZÇĞİÖŞÜa-zçğışöşü])', 'I'),
    (r'(?<=[A-ZÇĞİÖŞÜa-zçğışöşü])0(?=[A-ZÇĞİÖŞÜa-zçğışöşü])', 'O'),
    (r'rn(?=[a-zçğışöşü])', 'm'),
]

def corregir_ocr(texto):
    for patron, reemplazo in CORRECCIONES_OCR:
        texto = re.sub(patron, reemplazo, texto)
    return texto


# ==========================================
# PARSEO DE LÍNEA
# ==========================================

def parsear_linea(linea):
    linea = linea.strip()
    match = re.match(r'^((?:\([^\)]*\)\s*)?[^:]+):\s*(.*)$', linea)
    if match:
        prefijo = match.group(1).strip() + ":"
        mensaje = match.group(2).strip()
        return prefijo, mensaje
    return "", linea


# ==========================================
# SELECTOR DE ZONA
# ==========================================

def abrir_selector_zona():
    global CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2
    root.withdraw()
    time.sleep(0.15)

    selector = tk.Toplevel()
    selector.attributes("-fullscreen", True)
    selector.attributes("-topmost", True)
    selector.attributes("-alpha", 0.35)
    selector.config(bg="black", cursor="crosshair")

    canvas = tk.Canvas(selector, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    ancho = selector.winfo_screenwidth()
    canvas.create_text(ancho // 2, 40,
        text="Dibuja el recuadro del chat  ·  ESC para cancelar",
        fill="white", font=("Arial", 16, "bold"))

    estado = {"inicio": None, "rect": None}

    def on_press(e):
        estado["inicio"] = (e.x, e.y)
        if estado["rect"]: canvas.delete(estado["rect"])

    def on_drag(e):
        if not estado["inicio"]: return
        x0, y0 = estado["inicio"]
        if estado["rect"]: canvas.delete(estado["rect"])
        estado["rect"] = canvas.create_rectangle(
            x0, y0, e.x, e.y,
            outline="#00ffcc", width=2, fill="#00ffcc", stipple="gray25")

    def on_release(e):
        if not estado["inicio"]: return
        x0, y0 = estado["inicio"]
        nx1, nx2 = min(x0, e.x), max(x0, e.x)
        ny1, ny2 = min(y0, e.y), max(y0, e.y)
        if (nx2 - nx1) < 20 or (ny2 - ny1) < 20:
            selector.destroy(); root.deiconify(); root.attributes("-topmost", True); return
        global CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2
        CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2 = nx1, ny1, nx2, ny2
        guardar_config(TECLA_HOTKEY, MODO_JUEGO, CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2)
        selector.destroy()
        root.deiconify(); root.attributes("-topmost", True)
        log("SISTEMA", f"Zona actualizada: ({CHAT_X1},{CHAT_Y1}) → ({CHAT_X2},{CHAT_Y2})")
        escribir_en_ui("", f"-- ZONA: ({CHAT_X1},{CHAT_Y1}) → ({CHAT_X2},{CHAT_Y2}) --", "-- ZONA GUARDADA --")

    def on_escape(e):
        selector.destroy(); root.deiconify(); root.attributes("-topmost", True)

    canvas.bind("<ButtonPress-1>",   on_press)
    canvas.bind("<B1-Motion>",       on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    selector.bind("<Escape>",        on_escape)
    selector.focus_force()


# ==========================================
# PROCESADO DE IMAGEN
# ==========================================

def hash_imagen(img):
    pequeña = img.resize((64, 32)).convert("L")
    return hashlib.md5(pequeña.tobytes()).hexdigest()

def procesar_imagen_pso(img):
    img = img.convert("RGB")
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img.save(IMG_LIMPIA)
    return IMG_LIMPIA


# ==========================================
# DEDUPLICACIÓN
# ==========================================

def normalizar(texto):
    return re.sub(r'\s+', ' ', texto.strip().lower())

def similitud(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

def ya_esta_mostrado(linea):
    norm = normalizar(linea)
    for anterior in historial_mostrado[-50:]:
        if similitud(norm, anterior) >= 0.85:
            return True
    return False

def registrar_linea(linea):
    historial_mostrado.append(normalizar(linea))
    if len(historial_mostrado) > MAX_HISTORIAL:
        del historial_mostrado[:MAX_HISTORIAL // 2]


# ==========================================
# TRADUCCIÓN
# ==========================================

def traducir_mensaje(mensaje):
    try:
        resultado = traductor.translate(mensaje)
        # Si Google devuelve un error HTML/500, usar el original
        if resultado and ("Error" in resultado or "<!DOCTYPE" in resultado or len(resultado) > len(mensaje) * 5):
            return mensaje
        return resultado or mensaje
    except:
        return mensaje


# ==========================================
# ESCRITURA EN UI
# ==========================================

def escribir_en_ui(prefijo_orig, msg_orig, msg_trad):
    txt_original.config(state="normal")
    txt_traducido.config(state="normal")
    if prefijo_orig:
        txt_original.insert(tk.END, prefijo_orig + " ", "prefijo_orig")
        txt_original.insert(tk.END, msg_orig + "\n\n", "msg_orig")
        txt_traducido.insert(tk.END, prefijo_orig + " ", "prefijo_trad")
        txt_traducido.insert(tk.END, msg_trad + "\n\n", "msg_trad")
    else:
        txt_original.insert(tk.END, msg_orig + "\n\n", "sistema_orig")
        txt_traducido.insert(tk.END, msg_trad + "\n\n", "sistema_trad")
    txt_original.see(tk.END)
    txt_traducido.see(tk.END)
    txt_original.config(state="disabled")
    txt_traducido.config(state="disabled")


# ==========================================
# HILO CAPTURADOR
# ==========================================

def hilo_capturador():
    global ultimo_hash
    while ejecutando:
        if MODO_JUEGO == "PSO" and ventana_visible:
            try:
                img = ImageGrab.grab(bbox=(CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2))
                h = hash_imagen(img)
                if h != ultimo_hash:
                    ultimo_hash = h
                    try: cola_frames.get_nowait()
                    except queue.Empty: pass
                    try: cola_frames.put_nowait(img)
                    except queue.Full: pass
            except Exception as e:
                log("ERROR", f"Captura fallida: {e}")
        time.sleep(0.3)


# ==========================================
# HILO OCR — con fusión de líneas partidas
# ==========================================

def hilo_ocr():
    fragmento_pendiente = None  # guarda mitad de línea partida

    while ejecutando:
        try:
            img = cola_frames.get(timeout=1.0)
        except queue.Empty:
            continue

        if MODO_JUEGO != "PSO" or not ventana_visible:
            continue

        try:
            img_f = procesar_imagen_pso(img)
            resultado = lector_ocr.readtext(
                img_f, detail=1, paragraph=False,
                text_threshold=0.5, low_text=0.3, width_ths=0.5
            )

            fragmento_pendiente = None  # reseteamos por cada frame nuevo

            for bbox, linea, confianza in resultado:
                linea = linea.strip()
                if not linea:
                    continue

                # 1. Descartar por confianza (bajamos a 0.45)
                if confianza < 0.45:
                    log("DESCARTADO", linea, confianza=confianza,
                        motivo_descarte=f"confianza baja ({confianza:.2f} < 0.45)")
                    continue

                linea = corregir_ocr(linea)

                # 2. Intentar fusionar con fragmento pendiente del frame anterior
                if fragmento_pendiente is not None:
                    fusionada = fragmento_pendiente + " " + linea
                    log("FUSIONADO", linea, original=fusionada, motivo_descarte=fragmento_pendiente)
                    linea = fusionada
                    fragmento_pendiente = None

                # 3. Detectar si es línea incompleta → guardar para fusionar
                if es_linea_incompleta(linea):
                    fragmento_pendiente = linea
                    log("DESCARTADO", linea, confianza=confianza,
                        motivo_descarte="fragmento incompleto, esperando continuación")
                    continue

                # 4. Filtro de calidad (vocales, símbolos, longitud)
                valido, motivo = es_fragmento_valido(linea)
                if not valido:
                    log("DESCARTADO", linea, confianza=confianza, motivo_descarte=motivo)
                    continue

                # 5. Deduplicación
                if ya_esta_mostrado(linea):
                    log("REPETIDO", linea)
                    continue

                registrar_linea(linea)

                # 6. Parsear y traducir
                prefijo, mensaje = parsear_linea(linea)

                if prefijo and mensaje:
                    traducido = traducir_mensaje(mensaje)
                    log("OK", linea, confianza=confianza,
                        prefijo=prefijo, original=mensaje, traducido=traducido)
                    escribir_en_ui(prefijo, mensaje, traducido)
                else:
                    traducido = traducir_mensaje(linea)
                    log("OK", linea, confianza=confianza,
                        prefijo=None, original=linea, traducido=traducido)
                    escribir_en_ui("", linea, traducido)

        except Exception as e:
            log("ERROR", f"OCR fallido: {e}")


# ==========================================
# MOTOR CS2
# ==========================================

# Prefijos técnicos del motor de CS2 que NO son chat de jugadores
_CS2_PREFIJOS_SISTEMA = (
    "[Client]", "[Networking]", "[SignonState]", "[matchmaking]",
    "[SteamNetSock]", "[CSteam", "[Voice]", "[Lua]", "[Workshop]",
    "[GameUI]", "[ResourceSystem]", "[InputSystem]", "[VScript]",
    "[MDLCACHE]", "[Valve]", "[Steam]", "CDemoFile", "CNetworkGame",
    "DataTable", "CModelLoader", "StringTable", "Host_", "Tick ",
    "NET_", "SV_", "CL_", "CM_", "[Lobby]", "[Party]",
)

def _es_linea_chat_cs2(linea):
    """
    Devuelve True solo si la línea es chat real de un jugador.
    Filtra todo el ruido técnico del console.log.
    """
    linea = linea.strip()

    # Debe contener " : " o el marcador ruso de chat
    if " : " not in linea and "сказал" not in linea:
        return False

    # Descartar líneas que empiezan por timestamp técnico del motor
    # Formato: "05/27 01:53:13 [Client] ..."
    if re.match(r"^\d{2}/\d{2} \d{2}:\d{2}:\d{2}", linea):
        return False

    # Descartar si contiene algún prefijo de sistema conocido
    for prefijo in _CS2_PREFIJOS_SISTEMA:
        if prefijo in linea:
            return False

    # Descartar comandos de consola
    partes = linea.split(" : ", 1)
    if len(partes) == 2:
        msg = partes[1].strip()
        if msg.startswith(("exec", "bind", "//", "echo", "cvar", "cmd")):
            return False
        # El mensaje no puede estar vacío
        if not msg:
            return False

    return True

def hilo_motor_cs2():
    while ejecutando:
        if MODO_JUEGO == "CS2" and ventana_visible:
            if not os.path.exists(RUTA_LOG_CS2):
                time.sleep(2); continue
            with open(RUTA_LOG_CS2, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                while ejecutando and MODO_JUEGO == "CS2":
                    linea = f.readline()
                    if not linea:
                        time.sleep(0.1); continue

                    if not _es_linea_chat_cs2(linea):
                        continue

                    # Quitar prefijo (All) o (Team)
                    linea_limpia = re.sub(r'^\s*([Aa][Ll][Ll]|[Tt][Ee][Aa][Mm])\s*', '', linea.strip())
                    match = re.match(r"^(.+?)\s*:\s*(.+)$", linea_limpia)
                    if not match:
                        continue

                    prefijo = match.group(1).strip() + ":"
                    msg     = match.group(2).strip()
                    trad    = traducir_mensaje(msg)
                    log("OK", linea.strip(), prefijo=prefijo, original=msg, traducido=trad)
                    escribir_en_ui(prefijo, msg, trad)
        time.sleep(1)


# ==========================================
# CONTROLES
# ==========================================

def alternar_ventana():
    # Redefinida más abajo tras crear win_barra y win_panel
    pass

def cambiar_modo():
    global MODO_JUEGO
    MODO_JUEGO = "CS2" if MODO_JUEGO == "PSO" else "PSO"
    guardar_config(TECLA_HOTKEY, MODO_JUEGO, CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2)
    btn_modo.config(text=f"🎮 Modo: {MODO_JUEGO}")
    log("SISTEMA", f"Modo cambiado a {MODO_JUEGO}")
    escribir_en_ui("", f"-- MODO {MODO_JUEGO} --", f"-- MODO {MODO_JUEGO} --")

def abrir_ajustes():
    win = tk.Toplevel(root)
    win.title("Ajustes"); win.geometry("300x120"); win.config(bg="#1a1a1a"); win.attributes("-topmost", True)
    tk.Label(win, text="PULSA LA NUEVA TECLA", fg="#00ffcc", bg="#1a1a1a", font=("Arial", 10, "bold")).pack(pady=20)
    def capturar(e):
        global TECLA_HOTKEY
        TECLA_HOTKEY = e.keysym
        guardar_config(TECLA_HOTKEY, MODO_JUEGO, CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2)
        keyboard.remove_all_hotkeys(); keyboard.add_hotkey(TECLA_HOTKEY, alternar_ventana)
        label_titulo.config(text=f"TRADUCTOR | [{TECLA_HOTKEY.upper()}]"); win.destroy()
    win.bind("<Key>", capturar)

def cerrar_aplicacion():
    global ejecutando
    ejecutando = False
    log("SISTEMA", f"Sesión cerrada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try: guardar_config_completa()
    except: pass
    limpiar_temporales()
    try: keyboard.unhook_all()
    except: pass
    try: root.quit()
    except: pass
    sys.exit(0)

import ctypes

GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

def aplicar_click_through(hwnd):
    """Aplica WS_EX_TRANSPARENT a una ventana por su HWND real."""
    estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
        estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT)

def quitar_click_through(hwnd):
    estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
        estilo & ~WS_EX_TRANSPARENT)

def hwnd_de(ventana):
    """Obtiene el HWND real de una ventana tkinter."""
    return ctypes.windll.user32.GetParent(ventana.winfo_id())

# ==========================================
# DETECCIÓN DE CURSOR VISIBLE (Windows API)
# ==========================================

class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",   ctypes.c_uint32),
        ("flags",    ctypes.c_uint32),
        ("hCursor",  ctypes.c_void_p),
        ("ptScreenX", ctypes.c_int32),
        ("ptScreenY", ctypes.c_int32),
    ]

CURSOR_SHOWING = 0x00000001

def cursor_visible():
    """
    Devuelve True si el sistema tiene el cursor visible.
    Cuando el juego captura el ratón (modo FPS/juego), flags=0.
    Cuando hay menú o cursor libre, flags=CURSOR_SHOWING (1).
    """
    info = CURSORINFO()
    info.cbSize = ctypes.sizeof(CURSORINFO)
    ctypes.windll.user32.GetCursorInfo(ctypes.byref(info))
    return bool(info.flags & CURSOR_SHOWING)

# Estado previo para detectar cambios sin aplicar el flag en cada tick
_cursor_era_visible = None

def hilo_vigilar_cursor():
    """
    Revisa cada 100ms si el cursor cambió de estado.
    Si se hizo visible → quita click-through de win_barra (barra interactuable).
    Si se ocultó      → aplica click-through a win_barra (barra transparente).
    win_panel siempre tiene click-through; nunca cambia.
    """
    global _cursor_era_visible
    while ejecutando:
        visible = cursor_visible()
        if visible != _cursor_era_visible:
            _cursor_era_visible = visible
            try:
                hwnd_b = hwnd_de(win_barra)
                if visible:
                    quitar_click_through(hwnd_b)   # cursor libre → barra clicable
                else:
                    aplicar_click_through(hwnd_b)  # juego captura cursor → barra inerte
            except:
                pass
        time.sleep(0.1)


# ==========================================
# ARQUITECTURA: DOS VENTANAS SEPARADAS
# ==========================================

BARRA_H = 36
WIN_W   = WIN_W_CFG
WIN_H   = WIN_H_CFG
WIN_X   = WIN_X_CFG
WIN_Y   = WIN_Y_CFG
MIN_W   = 300
MIN_H   = 100

# --- Ventana raíz oculta ---
root = tk.Tk()
root.withdraw()

# --- Ventana fantasma para el icono en la barra de tareas ---
import ctypes.wintypes
taskbar_win = tk.Toplevel(root)
taskbar_win.title("Traductor PSO")
taskbar_win.geometry("1x1+-9999+-9999")
taskbar_win.resizable(False, False)
taskbar_win.attributes("-alpha", 0.01)

# --- Ventana BARRA (interactuable) ---
win_barra = tk.Toplevel(taskbar_win)
win_barra.overrideredirect(True)
win_barra.geometry(f"{WIN_W}x{BARRA_H}+{WIN_X}+{WIN_Y}")
win_barra.attributes("-topmost", True)
win_barra.config(bg="#1a1a1a")
win_barra.attributes("-alpha", 0.92)

# --- Ventana PANEL (click-through en modo chat) ---
win_panel = tk.Toplevel(taskbar_win)
win_panel.overrideredirect(True)
win_panel.geometry(f"{WIN_W}x{WIN_H}+{WIN_X}+{WIN_Y + BARRA_H}")
win_panel.attributes("-topmost", True)
win_panel.config(bg="#121212")
win_panel.attributes("-alpha", 0.85)


# ==========================================
# MOVER — arrastrar barra mueve ambas
# ==========================================

def iniciar_arrastre(event):
    win_barra._drag_x = event.x
    win_barra._drag_y = event.y

def mover_ventana(event):
    dx = event.x - win_barra._drag_x
    dy = event.y - win_barra._drag_y
    bx = win_barra.winfo_x() + dx
    by = win_barra.winfo_y() + dy
    win_barra.geometry(f"+{bx}+{by}")
    win_panel.geometry(f"+{bx}+{by + BARRA_H}")


# ==========================================
# PANEL — dos frames que se intercambian
# frame_chat    → los dos cuadros de texto (vista normal)
# frame_ajustes → configuración integrada
# ==========================================

# Contenedor principal del panel
contenedor = tk.Frame(win_panel, bg="#121212")
contenedor.pack(fill="both", expand=True)

# ---- FRAME CHAT ----
frame_chat = tk.Frame(contenedor, bg="#121212")

panel = tk.PanedWindow(frame_chat, orient=tk.HORIZONTAL, bg="#1a1a1a", bd=0, sashwidth=6)
panel.pack(expand=True, fill="both", padx=5, pady=5)

txt_original = tk.Text(panel, fg="#aaaaaa", bg="#121212", font=("Arial", 9),
    wrap="word", state="disabled", bd=0)
txt_traducido = tk.Text(panel, fg="#ffcc00", bg="#121212", font=("Arial", 10, "bold"),
    wrap="word", state="disabled", bd=0)
panel.add(txt_original, minsize=50)
panel.add(txt_traducido, minsize=100)

def ajustar_sash():
    """Reposiciona el divisor: <500px → original 20%, >=500px → 50/50."""
    w = win_panel.winfo_width()
    if w < 500:
        sash_pos = max(50, int(w * 0.20))
    else:
        sash_pos = w // 2
    try: panel.sash_place(0, sash_pos, 0)
    except: pass

txt_original.config(font=("Arial", ZOOM_O_CFG))
txt_traducido.config(font=("Arial", ZOOM_T_CFG, "bold"))

txt_original.tag_config("prefijo_orig",  foreground="#00ffcc", font=("Arial", ZOOM_O_CFG, "bold"))
txt_original.tag_config("msg_orig",      foreground="#aaaaaa", font=("Arial", ZOOM_O_CFG))
txt_original.tag_config("sistema_orig",  foreground="#666666", font=("Arial", ZOOM_O_CFG, "italic"))
txt_traducido.tag_config("prefijo_trad", foreground="#00ffcc", font=("Arial", ZOOM_T_CFG, "bold"))
txt_traducido.tag_config("msg_trad",     foreground="#ffcc00", font=("Arial", ZOOM_T_CFG, "bold"))
txt_traducido.tag_config("sistema_trad", foreground="#888888", font=("Arial", ZOOM_T_CFG, "italic"))

# ---- FRAME AJUSTES ----
# Usamos un canvas con scrollbar para que quepa todo el contenido
frame_ajustes_outer = tk.Frame(contenedor, bg="#1a1a1a")

_canvas_aj = tk.Canvas(frame_ajustes_outer, bg="#1a1a1a", highlightthickness=0)
_scroll_aj = tk.Scrollbar(frame_ajustes_outer, orient="vertical",
    command=_canvas_aj.yview)
_canvas_aj.configure(yscrollcommand=_scroll_aj.set)

_scroll_aj.pack(side="right", fill="y")
_canvas_aj.pack(side="left", fill="both", expand=True)

# Frame interior que contiene todos los widgets de ajustes
frame_ajustes = tk.Frame(_canvas_aj, bg="#1a1a1a")
_canvas_aj_window = _canvas_aj.create_window((0, 0), window=frame_ajustes, anchor="nw")

def _aj_on_resize(e):
    _canvas_aj.itemconfig(_canvas_aj_window, width=e.width)
_canvas_aj.bind("<Configure>", _aj_on_resize)

def _aj_update_scroll(e=None):
    _canvas_aj.configure(scrollregion=_canvas_aj.bbox("all"))
frame_ajustes.bind("<Configure>", _aj_update_scroll)

# Scroll con rueda del ratón sobre el canvas de ajustes
def _aj_mousewheel(e):
    _canvas_aj.yview_scroll(int(-1 * (e.delta / 120)), "units")
_canvas_aj.bind("<MouseWheel>", _aj_mousewheel)
frame_ajustes.bind("<MouseWheel>", _aj_mousewheel)

def mostrar_chat():
    """Vuelve a la vista de chat y reactiva click-through."""
    frame_ajustes_outer.pack_forget()
    frame_chat.pack(fill="both", expand=True)
    label_titulo.config(text=f"TRADUCTOR | [{TECLA_HOTKEY.upper()}]")
    try: aplicar_click_through(hwnd_de(win_panel))
    except: pass
    try: en_ajustes["val"] = False
    except: pass

def mostrar_ajustes():
    """Muestra la vista de ajustes y quita click-through para poder interactuar."""
    frame_chat.pack_forget()
    frame_ajustes_outer.pack(fill="both", expand=True)
    _canvas_aj.yview_moveto(0)   # scroll al inicio cada vez que se abre
    label_titulo.config(text="⚙  AJUSTES")
    try: quitar_click_through(hwnd_de(win_panel))
    except: pass

# Cabecera de ajustes con botón atrás
cab_aj = tk.Frame(frame_ajustes, bg="#1a1a1a")
cab_aj.pack(fill="x", padx=10, pady=(10, 0))

tk.Button(cab_aj, text="← Volver", bg="#2a2a2a", fg="#00ffcc",
    activebackground="#3a3a3a", bd=0, font=("Arial", 9, "bold"),
    cursor="hand2", command=mostrar_chat).pack(side="left")

# ---- Sección: Tecla hotkey ----
sec_tecla = tk.LabelFrame(frame_ajustes, text=" Tecla para mostrar/ocultar ",
    bg="#1a1a1a", fg="#00ffcc", font=("Arial", 8, "bold"), bd=1, relief="groove")
sec_tecla.pack(fill="x", padx=10, pady=(12, 0))

lbl_tecla_actual = tk.Label(sec_tecla, text=f"Tecla actual:  [ {TECLA_HOTKEY.upper()} ]",
    bg="#1a1a1a", fg="#ffcc00", font=("Arial", 10, "bold"))
lbl_tecla_actual.pack(pady=(6, 2))

lbl_tecla_instruc = tk.Label(sec_tecla,
    text="Pulsa el botón y luego la nueva tecla",
    bg="#1a1a1a", fg="#888888", font=("Arial", 8))
lbl_tecla_instruc.pack()

btn_capturar_tecla = tk.Button(sec_tecla, text="🎯 Cambiar tecla",
    bg="#2a2a2a", fg="white", activebackground="#3a3a3a",
    bd=0, font=("Arial", 9, "bold"), cursor="hand2")
btn_capturar_tecla.pack(pady=(4, 8))

esperando_tecla = {"activo": False}

def activar_captura_tecla():
    esperando_tecla["activo"] = True
    btn_capturar_tecla.config(text="⌨  Pulsa una tecla...", fg="#ffcc00")
    win_panel.bind("<Key>", capturar_nueva_tecla)
    win_panel.focus_force()

def capturar_nueva_tecla(e):
    global TECLA_HOTKEY
    if not esperando_tecla["activo"]: return
    if e.keysym in ("Escape", "Return", "space"): return
    esperando_tecla["activo"] = False
    TECLA_HOTKEY = e.keysym
    guardar_config(TECLA_HOTKEY, MODO_JUEGO, CHAT_X1, CHAT_Y1, CHAT_X2, CHAT_Y2)
    keyboard.remove_all_hotkeys()
    keyboard.add_hotkey(TECLA_HOTKEY, alternar_ventana)
    lbl_tecla_actual.config(text=f"Tecla actual:  [ {TECLA_HOTKEY.upper()} ]")
    label_titulo.config(text="⚙  AJUSTES")
    btn_capturar_tecla.config(text="🎯 Cambiar tecla", fg="white")
    win_panel.unbind("<Key>")

btn_capturar_tecla.config(command=activar_captura_tecla)

# ---- Sección: Tamaño del texto ----
sec_zoom = tk.LabelFrame(frame_ajustes, text=" Tamaño del texto ",
    bg="#1a1a1a", fg="#00ffcc", font=("Arial", 8, "bold"), bd=1, relief="groove")
sec_zoom.pack(fill="x", padx=10, pady=(12, 0))

zoom_frame = tk.Frame(sec_zoom, bg="#1a1a1a")
zoom_frame.pack(pady=8)

lbl_zoom = tk.Label(zoom_frame, text="Tamaño:", bg="#1a1a1a", fg="#aaaaaa", font=("Arial", 9))
lbl_zoom.pack(side="left", padx=(0, 8))

tam_original  = {"val": ZOOM_O_CFG}
tam_traducido = {"val": ZOOM_T_CFG}

lbl_tam_val = tk.Label(zoom_frame,
    text=f"{tam_original['val']} / {tam_traducido['val']} pt",
    bg="#1a1a1a", fg="#ffcc00", font=("Arial", 10, "bold"), width=10)
lbl_tam_val.pack(side="left")

def cambiar_zoom(delta):
    nuevo_o = max(7, min(20, tam_original["val"] + delta))
    nuevo_t = max(7, min(20, tam_traducido["val"] + delta))
    tam_original["val"]  = nuevo_o
    tam_traducido["val"] = nuevo_t
    txt_original.config(font=("Arial", nuevo_o))
    txt_traducido.config(font=("Arial", nuevo_t, "bold"))
    lbl_tam_val.config(text=f"{nuevo_o} / {nuevo_t} pt")
    try: guardar_config_completa()
    except: pass

tk.Button(zoom_frame, text="−", bg="#2a2a2a", fg="white",
    activebackground="#3a3a3a", bd=0, font=("Arial", 12, "bold"),
    cursor="hand2", width=2,
    command=lambda: cambiar_zoom(-1)).pack(side="left", padx=4)

tk.Button(zoom_frame, text="+", bg="#2a2a2a", fg="white",
    activebackground="#3a3a3a", bd=0, font=("Arial", 12, "bold"),
    cursor="hand2", width=2,
    command=lambda: cambiar_zoom(+1)).pack(side="left", padx=4)

# ---- Sección: Tamaño de la ventana ----
sec_ventana = tk.LabelFrame(frame_ajustes, text=" Tamaño de la ventana ",
    bg="#1a1a1a", fg="#00ffcc", font=("Arial", 8, "bold"), bd=1, relief="groove")
sec_ventana.pack(fill="x", padx=10, pady=(12, 0))

# Ancho
fila_ancho = tk.Frame(sec_ventana, bg="#1a1a1a")
fila_ancho.pack(fill="x", padx=8, pady=(8, 2))
tk.Label(fila_ancho, text="Ancho:", bg="#1a1a1a", fg="#aaaaaa",
    font=("Arial", 9), width=8, anchor="w").pack(side="left")

lbl_ancho_val = tk.Label(fila_ancho, text=f"{WIN_W} px",
    bg="#1a1a1a", fg="#ffcc00", font=("Arial", 9, "bold"), width=7)
lbl_ancho_val.pack(side="left")

def cambiar_ancho(delta):
    global WIN_W
    WIN_W = max(300, min(1800, WIN_W + delta))
    bx = win_barra.winfo_x()
    by = win_barra.winfo_y()
    win_barra.geometry(f"{WIN_W}x{BARRA_H}+{bx}+{by}")
    win_panel.geometry(f"{WIN_W}x{WIN_H}+{bx}+{by + BARRA_H}")
    lbl_ancho_val.config(text=f"{WIN_W} px")
    try: guardar_config_completa()
    except: pass
    # Reposicionar el sash: si ancho < 500 el original ocupa 20%, si no 50%
    win_panel.after(50, ajustar_sash)

tk.Button(fila_ancho, text="−", bg="#2a2a2a", fg="white", activebackground="#3a3a3a",
    bd=0, font=("Arial", 11, "bold"), cursor="hand2", width=2,
    command=lambda: cambiar_ancho(-50)).pack(side="left", padx=2)
tk.Button(fila_ancho, text="+", bg="#2a2a2a", fg="white", activebackground="#3a3a3a",
    bd=0, font=("Arial", 11, "bold"), cursor="hand2", width=2,
    command=lambda: cambiar_ancho(+50)).pack(side="left", padx=2)

# Alto
fila_alto = tk.Frame(sec_ventana, bg="#1a1a1a")
fila_alto.pack(fill="x", padx=8, pady=(2, 8))
tk.Label(fila_alto, text="Alto:", bg="#1a1a1a", fg="#aaaaaa",
    font=("Arial", 9), width=8, anchor="w").pack(side="left")

lbl_alto_val = tk.Label(fila_alto, text=f"{WIN_H} px",
    bg="#1a1a1a", fg="#ffcc00", font=("Arial", 9, "bold"), width=7)
lbl_alto_val.pack(side="left")

def cambiar_alto(delta):
    global WIN_H
    WIN_H = max(100, min(900, WIN_H + delta))
    bx = win_barra.winfo_x()
    by = win_barra.winfo_y()
    win_panel.geometry(f"{WIN_W}x{WIN_H}+{bx}+{by + BARRA_H}")
    lbl_alto_val.config(text=f"{WIN_H} px")
    try: guardar_config_completa()
    except: pass

tk.Button(fila_alto, text="−", bg="#2a2a2a", fg="white", activebackground="#3a3a3a",
    bd=0, font=("Arial", 11, "bold"), cursor="hand2", width=2,
    command=lambda: cambiar_alto(-30)).pack(side="left", padx=2)
tk.Button(fila_alto, text="+", bg="#2a2a2a", fg="white", activebackground="#3a3a3a",
    bd=0, font=("Arial", 11, "bold"), cursor="hand2", width=2,
    command=lambda: cambiar_alto(+30)).pack(side="left", padx=2)

# ---- Sección: Zona del chat ----
sec_zona = tk.LabelFrame(frame_ajustes, text=" Zona del chat (captura OCR) ",
    bg="#1a1a1a", fg="#00ffcc", font=("Arial", 8, "bold"), bd=1, relief="groove")
sec_zona.pack(fill="x", padx=10, pady=(12, 0))

lbl_zona_val = tk.Label(sec_zona,
    text=f"({CHAT_X1},{CHAT_Y1}) → ({CHAT_X2},{CHAT_Y2})",
    bg="#1a1a1a", fg="#ffcc00", font=("Arial", 9, "bold"))
lbl_zona_val.pack(pady=(6, 4))

def abrir_zona_desde_ajustes():
    """Cierra ajustes temporalmente, abre el selector, y al volver actualiza el label."""
    mostrar_chat()
    en_ajustes["val"] = False

    def _reabrir_ajustes_tras_zona():
        # Espera a que el selector cierre (lo detectamos por cambio en CHAT_X1)
        lbl_zona_val.config(
            text=f"({CHAT_X1},{CHAT_Y1}) → ({CHAT_X2},{CHAT_Y2})")
        mostrar_ajustes()
        en_ajustes["val"] = True

    # Abre el selector y programa la reapertura de ajustes 500ms después
    # (el selector es síncrono desde el punto de vista de tkinter)
    abrir_selector_zona()
    win_panel.after(500, _reabrir_ajustes_tras_zona)

tk.Button(sec_zona, text="✂  Seleccionar zona en pantalla",
    bg="#2a2a2a", fg="#00ffcc", activebackground="#3a3a3a",
    bd=0, font=("Arial", 9, "bold"), cursor="hand2",
    command=abrir_zona_desde_ajustes).pack(pady=(0, 8))

# ---- Sección: CS2 ----
cs2_encontrado = os.path.exists(RUTA_LOG_CS2)

sec_cs2 = tk.LabelFrame(frame_ajustes, text=" CS2 — console.log ",
    bg="#1a1a1a", fg="#00ffcc", font=("Arial", 8, "bold"), bd=1, relief="groove")
sec_cs2.pack(fill="x", padx=10, pady=(12, 10))

if cs2_encontrado:
    # ✔ Encontrado — mostrar ruta y tick verde
    fila_cs2_estado = tk.Frame(sec_cs2, bg="#1a1a1a")
    fila_cs2_estado.pack(fill="x", padx=8, pady=(8, 2))

    tk.Label(fila_cs2_estado, text="✔  CS2 detectado",
        bg="#1a1a1a", fg="#00ff88", font=("Arial", 10, "bold")).pack(side="left")

    lbl_cs2_ruta = tk.Label(sec_cs2,
        text=RUTA_LOG_CS2, bg="#1a1a1a", fg="#666666",
        font=("Arial", 7), wraplength=360, justify="left")
    lbl_cs2_ruta.pack(padx=8, pady=(0, 4), anchor="w")

    def cambiar_cs2_ruta():
        """Permite seleccionar manualmente aunque ya esté detectado."""
        global RUTA_LOG_CS2
        from tkinter import filedialog
        nueva = filedialog.askopenfilename(
            title="Selecciona console.log de CS2",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
            initialdir=os.path.dirname(RUTA_LOG_CS2)
        )
        if nueva:
            RUTA_LOG_CS2 = nueva
            lbl_cs2_ruta.config(text=RUTA_LOG_CS2)

    tk.Button(sec_cs2, text="📁  Cambiar ruta",
        bg="#2a2a2a", fg="#aaaaaa", activebackground="#3a3a3a",
        bd=0, font=("Arial", 8), cursor="hand2",
        command=cambiar_cs2_ruta).pack(pady=(0, 8))

else:
    # ✘ No encontrado — mostrar aviso y buscador
    fila_cs2_estado = tk.Frame(sec_cs2, bg="#1a1a1a")
    fila_cs2_estado.pack(fill="x", padx=8, pady=(8, 2))

    tk.Label(fila_cs2_estado, text="✘  CS2 no detectado",
        bg="#1a1a1a", fg="#ff4444", font=("Arial", 10, "bold")).pack(side="left")

    tk.Label(sec_cs2,
        text="Localiza manualmente el archivo console.log\ndentro de la carpeta de CS2.",
        bg="#1a1a1a", fg="#888888", font=("Arial", 8), justify="left").pack(
        padx=8, pady=(2, 4), anchor="w")

    lbl_cs2_ruta = tk.Label(sec_cs2,
        text="Sin seleccionar", bg="#1a1a1a", fg="#555555",
        font=("Arial", 7), wraplength=360, justify="left")
    lbl_cs2_ruta.pack(padx=8, pady=(0, 4), anchor="w")

    def seleccionar_cs2_ruta():
        global RUTA_LOG_CS2
        from tkinter import filedialog
        nueva = filedialog.askopenfilename(
            title="Selecciona console.log de CS2",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
            initialdir="C:\\"
        )
        if nueva:
            RUTA_LOG_CS2 = nueva
            lbl_cs2_ruta.config(text=RUTA_LOG_CS2, fg="#ffcc00")
            btn_cs2_buscar.config(text="📁  Cambiar ruta", fg="#aaaaaa")
            lbl_cs2_estado_icon.config(text="✔  Ruta asignada", fg="#00ff88")

    lbl_cs2_estado_icon = fila_cs2_estado.children.get("!label") or         tk.Label(fila_cs2_estado, text="✘  CS2 no detectado",
            bg="#1a1a1a", fg="#ff4444", font=("Arial", 10, "bold"))

    # Re-grab the label we already packed
    for w in fila_cs2_estado.winfo_children():
        lbl_cs2_estado_icon = w
        break

    btn_cs2_buscar = tk.Button(sec_cs2, text="📁  Buscar console.log",
        bg="#2a2a2a", fg="#00ffcc", activebackground="#3a3a3a",
        bd=0, font=("Arial", 9, "bold"), cursor="hand2",
        command=seleccionar_cs2_ruta)
    btn_cs2_buscar.pack(pady=(0, 8))

# Mostrar chat por defecto al arrancar
frame_chat.pack(fill="both", expand=True)


# ==========================================
# BARRA — contenido
# ==========================================

frame_sup = tk.Frame(win_barra, bg="#1a1a1a", cursor="fleur")
frame_sup.pack(fill="both", expand=True, padx=5, pady=4)

label_titulo = tk.Label(frame_sup, text=f"TRADUCTOR | [{TECLA_HOTKEY.upper()}]",
    fg="#00ffcc", bg="#1a1a1a", font=("Arial", 9, "bold"), cursor="fleur")
label_titulo.pack(side="left", padx=5)

frame_sup.bind("<Button-1>", iniciar_arrastre)
frame_sup.bind("<B1-Motion>", mover_ventana)
label_titulo.bind("<Button-1>", iniciar_arrastre)
label_titulo.bind("<B1-Motion>", mover_ventana)

tk.Button(frame_sup, text="✖", bg="#1a1a1a", fg="#ff4444", activebackground="#ff4444",
    activeforeground="white", bd=0, font=("Arial", 11, "bold"), cursor="hand2",
    command=cerrar_aplicacion).pack(side="right", padx=5)

en_ajustes = {"val": False}

def toggle_ajustes():
    if en_ajustes["val"]:
        mostrar_chat()
        en_ajustes["val"] = False
    else:
        mostrar_ajustes()
        en_ajustes["val"] = True

btn_engranaje = tk.Button(frame_sup, text="⚙️", bg="#1a1a1a", fg="white",
    activebackground="#2a2a2a", bd=0, font=("Arial", 11), cursor="hand2",
    command=toggle_ajustes)
btn_engranaje.pack(side="right", padx=5)

btn_modo = tk.Button(frame_sup, text=f"🎮 Modo: {MODO_JUEGO}", bg="#2a2a2a", fg="white",
    activebackground="#3a3a3a", bd=0, font=("Arial", 8, "bold"),
    cursor="hand2", command=cambiar_modo)
btn_modo.pack(side="right", padx=10)

# (Zona movida a Ajustes)


# ==========================================
# CLICK-THROUGH INICIAL (solo win_panel en modo chat)
# ==========================================

def aplicar_ct_inicial():
    try:
        aplicar_click_through(hwnd_de(win_panel))
    except Exception as e:
        log("ERROR", f"Click-through fallido: {e}")

root.after(600, aplicar_ct_inicial)

root.after(500, ajustar_sash)


# ==========================================
# ALTERNAR VISIBILIDAD
# ==========================================

def alternar_ventana():
    global ventana_visible
    if ventana_visible:
        win_barra.withdraw()
        win_panel.withdraw()
        ventana_visible = False
    else:
        win_barra.deiconify()
        win_panel.deiconify()
        win_barra.attributes("-topmost", True)
        win_panel.attributes("-topmost", True)
        ventana_visible = True


# ==========================================
# ARRANQUE
# ==========================================

def iniciar_todo():
    threading.Thread(target=hilo_capturador,      daemon=True).start()
    threading.Thread(target=hilo_ocr,             daemon=True).start()
    threading.Thread(target=hilo_motor_cs2,       daemon=True).start()
    threading.Thread(target=hilo_vigilar_cursor,  daemon=True).start()
    keyboard.add_hotkey(TECLA_HOTKEY, alternar_ventana)
    log("SISTEMA", f"Modo: {MODO_JUEGO} | Zona: ({CHAT_X1},{CHAT_Y1}) → ({CHAT_X2},{CHAT_Y2}) | Tecla: {TECLA_HOTKEY}")

root.after(1000, iniciar_todo)
root.mainloop()