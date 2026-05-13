#!/usr/bin/env python3
"""
AudioFix Pro
============
Automatiza o processamento de áudio de vídeos:
  1. Extrai o áudio do vídeo (ffmpeg)
  2. Cria canal Esquerdo  = áudio original
  3. Cria canal Direito   = áudio com fase INVERTIDA
  4. Mistura ruídos selecionados (rosa, branco, marrom, azul, violeta, cinza)
     em ambos os canais — cada um com amplitude independente
  5. Copy White — sobreposição de áudio externo mixado sobre o original
     🎤 TTS: converta texto em fala e faça download do WAV gerado
  6. DCB — controle de ganho dinâmico pré-export para manter audibilidade
  7. Exporta MP3 estéreo · 44 100 Hz · CBR 192 kbps
  8. Reúne áudio processado + vídeo original → arquivo final
  9. Gera N variações com metadados únicos (título, artista, data, comentário)
 10. Preview do vídeo processado com painel de informações
 11. Transcrição de áudio estilo YouTube com timestamps, segmentos e exportação
 12. MODO DUAL: Manipular Áudio | Áudio Original (só variações)

Requisitos: Python 3.8+, ffmpeg no PATH
Salvo como .pyw para ocultar o console no Windows.
"""

import sys
import os
import subprocess
import importlib
import platform


# ─── Ocultar console no Windows (fallback caso rode como .py) ────────────────
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


def _color(text, code):
    try:
        tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    except Exception:
        tty = False
    if tty and platform.system() != "Windows":
        return f"\033[{code}m{text}\033[0m"
    return text


def _pip_install(*packages):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def _is_importable(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def _check_python_version():
    v = sys.version_info
    if (v.major, v.minor) < (3, 8):
        sys.exit(1)


def _ensure_packages():
    required = [
        ("numpy",  "numpy"),
        ("scipy",  "scipy"),
    ]
    missing = [(pip, imp) for pip, imp in required if not _is_importable(imp)]
    if not missing:
        return
    names = [p for p, _ in missing]
    _pip_install(*names)
    importlib.invalidate_caches()


def _check_gtts_silent():
    return _is_importable("gtts")

def _check_whisper_silent():
    return _is_importable("faster_whisper") or _is_importable("whisper")

def _check_ffmpeg():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ffmpeg_install_hint():
    s = platform.system()
    if s == "Windows":
        return (
            "ffmpeg não encontrado.\n\n"
            "Como instalar no Windows:\n"
            "  • winget install ffmpeg\n"
            "  • ou baixe em: https://www.gyan.dev/ffmpeg/builds/\n\n"
            "Após instalar, reinicie o AudioFix Pro."
        )
    elif s == "Darwin":
        return "ffmpeg não encontrado.\n\nbrew install ffmpeg"
    else:
        return (
            "ffmpeg não encontrado.\n\n"
            "  Ubuntu/Debian:  sudo apt install ffmpeg\n"
            "  Fedora:         sudo dnf install ffmpeg\n"
            "  Arch Linux:     sudo pacman -S ffmpeg"
        )


# ─── Splash Screen ────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import ttk
import math
import time
import threading


# Paleta (duplicada aqui para o splash, antes do import completo)
_DARK   = "#0d0d0f"
_PANEL  = "#16161a"
_CARD   = "#1e1e24"
_ACCENT = "#7c6af7"
_ACC2   = "#a89cf7"
_TEXT   = "#e8e8f0"
_MUTED  = "#6b6b80"
_GREEN  = "#4ade80"
_TEAL   = "#14b8a6"


class SplashScreen(tk.Tk):
    WIDTH  = 520
    HEIGHT = 380

    STEPS = [
        (0,   "Iniciando AudioFix Pro…"),
        (12,  "Verificando Python 3.8+…"),
        (25,  "Carregando numpy / scipy…"),
        (40,  "Verificando ffmpeg…"),
        (55,  "Verificando gTTS…"),
        (68,  "Verificando Whisper…"),
        (80,  "Construindo interface…"),
        (92,  "Finalizando…"),
        (100, "Pronto!"),
    ]

    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.configure(bg=_DARK)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass

        self._center()
        self._pct      = 0.0
        self._step_lbl = tk.StringVar(value="Iniciando…")
        self._done     = False
        self._angle    = 0.0
        self._build()
        self._fade_in()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - self.WIDTH)  // 2
        y  = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _build(self):
        self.canvas = tk.Canvas(
            self, width=self.WIDTH, height=self.HEIGHT,
            bg=_DARK, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        self._draw_background()

        cx, cy = self.WIDTH // 2, 140
        r = 52
        self._ring_id = self.canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=0, extent=300,
            outline=_ACCENT, width=5, style="arc"
        )
        self._ring_glow_id = self.canvas.create_arc(
            cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4,
            start=60, extent=200,
            outline=_ACC2, width=2, style="arc"
        )

        self.canvas.create_text(
            cx, cy,
            text="🎛️", font=("Segoe UI Emoji", 28),
            fill=_TEXT, anchor="center"
        )

        self.canvas.create_text(
            self.WIDTH // 2, 210,
            text="AudioFix Pro",
            font=("Segoe UI", 22, "bold"),
            fill=_TEXT, anchor="center"
        )
        self.canvas.create_text(
            self.WIDTH // 2, 236,
            text="Processamento de áudio profissional",
            font=("Segoe UI", 10),
            fill=_MUTED, anchor="center"
        )

        bar_x1, bar_y1 = 60, 270
        bar_x2, bar_y2 = self.WIDTH - 60, 286
        bar_h          = bar_y2 - bar_y1
        bar_w          = bar_x2 - bar_x1

        self.canvas.create_rectangle(
            bar_x1, bar_y1, bar_x2, bar_y2,
            fill=_PANEL, outline=_CARD, width=1
        )
        self._bar_x1   = bar_x1
        self._bar_y1   = bar_y1
        self._bar_x2   = bar_x2
        self._bar_y2   = bar_y2
        self._bar_w    = bar_w
        self._bar_fill = self.canvas.create_rectangle(
            bar_x1, bar_y1, bar_x1, bar_y2,
            fill=_ACCENT, outline=""
        )
        self._bar_shine = self.canvas.create_rectangle(
            bar_x1, bar_y1, bar_x1, bar_y1 + bar_h // 2,
            fill=_ACC2, outline=""
        )

        self._pct_text = self.canvas.create_text(
            self.WIDTH // 2, 300,
            text="0%",
            font=("Segoe UI", 9, "bold"),
            fill=_ACCENT, anchor="center"
        )

        self._step_text = self.canvas.create_text(
            self.WIDTH // 2, 318,
            text="Iniciando…",
            font=("Segoe UI", 9),
            fill=_MUTED, anchor="center"
        )

        self.canvas.create_text(
            self.WIDTH // 2, self.HEIGHT - 14,
            text="v3.0  ·  Python + ffmpeg  ·  © 2025 AudioFix",
            font=("Segoe UI", 8),
            fill=_MUTED, anchor="center"
        )

        self.canvas.create_rectangle(
            0, 0, self.WIDTH, 3,
            fill=_ACCENT, outline=""
        )
        self.canvas.create_rectangle(
            0, self.HEIGHT - 3, self.WIDTH, self.HEIGHT,
            fill=_TEAL, outline=""
        )

    def _draw_background(self):
        steps = 20
        for i in range(steps):
            t   = i / steps
            r_c = int(0x0d + (0x16 - 0x0d) * t)
            g_c = int(0x0d + (0x16 - 0x0d) * t)
            b_c = int(0x0f + (0x1a - 0x0f) * t)
            color = f"#{r_c:02x}{g_c:02x}{b_c:02x}"
            y0    = int(i * self.HEIGHT / steps)
            y1    = int((i + 1) * self.HEIGHT / steps)
            self.canvas.create_rectangle(0, y0, self.WIDTH, y1, fill=color, outline="")

    def _fade_in(self, alpha=0.0):
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass
        if alpha < 1.0:
            self.after(16, lambda: self._fade_in(min(alpha + 0.07, 1.0)))
        else:
            self._animate_ring()

    def _animate_ring(self):
        if self._done:
            return
        self._angle = (self._angle + 4) % 360
        try:
            self.canvas.itemconfig(self._ring_id,     start=self._angle)
            self.canvas.itemconfig(self._ring_glow_id, start=(self._angle + 60) % 360)
        except Exception:
            pass
        self.after(18, self._animate_ring)

    def update_progress(self, pct: float, label: str = ""):
        self._pct = pct
        fill_w = int(self._bar_w * pct / 100)
        fx2    = self._bar_x1 + fill_w
        try:
            self.canvas.coords(self._bar_fill,
                               self._bar_x1, self._bar_y1,
                               fx2, self._bar_y2)
            self.canvas.coords(self._bar_shine,
                               self._bar_x1, self._bar_y1,
                               fx2, self._bar_y1 + (self._bar_y2 - self._bar_y1) // 2)
            self.canvas.itemconfig(self._pct_text,  text=f"{int(pct)}%")
            if label:
                self.canvas.itemconfig(self._step_text, text=label)
        except Exception:
            pass

    def finish(self, callback):
        self._done = True
        self._fade_out(1.0, callback)

    def _fade_out(self, alpha, callback):
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass
        if alpha > 0.0:
            self.after(16, lambda: self._fade_out(max(alpha - 0.08, 0.0), callback))
        else:
            self.destroy()
            callback()


# ─── Carregamento em background ───────────────────────────────────────────────

def _run_loading(splash: SplashScreen):
    def step(pct, label, delay=0.0):
        splash.after(0, lambda: splash.update_progress(pct, label))
        if delay:
            time.sleep(delay)

    step(0,  "Iniciando AudioFix Pro…",     0.2)
    step(12, "Verificando Python 3.8+…",    0.1)
    _check_python_version()

    step(25, "Carregando numpy / scipy…",   0.1)
    _ensure_packages()

    step(40, "Verificando ffmpeg…",         0.15)
    global _FFMPEG_OK
    _FFMPEG_OK = _check_ffmpeg()

    step(55, "Verificando gTTS…",           0.1)
    global _GTTS_OK
    _GTTS_OK = _check_gtts_silent()

    step(68, "Verificando Whisper…",        0.1)
    global _WHISPER_OK
    _WHISPER_OK = _check_whisper_silent()

    step(80, "Construindo interface…",      0.2)

    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly

    step(92, "Finalizando…",               0.15)
    step(100, "Pronto!",                   0.35)

    splash.after(0, lambda: splash.finish(_launch_main))


def _launch_main():
    app = AudioFixApp()
    app.mainloop()


# ─── Variáveis globais de status ─────────────────────────────────────────────
_FFMPEG_OK  = False
_WHISPER_OK = False
_GTTS_OK    = False


# ─── Resto do código ──────────────────────────────────────────────────────────

import tempfile
import random
import string
import datetime
import json
import math
from tkinter import filedialog, messagebox
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


# ─── Geradores de ruído ───────────────────────────────────────────────────────

def generate_pink_noise(n_samples, amplitude, seed=42):
    rng = np.random.default_rng(seed)
    n_rows = 16
    pink = np.zeros(n_samples)
    running_sum = np.zeros(n_rows)
    running_sum[:] = rng.random(n_rows)
    total = running_sum.sum()
    for i in range(n_samples):
        k = int(np.log2((i & -i) + 1)) % n_rows if i > 0 else 0
        old_val = running_sum[k]
        running_sum[k] = rng.random()
        total += running_sum[k] - old_val
        pink[i] = total
    pink -= pink.mean()
    mx = np.abs(pink).max()
    if mx > 0: pink = pink / mx * amplitude
    return pink.astype(np.float64)


def generate_white_noise(n_samples, amplitude, seed=43):
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n_samples)
    mx = np.abs(noise).max()
    if mx > 0: noise = noise / mx * amplitude
    return noise.astype(np.float64)


def generate_brown_noise(n_samples, amplitude, seed=44):
    rng = np.random.default_rng(seed)
    brown = np.cumsum(rng.standard_normal(n_samples))
    brown -= brown.mean()
    mx = np.abs(brown).max()
    if mx > 0: brown = brown / mx * amplitude
    return brown.astype(np.float64)


def generate_blue_noise(n_samples, amplitude, seed=45):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n_samples)
    blue = np.diff(white, prepend=white[0])
    blue -= blue.mean()
    mx = np.abs(blue).max()
    if mx > 0: blue = blue / mx * amplitude
    return blue.astype(np.float64)


def generate_violet_noise(n_samples, amplitude, seed=46):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n_samples)
    violet = np.diff(np.diff(white, prepend=white[0]), prepend=white[0])
    violet -= violet.mean()
    mx = np.abs(violet).max()
    if mx > 0: violet = violet / mx * amplitude
    return violet.astype(np.float64)


def generate_grey_noise(n_samples, amplitude, seed=47):
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n_samples)
    fft = np.fft.rfft(white)
    freqs_hz = np.abs(np.fft.rfftfreq(n_samples)) * 44100
    eps = 1e-6
    f = np.maximum(freqs_hz, eps)
    weight = (f/1000.0)**0.3 / (1.0+(f/6000.0)**2.0+(1.0/(f/120.0+eps))**1.5)
    weight = np.maximum(weight, eps) / weight.max()
    grey = np.fft.irfft(fft * weight, n=n_samples)
    grey -= grey.mean()
    mx = np.abs(grey).max()
    if mx > 0: grey = grey / mx * amplitude
    return grey.astype(np.float64)


NOISE_GENERATORS = {
    "Rosa":    generate_pink_noise,
    "Branco":  generate_white_noise,
    "Marrom":  generate_brown_noise,
    "Azul":    generate_blue_noise,
    "Violeta": generate_violet_noise,
    "Cinza":   generate_grey_noise,
}

NOISE_DESCRIPTIONS = {
    "Rosa":    "1/f · equilíbrio natural",
    "Branco":  "energia uniforme em todas as freq.",
    "Marrom":  "1/f² · grave e profundo",
    "Azul":    "f · ênfase nos agudos",
    "Violeta": "f² · agudos muito acentuados",
    "Cinza":   "eq. psicoacústica (igual loudness)",
}


# ─── Níveis de variação de metadados ─────────────────────────────────────────

VARIATION_LEVELS = {
    "Normal": {
        "label":       "Normal",
        "desc":        "Mudanças sutis · título leve · data próxima",
        "color":       "#4ade80",
        "title_len":   4,
        "artist_len":  4,
        "album_len":   3,
        "comment_len": 6,
        "date_range":  30,
        "track_range": (1, 20),
        "encoder_var": False,
    },
    "Moderada": {
        "label":       "Moderada",
        "desc":        "Alterações médias · campos misturados",
        "color":       "#fbbf24",
        "title_len":   6,
        "artist_len":  5,
        "album_len":   4,
        "comment_len": 9,
        "date_range":  365,
        "track_range": (1, 50),
        "encoder_var": True,
    },
    "Intensa": {
        "label":       "Intensa",
        "desc":        "Metadados bem distintos · datas variadas",
        "color":       "#f97316",
        "title_len":   8,
        "artist_len":  7,
        "album_len":   6,
        "comment_len": 12,
        "date_range":  1095,
        "track_range": (1, 99),
        "encoder_var": True,
    },
    "Brusca": {
        "label":       "Brusca",
        "desc":        "Metadados completamente aleatórios · máxima divergência",
        "color":       "#f87171",
        "title_len":   12,
        "artist_len":  10,
        "album_len":   9,
        "comment_len": 18,
        "date_range":  3650,
        "track_range": (1, 999),
        "encoder_var": True,
    },
}


def _rand_str(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def _rand_date(max_days_back=365):
    today = datetime.date.today()
    start = today - datetime.timedelta(days=max_days_back)
    delta = (today - start).days
    return str(start + datetime.timedelta(days=random.randint(0, delta)))

def generate_metadata_variants(n, level="Normal"):
    cfg = VARIATION_LEVELS.get(level, VARIATION_LEVELS["Normal"])
    result = []
    for _ in range(n):
        meta = {
            "title":   f"Video_{_rand_str(cfg['title_len'])}",
            "artist":  f"Creator_{_rand_str(cfg['artist_len'])}",
            "album":   f"Collection_{_rand_str(cfg['album_len'])}",
            "comment": f"Processed_{_rand_str(cfg['comment_len'])}",
            "date":    _rand_date(cfg['date_range']),
            "track":   str(random.randint(*cfg['track_range'])),
        }
        if cfg["encoder_var"]:
            meta["encoder"] = f"Encoder_{_rand_str(4)}_{random.randint(1,99)}"
        result.append(meta)
    return result


def _ensure_stereo_1d(arr):
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr[:, 0]
    raise ValueError(f"Array de áudio com shape inesperado: {arr.shape}")


def _ensure_stereo_2col(arr, n_samples):
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    elif arr.ndim == 2 and arr.shape[1] == 1:
        arr = np.concatenate([arr, arr], axis=1)
    elif arr.ndim == 2 and arr.shape[1] > 2:
        arr = arr[:, :2]
    m = len(arr)
    if m == 0:
        return np.zeros((n_samples, 2), dtype=np.float64)
    if m < n_samples:
        repeats = int(np.ceil(n_samples / m))
        arr = np.tile(arr, (repeats, 1))
    return arr[:n_samples]


def load_and_resample_wav(path, target_sr=44100):
    sr, data = wavfile.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    else:
        data = data.astype(np.float64)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] == 1:
        data = np.concatenate([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] > 2:
        data = data[:, :2]
    if sr != target_sr:
        from math import gcd
        g = gcd(sr, target_sr)
        up, down = target_sr // g, sr // g
        data = np.stack([resample_poly(data[:, 0], up, down),
                         resample_poly(data[:, 1], up, down)], axis=1)
    return data, target_sr


def mix_copy_white(base_1d, overlay_2d, channel, overlay_gain=0.5):
    n = len(base_1d)
    if overlay_2d is None or len(overlay_2d) == 0:
        return base_1d
    ov = _ensure_stereo_2col(overlay_2d, n)
    return base_1d + ov[:, channel] * overlay_gain


def apply_dcb(data, threshold=0.5, ratio=4.0, makeup_gain=1.8):
    out = data.copy()
    mask = np.abs(out) > threshold
    excess = np.abs(out[mask]) - threshold
    out[mask] = np.sign(out[mask]) * (threshold + excess / ratio)
    return np.clip(out * makeup_gain, -1.0, 1.0)


def process_audio(input_wav, output_wav, noise_amplitudes=None,
                  copy_white_path=None, copy_white_gain=0.5,
                  dcb_enabled=False, dcb_threshold=0.5,
                  dcb_ratio=4.0, dcb_makeup=1.8, target_sr=44100):
    if noise_amplitudes is None:
        noise_amplitudes = {"Rosa": 0.003}

    sr, data = wavfile.read(input_wav)
    if data.dtype == np.int16:
        data = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    else:
        data = data.astype(np.float64)

    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] == 1:
        data = np.concatenate([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] > 2:
        data = data[:, :2]

    if sr != target_sr:
        from math import gcd
        g = gcd(sr, target_sr)
        up, down = target_sr // g, sr // g
        data = np.stack([resample_poly(data[:, 0], up, down),
                         resample_poly(data[:, 1], up, down)], axis=1)
        sr = target_sr

    n = len(data)
    left  = data[:, 0].copy()
    right = -data[:, 0].copy()

    for idx, (name, amp) in enumerate(noise_amplitudes.items()):
        if amp <= 0:
            continue
        gen = NOISE_GENERATORS.get(name)
        if gen is None:
            continue
        noise = gen(n, amp, seed=42 + idx)
        left  += noise
        right += noise

    if copy_white_path and os.path.isfile(copy_white_path):
        cw, _ = load_and_resample_wav(copy_white_path, target_sr)
        left  = mix_copy_white(left,  cw, channel=0, overlay_gain=copy_white_gain)
        right = mix_copy_white(right, cw, channel=1, overlay_gain=copy_white_gain)

    left  = np.clip(left,  -1.0, 1.0)
    right = np.clip(right, -1.0, 1.0)

    if dcb_enabled:
        stereo = apply_dcb(np.stack([left, right], axis=1),
                           dcb_threshold, dcb_ratio, dcb_makeup)
        left, right = stereo[:, 0], stereo[:, 1]

    wavfile.write(output_wav, sr,
                  np.stack([left, right], axis=1).astype(np.float32))


def run(cmd, log_fn=None):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
    for line in proc.stdout:
        if log_fn: log_fn(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Comando falhou (código {proc.returncode}): {' '.join(cmd)}")


def extract_audio(video_path, wav_path, log_fn=None):
    run(["ffmpeg", "-y", "-i", video_path,
         "-vn", "-acodec", "pcm_f32le", "-ar", "44100", wav_path], log_fn)


def extract_audio_for_transcription(video_path, wav_path, log_fn=None):
    run(["ffmpeg", "-y", "-i", video_path,
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path], log_fn)


def wav_to_mp3(wav_path, mp3_path, log_fn=None):
    run(["ffmpeg", "-y", "-i", wav_path,
         "-acodec", "libmp3lame", "-b:a", "192k",
         "-ar", "44100", "-ac", "2", mp3_path], log_fn)


def merge_audio_video(video_path, audio_path, output_path,
                      metadata=None, log_fn=None):
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", audio_path,
           "-c:v", "copy", "-c:a", "copy",
           "-map", "0:v:0", "-map", "1:a:0"]
    if metadata:
        for k, v in metadata.items():
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(output_path)
    run(cmd, log_fn)


def copy_video_only(video_path, output_path, metadata=None, log_fn=None):
    cmd = ["ffmpeg", "-y", "-i", video_path,
           "-c:v", "copy", "-c:a", "copy"]
    if metadata:
        for k, v in metadata.items():
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(output_path)
    run(cmd, log_fn)


def get_video_info(path):
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_streams", "-show_format", path]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            info = {}
            fmt = data.get("format", {})
            info["duration"] = float(fmt.get("duration", 0))
            info["size_mb"]  = os.path.getsize(path) / (1024*1024)
            info["bitrate"]  = int(fmt.get("bit_rate", 0)) // 1000
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info["video_codec"] = stream.get("codec_name", "?")
                    info["width"]       = stream.get("width", 0)
                    info["height"]      = stream.get("height", 0)
                    try:
                        n, d = stream.get("r_frame_rate","0/1").split("/")
                        info["fps"] = round(int(n)/int(d), 2)
                    except: info["fps"] = 0
                elif stream.get("codec_type") == "audio":
                    info["audio_codec"]    = stream.get("codec_name", "?")
                    info["sample_rate"]    = stream.get("sample_rate", "?")
                    info["channels"]       = stream.get("channels", 0)
                    info["channel_layout"] = stream.get("channel_layout", "?")
            return info
    except: pass
    return {}


def open_video_player(path):
    if sys.platform == "win32":   os.startfile(path)
    elif sys.platform == "darwin": subprocess.Popen(["open", path])
    else:
        for p in ["xdg-open","vlc","mpv","mplayer","totem"]:
            try: subprocess.Popen([p, path]); return
            except FileNotFoundError: continue


# ─── Pipelines ────────────────────────────────────────────────────────────────

def full_pipeline_audio(video_path, output_path, noise_amplitudes=None,
                        copy_white_path=None, copy_white_gain=0.5,
                        dcb_enabled=False, dcb_threshold=0.5,
                        dcb_ratio=4.0, dcb_makeup=1.8,
                        n_variants=0, variation_level="Normal",
                        progress_cb=None, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    if noise_amplitudes is None:
        noise_amplitudes = {"Rosa": 0.003}
    ativos = {k: v for k, v in noise_amplitudes.items() if v > 0}
    log(f"🔊 Ruídos ativos: {' · '.join(f'{k}={v:.4f}' for k,v in ativos.items()) if ativos else 'nenhum'}")
    if copy_white_path: log(f"📻 Copy White: {os.path.basename(copy_white_path)}  ganho={copy_white_gain:.2f}")
    if dcb_enabled: log(f"🎚  DCB: threshold={dcb_threshold:.2f} · ratio={dcb_ratio:.1f}:1 · makeup={dcb_makeup:.2f}x")
    with tempfile.TemporaryDirectory(prefix="audiofix_") as tmp:
        raw_wav  = os.path.join(tmp, "raw.wav")
        proc_wav = os.path.join(tmp, "processed.wav")
        out_mp3  = os.path.join(tmp, "processed.mp3")
        log("▶ Extraindo áudio do vídeo…")
        extract_audio(video_path, raw_wav, log)
        if progress_cb: progress_cb(20)
        log("▶ Aplicando inversão de fase + ruídos + copy white + DCB…")
        process_audio(raw_wav, proc_wav, noise_amplitudes=noise_amplitudes,
                      copy_white_path=copy_white_path, copy_white_gain=copy_white_gain,
                      dcb_enabled=dcb_enabled, dcb_threshold=dcb_threshold,
                      dcb_ratio=dcb_ratio, dcb_makeup=dcb_makeup)
        if progress_cb: progress_cb(45)
        log("▶ Convertendo para MP3…")
        wav_to_mp3(proc_wav, out_mp3, log)
        if progress_cb: progress_cb(65)
        log("▶ Unindo áudio processado ao vídeo original…")
        merge_audio_video(video_path, out_mp3, output_path, log_fn=log)
        if progress_cb: progress_cb(80)
        if n_variants > 0:
            log(f"▶ Gerando {n_variants} variação(ões) [nível: {variation_level}]…")
            base, ext = os.path.splitext(output_path)
            for idx, meta in enumerate(generate_metadata_variants(n_variants, variation_level), 1):
                vp = f"{base}_var{idx:02d}{ext}"
                log(f"   [{idx}/{n_variants}] → {os.path.basename(vp)}")
                merge_audio_video(video_path, out_mp3, vp, metadata=meta, log_fn=log)
                if progress_cb: progress_cb(80 + int((idx/n_variants)*18))
        if progress_cb: progress_cb(100)
        log(f"✅ Concluído! {1+n_variants} arquivo(s) gerado(s).")
        log(f"   Principal → {output_path}")


def full_pipeline_original(video_path, output_path,
                           n_variants=0, variation_level="Normal",
                           progress_cb=None, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    log("🎬 Modo Áudio Original — nenhum processamento de áudio será aplicado.")
    log(f"🎲 Variações: {n_variants}  |  Nível: {variation_level}")
    log("▶ Copiando vídeo original…")
    copy_video_only(video_path, output_path, log_fn=log)
    if progress_cb: progress_cb(60)
    if n_variants > 0:
        log(f"▶ Gerando {n_variants} variação(ões) [nível: {variation_level}]…")
        base, ext = os.path.splitext(output_path)
        for idx, meta in enumerate(generate_metadata_variants(n_variants, variation_level), 1):
            vp = f"{base}_var{idx:02d}{ext}"
            log(f"   [{idx}/{n_variants}] → {os.path.basename(vp)}")
            copy_video_only(video_path, vp, metadata=meta, log_fn=log)
            if progress_cb: progress_cb(60 + int((idx/n_variants)*38))
    if progress_cb: progress_cb(100)
    log(f"✅ Concluído! {1+n_variants} arquivo(s) gerado(s).")
    log(f"   Principal → {output_path}")


# ─── Transcrição ──────────────────────────────────────────────────────────────

def check_whisper_available():
    importlib.invalidate_caches()
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper", faster_whisper
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return "whisper", whisper
    except ImportError:
        pass
    return None, None


def install_whisper_now():
    ok, _ = _pip_install("faster-whisper")
    if ok:
        importlib.invalidate_caches()
    return ok


def format_timestamp(seconds):
    ms = int((seconds % 1)*1000)
    s  = int(seconds) % 60
    m  = int(seconds)//60 % 60
    h  = int(seconds)//3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_yt(seconds):
    return f"{int(seconds)//60:02d}:{int(seconds)%60:02d}"


def transcribe_audio(audio_path, model_size="base", language=None,
                     progress_cb=None, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    backend, mod = check_whisper_available()
    if backend is None:
        raise RuntimeError("Nenhum backend Whisper encontrado.\npip install faster-whisper")
    log(f"🤖 Backend: {backend}  |  Modelo: {model_size}")
    if progress_cb: progress_cb(10)
    segments_out = []
    if backend == "faster-whisper":
        from faster_whisper import WhisperModel
        log("⏳ Carregando modelo faster-whisper…")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        if progress_cb: progress_cb(30)
        log("🎙  Transcrevendo…")
        kwargs = {}
        if language: kwargs["language"] = language
        segments, info = model.transcribe(audio_path, beam_size=5, **kwargs)
        log(f"🌐 Idioma detectado: {info.language}  ({info.language_probability:.0%})")
        if progress_cb: progress_cb(60)
        for seg in segments:
            segments_out.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
    else:
        import whisper
        log("⏳ Carregando modelo whisper…")
        model = mod.load_model(model_size)
        if progress_cb: progress_cb(30)
        log("🎙  Transcrevendo…")
        kwargs = {"verbose": False}
        if language: kwargs["language"] = language
        result = model.transcribe(audio_path, **kwargs)
        if progress_cb: progress_cb(60)
        log(f"🌐 Idioma detectado: {result.get('language','?')}")
        for seg in result.get("segments", []):
            segments_out.append({"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()})
    if progress_cb: progress_cb(90)
    log(f"✅ {len(segments_out)} segmento(s) transcritos.")
    return segments_out


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(f"{i}\n{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n{seg['text']}\n")
    return "\n".join(lines)

def segments_to_vtt(segments):
    lines = ["WEBVTT\n"]
    for i, seg in enumerate(segments, 1):
        s = format_timestamp(seg['start']).replace(",",".")
        e = format_timestamp(seg['end']).replace(",",".")
        lines.append(f"{i}\n{s} --> {e}\n{seg['text']}\n")
    return "\n".join(lines)

def segments_to_txt(segments):
    return "\n".join(s["text"] for s in segments)

def segments_to_youtube_chapters(segments, merge_secs=30.0):
    if not segments:
        return ""
    chapters = []
    current_start = segments[0]["start"]
    current_texts = []
    for seg in segments:
        current_texts.append(seg["text"].strip())
        if seg["end"] - current_start >= merge_secs:
            title = " ".join(current_texts).strip()[:80]
            chapters.append(f"{format_timestamp_yt(current_start)} {title}")
            current_start = seg["end"]
            current_texts = []
    if current_texts:
        title = " ".join(current_texts).strip()[:80]
        chapters.append(f"{format_timestamp_yt(current_start)} {title}")
    if chapters and not chapters[0].startswith("00:00"):
        chapters.insert(0, "00:00 Introdução")
    return "\n".join(chapters)


# ─── TTS ─────────────────────────────────────────────────────────────────────

TTS_VOICES = [
    {"id":"pt-BR-F-slow","label":"🇧🇷 Feminina Suave","desc":"Português BR · feminina · ritmo calmo","lang":"pt-br","slow":True,"tld":"com.br"},
    {"id":"pt-BR-M-normal","label":"🇧🇷 Masculina Serena","desc":"Português BR · masculina · ritmo normal","lang":"pt-br","slow":False,"tld":"com.br"},
    {"id":"en-US-F-slow","label":"🇺🇸 Female Calm","desc":"English US · female · slow pace","lang":"en","slow":True,"tld":"com"},
    {"id":"en-UK-F-slow","label":"🇬🇧 Female Soft","desc":"English UK · female · slow & refined","lang":"en","slow":True,"tld":"co.uk"},
    {"id":"es-ES-F-slow","label":"🇪🇸 Femenina Tranquila","desc":"Español ES · femenina · ritmo pausado","lang":"es","slow":True,"tld":"es"},
    {"id":"fr-FR-F-slow","label":"🇫🇷 Féminine Douce","desc":"Français FR · féminine · rythme lent","lang":"fr","slow":True,"tld":"fr"},
    {"id":"de-DE-F-slow","label":"🇩🇪 Weiblich Sanft","desc":"Deutsch DE · weiblich · langsam","lang":"de","slow":True,"tld":"de"},
    {"id":"it-IT-F-slow","label":"🇮🇹 Femminile Dolce","desc":"Italiano IT · femminile · lento","lang":"it","slow":True,"tld":"it"},
    {"id":"ja-JP-F-slow","label":"🇯🇵 女性・ゆっくり","desc":"日本語 JP · 女性 · ゆっくり","lang":"ja","slow":True,"tld":"co.jp"},
    {"id":"zh-CN-F-normal","label":"🇨🇳 中文 女声","desc":"中文 CN · 女声 · 正常速度","lang":"zh-CN","slow":False,"tld":"com"},
]


def install_gtts_now():
    ok, _ = _pip_install("gtts")
    if ok:
        importlib.invalidate_caches()
    return ok


def text_to_wav(text, voice_id, output_wav, volume_factor=0.4, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    if not _is_importable("gtts"):
        log("⏳ Instalando gTTS…")
        if not install_gtts_now():
            raise RuntimeError("Falha ao instalar gTTS. Execute: pip install gtts")
        importlib.invalidate_caches()
    from gtts import gTTS
    voice = next((v for v in TTS_VOICES if v["id"] == voice_id), TTS_VOICES[0])
    log(f"🔊 Gerando voz: {voice['label']} ({voice['lang']})")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
        tmp_mp3_path = tmp_mp3.name
    tts = gTTS(text=text, lang=voice["lang"], slow=voice["slow"], tld=voice["tld"])
    tts.save(tmp_mp3_path)
    log("✅ Áudio TTS gerado, convertendo para WAV…")
    vol_db = 20 * np.log10(max(volume_factor, 0.01))
    vol_str = f"{vol_db:.1f}dB"
    run(["ffmpeg", "-y", "-i", tmp_mp3_path,
         "-af", f"volume={vol_str}",
         "-ar", "44100", "-ac", "2",
         "-acodec", "pcm_s16le", output_wav], log_cb)
    try:
        os.unlink(tmp_mp3_path)
    except Exception:
        pass
    log(f"✅ WAV salvo: {os.path.basename(output_wav)}")
    return output_wav


# ─── Paleta ───────────────────────────────────────────────────────────────────

DARK   = "#0d0d0f"
PANEL  = "#16161a"
CARD   = "#1e1e24"
ACCENT = "#7c6af7"
ACC2   = "#a89cf7"
TEXT   = "#e8e8f0"
MUTED  = "#6b6b80"
GREEN  = "#4ade80"
RED    = "#f87171"
WARN   = "#fbbf24"
CYAN   = "#22d3ee"
GOLD   = "#f59e0b"
TEAL   = "#14b8a6"
LIME   = "#84cc16"
PURPLE = "#c084fc"
PINK   = "#f472b6"
ORANGE = "#f97316"

NOISE_COLORS = {
    "Rosa": "#f472b6", "Branco": "#e8e8f0", "Marrom": "#d97706",
    "Azul": "#38bdf8", "Violeta": "#c084fc", "Cinza": "#94a3b8",
}

FONT_TITLE  = ("Segoe UI", 22, "bold")
FONT_LABEL  = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_MONO   = ("Consolas", 9)
FONT_STATUS = ("Segoe UI", 9)
FONT_SMALL  = ("Segoe UI", 8)
FONT_H3     = ("Segoe UI", 9, "bold")
INPUT_FG    = "black"
INPUT_BG    = "#f0f0f5"


# ─── Janela TTS ───────────────────────────────────────────────────────────────

class TTSWindow(tk.Toplevel):
    def __init__(self, parent, on_wav_ready=None):
        super().__init__(parent)
        self.title("AudioFix Pro — Texto para Fala (TTS)")
        self.geometry("820x900")
        self.minsize(700, 750)
        self.configure(bg=DARK)
        self.resizable(True, True)
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.on_wav_ready   = on_wav_ready
        self._generated_wav = None
        self._running       = False
        self.voice_var  = tk.StringVar(value=TTS_VOICES[0]["id"])
        self.volume_var = tk.DoubleVar(value=0.40)
        self._voice_btns: dict = {}
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text="🎤  Texto para Fala", font=("Segoe UI", 14, "bold"), bg=PANEL, fg=TEXT).pack(side="left", padx=20)
        tk.Label(hdr, text="gTTS · 10 vozes · download WAV", font=FONT_SMALL, bg=PANEL, fg=MUTED).pack(side="left")
        tk.Button(hdr, text="✕", font=FONT_SMALL, bg=CARD, fg=MUTED, relief="flat", padx=10, pady=4, cursor="hand2", command=self.destroy).pack(side="right", padx=12)

        footer = tk.Frame(self, bg=DARK, pady=12, padx=20)
        footer.pack(fill="x", side="bottom")
        self.use_btn = tk.Button(footer, text="✅  Usar no Copy White", font=("Segoe UI", 10, "bold"), bg=GREEN, fg=DARK, activebackground="#22c55e", activeforeground=DARK, relief="flat", padx=20, pady=9, cursor="hand2", state="disabled", command=self._use_wav)
        self.use_btn.pack(side="right")
        self.download_btn = tk.Button(footer, text="💾  Salvar WAV…", font=("Segoe UI", 10, "bold"), bg=CYAN, fg=DARK, activebackground="#06b6d4", activeforeground=DARK, relief="flat", padx=20, pady=9, cursor="hand2", state="disabled", command=self._download_wav)
        self.download_btn.pack(side="right", padx=(0, 8))
        self.gen_btn = tk.Button(footer, text="🔊  Gerar Fala", font=("Segoe UI", 10, "bold"), bg=TEAL, fg="white", activebackground="#0f9488", activeforeground="white", relief="flat", padx=24, pady=9, cursor="hand2", command=self._start_tts)
        self.gen_btn.pack(side="right", padx=(0, 8))
        tk.Button(footer, text="🗑  Limpar", font=FONT_LABEL, bg=CARD, fg=MUTED, relief="flat", padx=12, pady=9, cursor="hand2", command=self._clear).pack(side="left")

        outer = tk.Frame(self, bg=DARK)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body_frame = tk.Frame(canvas, bg=DARK)
        body_win = canvas.create_window((0, 0), window=body_frame, anchor="nw")
        body_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        body = tk.Frame(body_frame, bg=DARK, padx=20, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        row = 0

        self._section_label(body, row, "✍️  Texto a converter em fala"); row += 1
        text_card = self._card_frame(body, row); row += 1
        char_row = tk.Frame(text_card, bg=CARD)
        char_row.pack(fill="x", pady=(0, 4))
        tk.Label(char_row, text="Digite ou cole o texto:", font=FONT_SMALL, bg=CARD, fg=MUTED).pack(side="left")
        self.char_count_lbl = tk.Label(char_row, text="0 caracteres", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self.char_count_lbl.pack(side="right")
        text_inner = tk.Frame(text_card, bg=CARD)
        text_inner.pack(fill="both", expand=True)
        text_inner.rowconfigure(0, weight=1)
        text_inner.columnconfigure(0, weight=1)
        self.text_input = tk.Text(text_inner, height=10, font=("Consolas", 10), bg="#111116", fg="#c8c8e0", relief="flat", wrap="word", padx=10, pady=8, insertbackground=TEXT, selectbackground=ACCENT)
        self.text_input.grid(row=0, column=0, sticky="nsew")
        sb_text = ttk.Scrollbar(text_inner, command=self.text_input.yview)
        sb_text.grid(row=0, column=1, sticky="ns")
        self.text_input.config(yscrollcommand=sb_text.set)
        self.text_input.bind("<KeyRelease>", self._update_char_count)
        self.text_input.bind("<<Paste>>", lambda e: self.after(10, self._update_char_count))

        ex_row = tk.Frame(text_card, bg=CARD)
        ex_row.pack(fill="x", pady=(6, 0))
        tk.Label(ex_row, text="Exemplos:", font=FONT_SMALL, bg=CARD, fg=MUTED).pack(side="left", padx=(0, 8))
        for label, sample in [
            ("PT Boas-vindas", "Olá! Seja muito bem-vindo."),
            ("EN Welcome", "Hello and welcome!"),
            ("Aviso", "Atenção! Este é um aviso importante."),
        ]:
            tk.Button(ex_row, text=label, font=FONT_SMALL, bg="#2a2a35", fg=ACC2, relief="flat", padx=8, pady=3, cursor="hand2", command=lambda t=sample: self._set_text(t)).pack(side="left", padx=(0, 4))

        self._section_label(body, row, "🎤  Selecionar Voz"); row += 1
        voice_card = self._card_frame(body, row); row += 1
        gtts_ok = _is_importable("gtts")
        tk.Label(voice_card, text="✅ gTTS instalado" if gtts_ok else "⚠️  gTTS instalado automaticamente ao gerar", font=FONT_SMALL, bg=CARD, fg=GREEN if gtts_ok else WARN).pack(anchor="w", pady=(0, 10))
        voice_grid = tk.Frame(voice_card, bg=CARD)
        voice_grid.pack(fill="x")
        voice_grid.columnconfigure(0, weight=1)
        voice_grid.columnconfigure(1, weight=1)
        for i, v in enumerate(TTS_VOICES):
            self._make_voice_card(voice_grid, v, i//2, i%2)

        self._section_label(body, row, "🎛️  Opções de Áudio"); row += 1
        opts_card = self._card_frame(body, row); row += 1
        vol_row = tk.Frame(opts_card, bg=CARD)
        vol_row.pack(fill="x", pady=(0, 6))
        tk.Label(vol_row, text="🔉 Volume:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=14, anchor="w").pack(side="left")
        self.vol_lbl = tk.Label(vol_row, text=f"{int(self.volume_var.get()*100)}%", font=FONT_BOLD, bg=CARD, fg=TEAL, width=5)
        self.vol_lbl.pack(side="right")
        ttk.Scale(vol_row, from_=0.1, to=1.0, variable=self.volume_var, orient="horizontal", command=lambda v: self.vol_lbl.config(text=f"{int(float(v)*100)}%")).pack(side="left", fill="x", expand=True, padx=(8, 8))

        self._section_label(body, row, "⚙️  Status"); row += 1
        status_card = self._card_frame(body, row); row += 1
        self.progress = ttk.Progressbar(status_card, mode="determinate", maximum=100, length=200)
        self.progress.pack(fill="x")
        self.status_lbl = tk.Label(status_card, text="Aguardando texto…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self.status_lbl.pack(anchor="w", pady=(4, 0))
        self.wav_info_lbl = tk.Label(status_card, text="", font=("Consolas", 8), bg=CARD, fg=GREEN)
        self.wav_info_lbl.pack(anchor="w", pady=(2, 0))

    def _section_label(self, parent, row, text):
        tk.Label(parent, text=text, font=FONT_BOLD, bg=DARK, fg=MUTED).grid(row=row, column=0, sticky="w", pady=(12, 4))

    def _card_frame(self, parent, row):
        card = tk.Frame(parent, bg=CARD, padx=14, pady=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        return card

    def _make_voice_card(self, parent, voice, row_v, col):
        is_selected = self.voice_var.get() == voice["id"]
        frame = tk.Frame(parent, bg=TEAL if is_selected else "#2a2a35", padx=1, pady=1)
        frame.grid(row=row_v, column=col, sticky="ew", padx=(0,4) if col==0 else (4,0), pady=3)
        inner = tk.Frame(frame, bg=CARD, padx=10, pady=8, cursor="hand2")
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=voice["label"], font=FONT_BOLD, bg=CARD, fg=TEAL if is_selected else TEXT).pack(anchor="w")
        tk.Label(inner, text=voice["desc"], font=FONT_SMALL, bg=CARD, fg=MUTED).pack(anchor="w")
        rb = tk.Radiobutton(inner, variable=self.voice_var, value=voice["id"], bg=CARD, activebackground=CARD, selectcolor="#111116", relief="flat", bd=0, cursor="hand2", command=self._refresh_voice_cards)
        rb.pack(anchor="e")
        for w in [frame, inner]:
            w.bind("<Button-1>", lambda e, vid=voice["id"]: self._select_voice(vid))
        self._voice_btns[voice["id"]] = (frame, inner)

    def _select_voice(self, voice_id):
        self.voice_var.set(voice_id)
        self._refresh_voice_cards()

    def _refresh_voice_cards(self):
        selected = self.voice_var.get()
        for vid, (frame, inner) in self._voice_btns.items():
            is_sel = vid == selected
            try:
                frame.config(bg=TEAL if is_sel else "#2a2a35")
                children = inner.winfo_children()
                if children:
                    children[0].config(fg=TEAL if is_sel else TEXT)
            except Exception:
                pass

    def _update_char_count(self, *_):
        n = len(self.text_input.get("1.0", "end").strip())
        self.char_count_lbl.config(text=f"{n} caracteres", fg=RED if n > 5000 else WARN if n > 2000 else MUTED)

    def _set_text(self, text):
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", text)
        self._update_char_count()

    def _set_status(self, msg, color=None, progress=None):
        self.after(0, lambda: self.status_lbl.config(text=msg, fg=color or TEXT))
        if progress is not None:
            self.after(0, lambda: self.progress.config(value=progress))

    def _clear(self):
        self.text_input.delete("1.0", "end")
        self._update_char_count()
        self._generated_wav = None
        self.download_btn.config(state="disabled")
        self.use_btn.config(state="disabled")
        self.progress.config(value=0)
        self.status_lbl.config(text="Aguardando texto…", fg=MUTED)
        self.wav_info_lbl.config(text="")

    def _start_tts(self):
        if self._running: return
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            messagebox.showerror("Texto vazio", "Digite ou cole um texto antes de gerar.")
            return
        if not _FFMPEG_OK:
            messagebox.showerror("ffmpeg não encontrado", _ffmpeg_install_hint())
            return
        self._running = True
        self.gen_btn.config(state="disabled", text="⏳ Gerando…", bg=MUTED)
        self.download_btn.config(state="disabled")
        self.use_btn.config(state="disabled")
        self._set_status("🔊 Iniciando síntese de voz…", TEXT, 10)
        voice_id = self.voice_var.get()
        volume   = self.volume_var.get()
        out_path = os.path.join(tempfile.gettempdir(), f"audiofix_tts_{int(time.time())}.wav")

        def worker():
            try:
                self._set_status("📦 Verificando gTTS…", TEXT, 20)
                path = text_to_wav(text=text, voice_id=voice_id, output_wav=out_path, volume_factor=volume, log_cb=lambda m: self._set_status(m))
                self._generated_wav = path
                size_kb = os.path.getsize(path) / 1024
                duration_s = size_kb * 1024 / (44100 * 2 * 2)
                self.after(0, lambda: self.download_btn.config(state="normal"))
                self.after(0, lambda: self.use_btn.config(state="normal"))
                self.after(0, lambda: self.wav_info_lbl.config(text=f"📄 {os.path.basename(path)}  ({size_kb:.0f} KB  ~{duration_s:.1f}s)"))
                self._set_status("✅ WAV pronto!", GREEN, 100)
            except Exception as e:
                err_msg = str(e)
                self._set_status(f"❌ {err_msg}", RED, 0)
                self.after(0, lambda: messagebox.showerror("Erro TTS", err_msg))
            finally:
                self._running = False
                self.after(0, lambda: self.gen_btn.config(state="normal", text="🔊  Gerar Fala", bg=TEAL))

        threading.Thread(target=worker, daemon=True).start()

    def _download_wav(self):
        if not self._generated_wav or not os.path.isfile(self._generated_wav):
            messagebox.showwarning("WAV", "Nenhum WAV disponível.")
            return
        dest = filedialog.asksaveasfilename(title="Salvar WAV", defaultextension=".wav", initialfile=f"tts_{int(time.time())}.wav", filetypes=[("WAV Audio","*.wav"),("Todos","*.*")])
        if not dest: return
        import shutil
        shutil.copy2(self._generated_wav, dest)
        messagebox.showinfo("Download concluído!", f"WAV salvo em:\n{dest}")

    def _use_wav(self):
        if self._generated_wav and os.path.isfile(self._generated_wav):
            if self.on_wav_ready:
                self.on_wav_ready(self._generated_wav)
            messagebox.showinfo("Copy White atualizado!", f"WAV definido como Copy White:\n{self._generated_wav}")
            self.destroy()
        else:
            messagebox.showwarning("WAV", "Nenhum WAV disponível.")


# ─── Janela Transcrição ───────────────────────────────────────────────────────

class TranscriptionWindow(tk.Toplevel):
    def __init__(self, parent, video_path=None):
        super().__init__(parent)
        self.title("AudioFix Pro — Transcrição de Áudio")
        self.geometry("860x820")
        self.minsize(720, 720)
        self.configure(bg=DARK)
        self.resizable(True, True)
        self.transient(parent)
        self.lift()
        self.focus_force()
        self.video_path = tk.StringVar(value=video_path or "")
        self.model_size = tk.StringVar(value="base")
        self.language   = tk.StringVar(value="")
        self.merge_secs = tk.DoubleVar(value=30.0)
        self._segments  = []
        self._running   = False
        self._whisper_hint = None
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text="🎙  Transcrição de Áudio", font=("Segoe UI", 14, "bold"), bg=PANEL, fg=TEXT).pack(side="left", padx=20)
        tk.Label(hdr, text="powered by Whisper · estilo YouTube", font=FONT_SMALL, bg=PANEL, fg=MUTED).pack(side="left")
        tk.Button(hdr, text="✕", font=FONT_SMALL, bg=CARD, fg=MUTED, relief="flat", padx=10, pady=4, cursor="hand2", command=self.destroy).pack(side="right", padx=12)

        footer = tk.Frame(self, bg=DARK, pady=12, padx=20)
        footer.pack(fill="x", side="bottom")
        self.trans_btn = tk.Button(footer, text="🎙  TRANSCREVER", font=("Segoe UI", 11, "bold"), bg=TEAL, fg="white", activebackground="#0f9488", activeforeground="white", relief="flat", padx=28, pady=10, cursor="hand2", command=self._start_transcription)
        self.trans_btn.pack(side="right")
        for label, fmt, color in [("💾  SRT","srt",TEAL),("💾  VTT","vtt",CYAN),("💾  TXT","txt",GREEN)]:
            tk.Button(footer, text=label, font=FONT_LABEL, bg=CARD, fg=color, relief="flat", padx=14, pady=10, cursor="hand2", command=lambda f=fmt: self._export(f)).pack(side="right", padx=(0,6))
        tk.Button(footer, text="📋  Copiar tudo", font=FONT_LABEL, bg=CARD, fg=MUTED, relief="flat", padx=12, pady=10, cursor="hand2", command=self._copy_all).pack(side="left")

        body = tk.Frame(self, bg=DARK, padx=20, pady=14)
        body.pack(fill="both", expand=True, side="top")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        file_row = tk.Frame(body, bg=DARK)
        file_row.grid(row=0, column=0, sticky="ew", pady=(0,8))
        tk.Label(file_row, text="🎬  Vídeo/Áudio:", font=FONT_BOLD, bg=DARK, fg=MUTED, width=14, anchor="w").pack(side="left")
        tk.Entry(file_row, textvariable=self.video_path, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(file_row, text="Escolher", font=FONT_LABEL, bg=ACCENT, fg="white", relief="flat", padx=10, pady=2, cursor="hand2", command=self._browse).pack(side="right")

        opts_card = tk.Frame(body, bg=CARD, padx=14, pady=10)
        opts_card.grid(row=1, column=0, sticky="ew", pady=(0,8))
        opts_card.columnconfigure(1, weight=1)
        opts_card.columnconfigure(3, weight=1)
        tk.Label(opts_card, text="Modelo Whisper:", font=FONT_BOLD, bg=CARD, fg=MUTED).grid(row=0, column=0, sticky="w", padx=(0,8))
        ttk.Combobox(opts_card, textvariable=self.model_size, values=["tiny","base","small","medium","large"], state="readonly", width=10, font=FONT_LABEL).grid(row=0, column=1, sticky="w")
        tk.Label(opts_card, text="Idioma (opcional):", font=FONT_BOLD, bg=CARD, fg=MUTED).grid(row=0, column=2, sticky="w", padx=(20,8))
        tk.Entry(opts_card, textvariable=self.language, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1, width=8).grid(row=0, column=3, sticky="w")
        tk.Label(opts_card, text="(pt, en, es… vazio = auto)", font=FONT_SMALL, bg=CARD, fg=MUTED).grid(row=0, column=4, sticky="w", padx=(6,0))
        tk.Label(opts_card, text="Capítulos a cada:", font=FONT_BOLD, bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", pady=(6,0))
        self.merge_lbl = tk.Label(opts_card, text="30s", font=FONT_BOLD, bg=CARD, fg=TEAL, width=5)
        self.merge_lbl.grid(row=1, column=3, sticky="w", pady=(6,0))
        ttk.Scale(opts_card, from_=10, to=120, variable=self.merge_secs, orient="horizontal", command=lambda v: self.merge_lbl.config(text=f"{int(float(v))}s")).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6,0), padx=(0,6))
        self._refresh_whisper_badge(opts_card)

        prog_card = tk.Frame(body, bg=CARD, padx=14, pady=8)
        prog_card.grid(row=2, column=0, sticky="ew", pady=(0,8))
        self.trans_progress = ttk.Progressbar(prog_card, mode="determinate", maximum=100, length=200)
        self.trans_progress.pack(fill="x")
        self.trans_status = tk.Label(prog_card, text="Aguardando…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self.trans_status.pack(anchor="w", pady=(4,0))

        nb_outer = tk.Frame(body, bg=DARK)
        nb_outer.grid(row=3, column=0, sticky="nsew", pady=(0,4))
        nb_outer.columnconfigure(0, weight=1)
        nb_outer.rowconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure("Trans.TNotebook", background=DARK, borderwidth=0)
        style.configure("Trans.TNotebook.Tab", background=CARD, foreground=MUTED, padding=[14,6], font=FONT_BOLD)
        style.map("Trans.TNotebook.Tab", background=[("selected",PANEL)], foreground=[("selected",TEXT)])
        self.nb = ttk.Notebook(nb_outer, style="Trans.TNotebook")
        self.nb.grid(row=0, column=0, sticky="nsew")

        def _text_tab(label):
            tab = tk.Frame(self.nb, bg=PANEL)
            self.nb.add(tab, text=label)
            tab.rowconfigure(0, weight=1)
            tab.columnconfigure(0, weight=1)
            t = tk.Text(tab, font=("Consolas",10), bg="#111116", fg="#c8c8e0", relief="flat", state="disabled", wrap="word", padx=10, pady=8, selectbackground=ACCENT)
            t.grid(row=0, column=0, sticky="nsew")
            sb = ttk.Scrollbar(tab, command=t.yview)
            sb.grid(row=0, column=1, sticky="ns")
            t.config(yscrollcommand=sb.set)
            return t

        self.segments_text = _text_tab("▶  Segmentos")
        self.segments_text.tag_configure("ts", foreground=TEAL, font=("Consolas",10,"bold"))
        self.segments_text.tag_configure("text", foreground=TEXT, font=("Consolas",10))
        self.srt_text      = _text_tab("📄  SRT")
        self.chapters_text = _text_tab("📑  Capítulos")
        self.plain_text    = _text_tab("📝  Texto puro")
        tk.Label(self, text="💡 modelo 'base' é rápido e preciso para a maioria dos casos", font=FONT_SMALL, bg=PANEL, fg=MUTED, pady=6).pack(fill="x", side="bottom")

    def _refresh_whisper_badge(self, parent_card=None):
        backend, _ = check_whisper_available()
        text  = (f"✅ Backend disponível: {backend}" if backend else "⚠️  Whisper não instalado — clique em TRANSCREVER para instalar")
        color = GREEN if backend else WARN
        if self._whisper_hint is not None:
            try:
                if self._whisper_hint.winfo_exists():
                    self._whisper_hint.config(text=text, fg=color); return
            except Exception: pass
        if parent_card is not None:
            self._whisper_hint = tk.Label(parent_card, text=text, font=FONT_SMALL, bg=CARD, fg=color)
            self._whisper_hint.grid(row=2, column=0, columnspan=5, sticky="w", pady=(8,0))

    def _browse(self):
        path = filedialog.askopenfilename(title="Selecionar vídeo ou áudio", filetypes=[("Vídeos e Áudios","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v *.mp3 *.wav *.m4a *.ogg"),("Todos","*.*")])
        if path: self.video_path.set(path)

    def _log_status(self, msg, color=None):
        self.after(0, lambda: self.trans_status.config(text=msg, fg=color or TEXT))

    def _set_progress(self, pct):
        self.after(0, lambda: self.trans_progress.config(value=pct))

    def _start_transcription(self):
        if self._running: return
        path = self.video_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Erro", "Selecione um arquivo válido.")
            return
        backend, _ = check_whisper_available()
        if not backend:
            ok = _WhisperInstallDialog(self)
            self.wait_window(ok)
            if ok.result != "installed": return
            importlib.invalidate_caches()
            backend, _ = check_whisper_available()
            if not backend:
                self._log_status("❌ Reinicie o app.", RED); return
            self._refresh_whisper_badge()
        is_video = path.lower().endswith((".mp4",".mkv",".avi",".mov",".webm",".flv",".ts",".m4v"))
        if is_video and not _FFMPEG_OK:
            messagebox.showerror("ffmpeg não encontrado", _ffmpeg_install_hint()); return
        self._running = True
        self.trans_btn.config(state="disabled", text="⏳ Transcrevendo…", bg=MUTED)
        self.trans_progress.config(value=0)
        self._clear_tabs()
        model = self.model_size.get()
        lang  = self.language.get().strip() or None

        def worker():
            try:
                wav_path = path
                tmp_dir  = None
                if is_video:
                    tmp_dir  = tempfile.mkdtemp(prefix="audiofix_trans_")
                    wav_path = os.path.join(tmp_dir, "audio_16k.wav")
                    self._log_status("▶ Extraindo áudio…", TEXT)
                    self._set_progress(5)
                    extract_audio_for_transcription(path, wav_path, self._log_status)
                    self._set_progress(15)
                segments = transcribe_audio(wav_path, model_size=model, language=lang, progress_cb=self._set_progress, log_cb=self._log_status)
                self._segments = segments
                if tmp_dir:
                    import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)
                self.after(0, lambda: self._populate_tabs(segments))
                self.after(0, lambda: self.trans_status.config(text=f"✅ {len(segments)} segmento(s).", fg=GREEN))
                self.after(0, lambda: self.trans_progress.config(value=100))
            except Exception as e:
                import traceback
                err_msg = str(e)
                self.after(0, lambda: self.trans_status.config(text=f"❌ {err_msg}", fg=RED))
                self.after(0, lambda: messagebox.showerror("Erro", f"{err_msg}\n\n{traceback.format_exc()[-400:]}"))
            finally:
                self._running = False
                self.after(0, lambda: self.trans_btn.config(state="normal", text="🎙  TRANSCREVER", bg=TEAL))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_tabs(self):
        for w in [self.segments_text, self.srt_text, self.chapters_text, self.plain_text]:
            w.config(state="normal"); w.delete("1.0","end"); w.config(state="disabled")

    def _populate_tabs(self, segments):
        self.segments_text.config(state="normal")
        self.segments_text.delete("1.0","end")
        for seg in segments:
            ts = format_timestamp_yt(seg["start"])
            self.segments_text.insert("end", f"[{ts}]  ", "ts")
            self.segments_text.insert("end", seg["text"]+"\n", "text")
        self.segments_text.config(state="disabled")
        for widget, content in [
            (self.srt_text, segments_to_srt(segments)),
            (self.chapters_text, "── Cole na descrição do YouTube ──\n\n"+segments_to_youtube_chapters(segments, self.merge_secs.get())),
            (self.plain_text, segments_to_txt(segments)),
        ]:
            widget.config(state="normal"); widget.delete("1.0","end"); widget.insert("1.0",content); widget.config(state="disabled")
        self.nb.select(0)

    def _export(self, fmt):
        if not self._segments:
            messagebox.showwarning("Exportar","Execute a transcrição primeiro."); return
        exts = {"srt":("SRT","*.srt"),"vtt":("WebVTT","*.vtt"),"txt":("Texto","*.txt")}
        label, ext = exts[fmt]
        path = filedialog.asksaveasfilename(title=f"Salvar {label}", defaultextension=f".{fmt}", filetypes=[(label,ext),("Todos","*.*")])
        if not path: return
        content = {"srt":segments_to_srt,"vtt":segments_to_vtt,"txt":segments_to_txt}[fmt](self._segments)
        with open(path,"w",encoding="utf-8") as f: f.write(content)
        messagebox.showinfo("Exportado!", f"Salvo em:\n{path}")

    def _copy_all(self):
        if not self._segments: return
        self.clipboard_clear()
        self.clipboard_append(segments_to_txt(self._segments))
        messagebox.showinfo("Copiado!","Texto copiado.")


# ─── Diálogo instalação Whisper ───────────────────────────────────────────────

class _WhisperInstallDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Instalar Whisper")
        self.geometry("500x320")
        self.resizable(False, False)
        self.configure(bg=DARK)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._build()

    def _build(self):
        tk.Label(self, text="🎙  Transcrição de Áudio", font=("Segoe UI",14,"bold"), bg=DARK, fg=TEXT, pady=16).pack()
        card = tk.Frame(self, bg=CARD, padx=20, pady=16)
        card.pack(fill="both", expand=True, padx=20, pady=(0,10))
        tk.Label(card, text="O backend Whisper não está instalado.", font=("Segoe UI",10), bg=CARD, fg=WARN, wraplength=420).pack(anchor="w")
        tk.Label(card, text="\nDeseja instalar o faster-whisper agora?\n(~50 MB · necessário apenas uma vez)", font=("Segoe UI",10), bg=CARD, fg=TEXT, wraplength=420, justify="left").pack(anchor="w")
        tk.Label(card, text="pip install faster-whisper", font=("Consolas",9), bg=CARD, fg=MUTED).pack(anchor="w", pady=(8,0))
        self._status = tk.Label(card, text="", font=("Segoe UI",9), bg=CARD, fg=MUTED)
        self._status.pack(anchor="w", pady=(6,0))
        self._progress = ttk.Progressbar(card, mode="indeterminate", length=300)
        self._progress.pack(fill="x", pady=(6,0))
        btn_frame = tk.Frame(self, bg=DARK, pady=10)
        btn_frame.pack()
        self._install_btn = tk.Button(btn_frame, text="⬇  Instalar faster-whisper", font=("Segoe UI",10,"bold"), bg=TEAL, fg="white", relief="flat", padx=18, pady=8, cursor="hand2", command=self._do_install)
        self._install_btn.pack(side="left", padx=(0,8))
        tk.Button(btn_frame, text="Agora não", font=FONT_LABEL, bg=CARD, fg=MUTED, relief="flat", padx=14, pady=8, cursor="hand2", command=self._skip).pack(side="left")

    def _do_install(self):
        self._install_btn.config(state="disabled", text="⏳ Instalando…")
        self._progress.start(12)
        self._status.config(text="Instalando faster-whisper…", fg=TEXT)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        success = install_whisper_now()
        self.after(0, lambda: self._finish(success))

    def _finish(self, success):
        self._progress.stop()
        if success:
            self._status.config(text="✅ Instalado!", fg=GREEN)
            self.result = "installed"
            self.after(1200, self.destroy)
        else:
            self._status.config(text="❌ Falha. Tente: pip install faster-whisper", fg=RED)
            self._install_btn.config(state="normal", text="⬇  Tentar novamente")

    def _skip(self):
        self.result = "skip"
        self.destroy()


# ─── Janela Preview ───────────────────────────────────────────────────────────

class PreviewWindow(tk.Toplevel):
    def __init__(self, parent, original_path, processed_path, variants=None):
        super().__init__(parent)
        self.title("AudioFix Pro — Preview")
        self.geometry("660x560")
        self.minsize(560, 480)
        self.configure(bg=DARK)
        self.resizable(True, True)
        self.original_path  = original_path
        self.processed_path = processed_path
        self.variants       = variants or []
        self.transient(parent)
        self.lift()
        self.focus_force()
        self._build()
        self._load_info()

    def _build(self):
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎬  Preview & Informações", font=("Segoe UI",14,"bold"), bg=PANEL, fg=TEXT).pack(side="left", padx=20)
        tk.Button(hdr, text="✕  Fechar", font=FONT_SMALL, bg=CARD, fg=MUTED, relief="flat", padx=10, pady=4, cursor="hand2", command=self.destroy).pack(side="right", padx=12)

        body = tk.Frame(self, bg=DARK, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        left = tk.Frame(body, bg=DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        tk.Label(left, text="📁  Vídeo Original", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        self.orig_card = tk.Frame(left, bg=CARD, padx=14, pady=12)
        self.orig_card.pack(fill="both", expand=True)
        self.orig_info = tk.Text(self.orig_card, height=10, font=FONT_MONO, bg=CARD, fg=TEXT, relief="flat", state="disabled", wrap="word", bd=0)
        self.orig_info.pack(fill="both", expand=True)
        tk.Button(left, text="▶  Abrir Original", font=FONT_LABEL, bg="#2a2a35", fg=TEXT, relief="flat", padx=12, pady=6, cursor="hand2", command=lambda: open_video_player(self.original_path)).pack(fill="x", pady=(6,0))

        right = tk.Frame(body, bg=DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        tk.Label(right, text="✅  Vídeo Processado", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        self.proc_card = tk.Frame(right, bg=CARD, padx=14, pady=12)
        self.proc_card.pack(fill="both", expand=True)
        self.proc_info = tk.Text(self.proc_card, height=10, font=FONT_MONO, bg=CARD, fg=TEXT, relief="flat", state="disabled", wrap="word", bd=0)
        self.proc_info.pack(fill="both", expand=True)
        tk.Button(right, text="▶  Abrir Processado", font=FONT_LABEL, bg=ACCENT, fg="white", relief="flat", padx=12, pady=6, cursor="hand2", command=lambda: open_video_player(self.processed_path)).pack(fill="x", pady=(6,0))

        body.rowconfigure(0, weight=1)
        cmp_outer = tk.Frame(body, bg=DARK)
        cmp_outer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14,0))
        tk.Label(cmp_outer, text="⚡  Comparação", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        cmp_card = tk.Frame(cmp_outer, bg=CARD, padx=14, pady=10)
        cmp_card.pack(fill="x")
        btn_row = tk.Frame(cmp_card, bg=CARD)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="▶▶  Abrir Ambos", font=FONT_BOLD, bg="#1a3a2a", fg=GREEN, relief="flat", padx=16, pady=8, cursor="hand2", command=self._open_both).pack(side="left")
        if self.variants:
            tk.Button(btn_row, text=f"🎲  {len(self.variants)} variação(ões)", font=FONT_LABEL, bg="#1a1a2e", fg=CYAN, relief="flat", padx=14, pady=8, cursor="hand2", command=self._show_variants).pack(side="left", padx=(8,0))
        self.diff_label = tk.Label(cmp_card, text="", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self.diff_label.pack(anchor="w", pady=(6,0))

    def _load_info(self):
        def worker():
            oi = get_video_info(self.original_path)
            pi = get_video_info(self.processed_path)
            self.after(0, lambda: self._fill(self.orig_info, oi, self.original_path, TEXT))
            self.after(0, lambda: self._fill(self.proc_info, pi, self.processed_path, GREEN))
            self.after(0, lambda: self._fill_diff(oi, pi))
        threading.Thread(target=worker, daemon=True).start()

    def _fill(self, widget, info, path, color):
        def fmt_dur(s):
            if not s: return "?"
            m, sec = divmod(int(s),60); h, m = divmod(m,60)
            return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
        rows = [
            ("📄","Arquivo:  ", os.path.basename(path)),
            ("⏱ ","Duração:  ", fmt_dur(info.get("duration",0))),
            ("💾","Tamanho:  ", f"{info.get('size_mb',0):.2f} MB"),
            ("📡","Bitrate:  ", f"{info.get('bitrate','?')} kbps"),
            ("🖥 ","Resolução:", f"{info.get('width','?')}×{info.get('height','?')}"),
            ("🎞 ","Vídeo:    ", f"{info.get('video_codec','?')} @ {info.get('fps','?')} fps"),
            ("🔊","Áudio:    ", f"{info.get('audio_codec','?')}"),
            ("🎚 ","Taxa:     ", f"{info.get('sample_rate','?')} Hz"),
            ("🎛 ","Canais:   ", f"{info.get('channels','?')} ({info.get('channel_layout','?')})"),
        ]
        widget.config(state="normal"); widget.delete("1.0","end")
        widget.tag_configure("icon", foreground=MUTED, font=FONT_MONO)
        widget.tag_configure("key",  foreground=MUTED, font=("Consolas",9))
        widget.tag_configure("val",  foreground=color, font=("Consolas",9,"bold"))
        widget.tag_configure("name", foreground=ACC2,  font=("Consolas",8))
        for icon, key, val in rows:
            widget.insert("end", icon, "icon"); widget.insert("end", key, "key")
            widget.insert("end", val+"\n", "name" if "Arquivo" in key else "val")
        widget.config(state="disabled")

    def _fill_diff(self, orig, proc):
        if not orig or not proc: return
        om, pm = orig.get("size_mb",0), proc.get("size_mb",0)
        if om > 0:
            pct  = ((pm-om)/om)*100
            sign = "+" if pct >= 0 else ""
            self.diff_label.config(text=f"Diferença de tamanho: {sign}{pct:.1f}%  ({om:.2f} MB → {pm:.2f} MB)", fg=WARN if abs(pct)>5 else GREEN)

    def _open_both(self):
        open_video_player(self.original_path)
        self.after(800, lambda: open_video_player(self.processed_path))

    def _show_variants(self):
        win = tk.Toplevel(self)
        win.title("Variações geradas")
        win.geometry("480x320")
        win.configure(bg=DARK)
        win.transient(self)
        win.lift()
        tk.Label(win, text=f"🎲  {len(self.variants)} variação(ões)", font=FONT_BOLD, bg=DARK, fg=TEXT, pady=14).pack()
        frame = tk.Frame(win, bg=DARK, padx=16)
        frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(frame, bg=DARK, highlightthickness=0)
        sb = ttk.Scrollbar(frame, command=canvas.yview)
        canvas.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=DARK)
        cwin = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
        for i, path in enumerate(self.variants, 1):
            row = tk.Frame(inner, bg=CARD, padx=10, pady=6)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"Var {i:02d}: {os.path.basename(path)}", font=FONT_MONO, bg=CARD, fg=ACC2).pack(side="left")
            p = path
            tk.Button(row, text="▶ Abrir", font=FONT_SMALL, bg=ACCENT, fg="white", relief="flat", padx=8, pady=2, cursor="hand2", command=lambda p=p: open_video_player(p)).pack(side="right")
        tk.Button(win, text="Fechar", font=FONT_LABEL, bg=CARD, fg=MUTED, relief="flat", padx=14, pady=6, cursor="hand2", command=win.destroy).pack(pady=10)


# ─── Widget de ruído ──────────────────────────────────────────────────────────

class NoiseControl(tk.Frame):
    def __init__(self, parent, name, color, default_amp=0.0, **kwargs):
        super().__init__(parent, bg=CARD, padx=10, pady=8, **kwargs)
        self.name  = name
        self.color = color
        self._enabled = tk.BooleanVar(value=default_amp > 0)
        self._amp     = tk.DoubleVar(value=default_amp if default_amp > 0 else 0.003)

        top = tk.Frame(self, bg=CARD)
        top.pack(fill="x")
        tk.Checkbutton(top, variable=self._enabled, bg=CARD, activebackground=CARD, fg=color, selectcolor="#111116", relief="flat", bd=0, cursor="hand2", command=self._toggle).pack(side="left")
        self._name_lbl = tk.Label(top, text=f"Ruído {name}", font=FONT_BOLD, bg=CARD, fg=color)
        self._name_lbl.pack(side="left")
        tk.Label(top, text=f"  ·  {NOISE_DESCRIPTIONS.get(name,'')}", font=FONT_SMALL, bg=CARD, fg=MUTED).pack(side="left")
        self._amp_lbl = tk.Label(top, text=f"{self._amp.get():.4f}", font=FONT_BOLD, bg=CARD, fg=color, width=7)
        self._amp_lbl.pack(side="right")
        self._slider = ttk.Scale(self, from_=0.0001, to=0.02, variable=self._amp, orient="horizontal", command=self._on_slide)
        self._slider.pack(fill="x", pady=(4,0))
        self._toggle()

    def _toggle(self):
        state = "normal" if self._enabled.get() else "disabled"
        self._slider.config(state=state)
        fg = self.color if self._enabled.get() else MUTED
        self._name_lbl.config(fg=fg)
        self._amp_lbl.config(fg=fg)

    def _on_slide(self, *_):
        self._amp_lbl.config(text=f"{self._amp.get():.4f}")

    @property
    def amplitude(self):
        return self._amp.get() if self._enabled.get() else 0.0

    @property
    def enabled(self):
        return self._enabled.get()


# ─── Widget seletor de modo ───────────────────────────────────────────────────

class ModeSelector(tk.Frame):
    def __init__(self, parent, on_change=None, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._mode = tk.StringVar(value="audio")
        self._on_change = on_change
        self._build()

    def _build(self):
        tk.Label(self, text="⚙️  Modo de processamento",
                 font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0, 6))

        container = tk.Frame(self, bg=DARK)
        container.pack(fill="x")
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        # ── Card: Manipular Áudio ──────────────────────────────────────────
        self._btn_audio_frame = tk.Frame(container, bg=ACCENT, padx=2, pady=2)
        self._btn_audio_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._btn_audio_inner = tk.Frame(self._btn_audio_frame, bg="#1a1830", padx=14, pady=12, cursor="hand2")
        self._btn_audio_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_audio_inner, text="🎛️  Manipular Áudio",
                 font=("Segoe UI", 11, "bold"), bg="#1a1830", fg=ACC2).pack(anchor="w")
        tk.Label(self._btn_audio_inner,
                 text="Inversão de fase · Ruídos coloridos\nCopy White · TTS · DCB · MP3 processado",
                 font=FONT_SMALL, bg="#1a1830", fg=MUTED, justify="left").pack(anchor="w", pady=(4, 0))
        for w in [self._btn_audio_frame, self._btn_audio_inner]:
            w.bind("<Button-1>", lambda e: self._select("audio"))
        # bind clicks on child labels too
        for child in self._btn_audio_inner.winfo_children():
            child.bind("<Button-1>", lambda e: self._select("audio"))

        # ── Card: Áudio Original ───────────────────────────────────────────
        self._btn_orig_frame = tk.Frame(container, bg=MUTED, padx=2, pady=2)
        self._btn_orig_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._btn_orig_inner = tk.Frame(self._btn_orig_frame, bg=CARD, padx=14, pady=12, cursor="hand2")
        self._btn_orig_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_orig_inner, text="🎬  Áudio Original",
                 font=("Segoe UI", 11, "bold"), bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self._btn_orig_inner,
                 text="Sem processamento de áudio\nApenas variações de metadados",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, justify="left").pack(anchor="w", pady=(4, 0))
        for w in [self._btn_orig_frame, self._btn_orig_inner]:
            w.bind("<Button-1>", lambda e: self._select("original"))
        for child in self._btn_orig_inner.winfo_children():
            child.bind("<Button-1>", lambda e: self._select("original"))

    def _select(self, mode):
        self._mode.set(mode)
        self._on_select()

    def _on_select(self):
        mode = self._mode.get()
        if mode == "audio":
            self._btn_audio_frame.config(bg=ACCENT)
            self._btn_audio_inner.config(bg="#1a1830")
            for w in self._btn_audio_inner.winfo_children():
                try: w.config(bg="#1a1830")
                except: pass
            self._btn_orig_frame.config(bg=MUTED)
            self._btn_orig_inner.config(bg=CARD)
            for w in self._btn_orig_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
        else:
            self._btn_orig_frame.config(bg=GREEN)
            self._btn_orig_inner.config(bg="#0d1a12")
            for w in self._btn_orig_inner.winfo_children():
                try: w.config(bg="#0d1a12")
                except: pass
            self._btn_audio_frame.config(bg=MUTED)
            self._btn_audio_inner.config(bg=CARD)
            for w in self._btn_audio_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
        if self._on_change:
            self._on_change(mode)

    @property
    def mode(self):
        return self._mode.get()


# ─── Widget seletor nível de variação ─────────────────────────────────────────

class VariationLevelSelector(tk.Frame):
    LEVELS = list(VARIATION_LEVELS.keys())

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=CARD, **kwargs)
        self._level = tk.StringVar(value="Normal")
        self._btns  = {}
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=CARD)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text="📊  Nível de variação dos metadados:",
                 font=FONT_BOLD, bg=CARD, fg=MUTED).pack(side="left")
        self._desc_lbl = tk.Label(hdr, text="", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self._desc_lbl.pack(side="right")

        btn_row = tk.Frame(self, bg=CARD)
        btn_row.pack(fill="x")
        for i in range(4):
            btn_row.columnconfigure(i, weight=1)

        for idx, level_name in enumerate(self.LEVELS):
            cfg = VARIATION_LEVELS[level_name]
            col = cfg["color"]
            btn_outer = tk.Frame(btn_row, bg=MUTED, padx=1, pady=1)
            btn_outer.grid(row=0, column=idx, sticky="ew",
                           padx=(0, 3) if idx < 3 else 0)
            btn_inner = tk.Frame(btn_outer, bg=CARD, padx=8, pady=8, cursor="hand2")
            btn_inner.pack(fill="both", expand=True)
            name_lbl = tk.Label(btn_inner, text=cfg["label"],
                                font=FONT_BOLD, bg=CARD, fg=TEXT)
            name_lbl.pack(anchor="center")
            line = tk.Frame(btn_inner, bg=col, height=3)
            line.pack(fill="x", pady=(4, 0))
            rb = tk.Radiobutton(btn_inner, variable=self._level, value=level_name,
                                bg=CARD, activebackground=CARD,
                                selectcolor="#111116", relief="flat", bd=0,
                                cursor="hand2", command=self._refresh)
            rb.pack(anchor="e")
            for w in [btn_outer, btn_inner, name_lbl, line]:
                w.bind("<Button-1>", lambda e, lv=level_name: self._select(lv))
            self._btns[level_name] = (btn_outer, btn_inner, name_lbl, line, rb)

        ex_card = tk.Frame(self, bg="#111116", padx=10, pady=8)
        ex_card.pack(fill="x", pady=(8, 0))
        self._ex_title = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=ACC2)
        self._ex_title.pack(anchor="w")
        self._ex_date  = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=MUTED)
        self._ex_date.pack(anchor="w")
        self._ex_track = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=MUTED)
        self._ex_track.pack(anchor="w")

        self._refresh()

    def _select(self, level_name):
        self._level.set(level_name)
        self._refresh()

    def _refresh(self):
        selected = self._level.get()
        cfg = VARIATION_LEVELS[selected]
        for lv_name, (outer, inner, name_lbl, line, rb) in self._btns.items():
            is_sel = lv_name == selected
            lv_cfg = VARIATION_LEVELS[lv_name]
            try:
                if is_sel:
                    outer.config(bg=lv_cfg["color"])
                    inner.config(bg="#181818")
                    name_lbl.config(bg="#181818", fg=lv_cfg["color"])
                    line.config(bg=lv_cfg["color"])
                    rb.config(bg="#181818", selectcolor="#0d0d0d", activebackground="#181818")
                else:
                    outer.config(bg=MUTED)
                    inner.config(bg=CARD)
                    name_lbl.config(bg=CARD, fg=TEXT)
                    line.config(bg=lv_cfg["color"])
                    rb.config(bg=CARD, selectcolor="#111116", activebackground=CARD)
            except Exception:
                pass
        self._desc_lbl.config(text=cfg["desc"], fg=cfg["color"])
        ex_meta = generate_metadata_variants(1, selected)[0]
        self._ex_title.config(text=f"  title:  {ex_meta['title']}")
        self._ex_date.config(text=f"  date:   {ex_meta['date']}")
        self._ex_track.config(text=f"  track:  {ex_meta['track']}")

    @property
    def level(self):
        return self._level.get()


# ─── App principal ────────────────────────────────────────────────────────────

class AudioFixApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AudioFix Pro")
        self.geometry("820x1180")
        self.minsize(720, 960)
        self.configure(bg=DARK)
        self.resizable(True, True)

        self.video_path  = tk.StringVar()
        self.output_path = tk.StringVar()
        self.n_variants  = tk.IntVar(value=0)
        self.running     = False

        self.cw_path     = tk.StringVar()
        self.cw_enabled  = tk.BooleanVar(value=False)
        self.cw_gain     = tk.DoubleVar(value=0.40)

        self.dcb_enabled   = tk.BooleanVar(value=False)
        self.dcb_threshold = tk.DoubleVar(value=0.50)
        self.dcb_ratio     = tk.DoubleVar(value=4.0)
        self.dcb_makeup    = tk.DoubleVar(value=1.80)

        self._last_original  = None
        self._last_processed = None
        self._last_variants  = []
        self._noise_controls: dict = {}
        self._dcb_widgets    = []
        self._audio_mode_widgets = []

        self._build_ui()
        if not _FFMPEG_OK:
            self.after(500, self._warn_ffmpeg)

    def _warn_ffmpeg(self):
        messagebox.showwarning("ffmpeg não encontrado", _ffmpeg_install_hint())

    def _build_ui(self):
        hdr = tk.Frame(self, bg=PANEL, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="AudioFix Pro", font=FONT_TITLE, bg=PANEL, fg=TEXT).pack()
        tk.Label(hdr, text="Inversão de fase · Ruídos coloridos · Copy White · TTS · DCB · Transcrição · MP3 estéreo",
                 font=FONT_STATUS, bg=PANEL, fg=MUTED).pack(pady=(2,0))

        dep_frame = tk.Frame(hdr, bg=PANEL)
        dep_frame.pack(pady=(6,0))
        gtts_ok = _is_importable("gtts")
        for text, color in [
            ("ffmpeg ✔" if _FFMPEG_OK else "ffmpeg ✖", GREEN if _FFMPEG_OK else RED),
            ("  |  ", MUTED),
            ("whisper ✔" if _WHISPER_OK else "whisper —", GREEN if _WHISPER_OK else MUTED),
            ("  |  ", MUTED),
            ("gTTS ✔" if gtts_ok else "gTTS —", GREEN if gtts_ok else MUTED),
            ("  |  ", MUTED),
            ("numpy ✔", GREEN), ("  |  ", MUTED), ("scipy ✔", GREEN),
        ]:
            tk.Label(dep_frame, text=text, font=FONT_SMALL, bg=PANEL, fg=color).pack(side="left")

        outer = tk.Frame(self, bg=DARK)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body_frame = tk.Frame(canvas, bg=DARK)
        body_win   = canvas.create_window((0,0), window=body_frame, anchor="nw")
        body_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        body = tk.Frame(body_frame, bg=DARK, padx=24, pady=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        row_idx = 0

        self._file_row(body, row_idx, "🎬  Vídeo de entrada", self.video_path, self._browse_input, "Nenhum vídeo selecionado…"); row_idx += 1
        self._file_row(body, row_idx, "💾  Arquivo de saída", self.output_path, self._browse_output, "Onde salvar o vídeo processado…"); row_idx += 1

        mode_outer = tk.Frame(body, bg=DARK, pady=5)
        mode_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0, 4)); row_idx += 1
        self.mode_selector = ModeSelector(mode_outer, on_change=self._on_mode_change)
        self.mode_selector.pack(fill="x")

        noise_outer = tk.Frame(body, bg=DARK, pady=5)
        noise_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(noise_outer, text="🎨  Mistura de ruídos coloridos", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,6))
        noise_grid = tk.Frame(noise_outer, bg=DARK)
        noise_grid.pack(fill="x")
        noise_grid.columnconfigure(0, weight=1)
        noise_grid.columnconfigure(1, weight=1)
        defaults = {"Rosa":0.003,"Branco":0.0,"Marrom":0.0,"Azul":0.0,"Violeta":0.0,"Cinza":0.0}
        for idx, name in enumerate(NOISE_GENERATORS.keys()):
            ctrl = NoiseControl(noise_grid, name=name, color=NOISE_COLORS[name], default_amp=defaults.get(name,0.0))
            ctrl.grid(row=idx//2, column=idx%2, sticky="ew", padx=(0,4) if idx%2==0 else (4,0), pady=2)
            self._noise_controls[name] = ctrl
        self._audio_mode_widgets.append(noise_outer)

        cw_outer = tk.Frame(body, bg=DARK, pady=5)
        cw_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        cw_hdr = tk.Frame(cw_outer, bg=DARK)
        cw_hdr.pack(fill="x")
        tk.Checkbutton(cw_hdr, variable=self.cw_enabled, bg=DARK, activebackground=DARK, fg=CYAN, selectcolor="#111116", relief="flat", bd=0, cursor="hand2", command=self._toggle_cw).pack(side="left")
        tk.Label(cw_hdr, text="📻  Copy White — sobreposição de áudio externo", font=FONT_BOLD, bg=DARK, fg=CYAN).pack(side="left")
        self.tts_open_btn = tk.Button(cw_hdr, text="🎤  Texto para Fala", font=("Segoe UI",9,"bold"), bg=TEAL, fg="white", activebackground="#0f9488", activeforeground="white", relief="flat", padx=12, pady=3, cursor="hand2", command=self._open_tts)
        self.tts_open_btn.pack(side="right", padx=(0,0))
        tk.Label(cw_hdr, text="← gera voz WAV", font=FONT_SMALL, bg=DARK, fg=TEAL).pack(side="right", padx=(0,8))
        self.cw_card = tk.Frame(cw_outer, bg=CARD, padx=14, pady=12)
        self.cw_card.pack(fill="x")
        self.tts_wav_badge = tk.Label(self.cw_card, text="", font=FONT_SMALL, bg="#0d1f1f", fg=TEAL, padx=8, pady=4)
        rec = tk.Frame(self.cw_card, bg="#1a2a2a", padx=10, pady=7)
        rec.pack(fill="x", pady=(0,8))
        for line in [("💡 Recomendação:","bold"),("  • Ganho: 0.30–0.50",""),("  • Ative o DCB para nivelar o volume","")]:
            tk.Label(rec, text=line[0], font=("Segoe UI",9,line[1]) if line[1] else FONT_SMALL, bg="#1a2a2a", fg=TEAL).pack(anchor="w")
        file_row_cw = tk.Frame(self.cw_card, bg=CARD)
        file_row_cw.pack(fill="x", pady=(0,8))
        tk.Label(file_row_cw, text="Áudio WAV:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_entry = tk.Entry(file_row_cw, textvariable=self.cw_path, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1, disabledbackground=INPUT_BG, disabledforeground="#888888")
        self.cw_entry.pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(file_row_cw, text="Escolher WAV", font=FONT_LABEL, bg=CYAN, fg=DARK, relief="flat", padx=10, pady=2, cursor="hand2", command=self._browse_cw).pack(side="right")
        gain_row = tk.Frame(self.cw_card, bg=CARD)
        gain_row.pack(fill="x")
        tk.Label(gain_row, text="Ganho mix:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_gain_lbl = tk.Label(gain_row, text=f"{self.cw_gain.get():.2f}", font=FONT_BOLD, bg=CARD, fg=CYAN, width=5)
        self.cw_gain_lbl.pack(side="right")
        self.cw_slider = ttk.Scale(gain_row, from_=0.05, to=1.0, variable=self.cw_gain, orient="horizontal", command=lambda v: self.cw_gain_lbl.config(text=f"{float(v):.2f}"))
        self.cw_slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._toggle_cw()
        self._audio_mode_widgets.append(cw_outer)

        dcb_outer = tk.Frame(body, bg=DARK, pady=5)
        dcb_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        dcb_hdr = tk.Frame(dcb_outer, bg=DARK)
        dcb_hdr.pack(fill="x")
        tk.Checkbutton(dcb_hdr, variable=self.dcb_enabled, bg=DARK, activebackground=DARK, fg=GOLD, selectcolor="#111116", relief="flat", bd=0, cursor="hand2", command=self._toggle_dcb).pack(side="left")
        tk.Label(dcb_hdr, text="🎚  DCB — Dynamic Compression Boost", font=FONT_BOLD, bg=DARK, fg=GOLD).pack(side="left")
        self.dcb_card = tk.Frame(dcb_outer, bg=CARD, padx=14, pady=12)
        self.dcb_card.pack(fill="x")
        dcb_rec = tk.Frame(self.dcb_card, bg="#1a1a00", padx=10, pady=7)
        dcb_rec.pack(fill="x", pady=(0,8))
        tk.Label(dcb_rec, text="💡 Valores recomendados:", font=("Segoe UI",9,"bold"), bg="#1a1a00", fg=GOLD).pack(anchor="w")
        tk.Label(dcb_rec, text="  • Threshold: 0.40–0.55  |  Ratio: 3:1–6:1  |  Makeup: 1.5×–2.2×", font=FONT_SMALL, bg="#1a1a00", fg=GOLD).pack(anchor="w")
        tk.Label(dcb_rec, text="  • Makeup Gain > 2.5× pode introduzir distorção", font=FONT_SMALL, bg="#1a1a00", fg=RED).pack(anchor="w")
        dcb_ctrl = tk.Frame(self.dcb_card, bg=CARD)
        dcb_ctrl.pack(fill="x")
        self._dcb_slider_row(dcb_ctrl, "Threshold",   self.dcb_threshold, 0.10, 0.90, "{:.2f}",  GOLD)
        self._dcb_slider_row(dcb_ctrl, "Ratio",       self.dcb_ratio,     1.0,  10.0, "{:.1f}:1", GOLD)
        self._dcb_slider_row(dcb_ctrl, "Makeup Gain", self.dcb_makeup,    0.5,  3.0,  "{:.2f}×",  WARN)
        self._toggle_dcb()
        self._audio_mode_widgets.append(dcb_outer)

        var_outer = tk.Frame(body, bg=DARK, pady=5)
        var_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(var_outer, text="🎲  Variações de metadados", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        var_card = tk.Frame(var_outer, bg=CARD, padx=14, pady=12)
        var_card.pack(fill="x")

        spin_frame = tk.Frame(var_card, bg=CARD)
        spin_frame.pack(fill="x")
        self.var_minus_btn = tk.Button(spin_frame, text="  −  ", font=("Segoe UI",12,"bold"), bg="#2a1a1a", fg=RED, relief="flat", cursor="hand2", padx=6, pady=4, command=self._decrement_variants)
        self.var_minus_btn.pack(side="left")
        self.var_display = tk.Label(spin_frame, text="0", font=("Segoe UI",14,"bold"), bg=CARD, fg=TEXT, width=4, anchor="center")
        self.var_display.pack(side="left", padx=4)
        self.var_plus_btn = tk.Button(spin_frame, text="  +  ", font=("Segoe UI",12,"bold"), bg="#1a2a1a", fg=GREEN, relief="flat", cursor="hand2", padx=6, pady=4, command=self._increment_variants)
        self.var_plus_btn.pack(side="left")
        self.var_hint = tk.Label(spin_frame, text="sem variações", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self.var_hint.pack(side="left", padx=(10,0))
        self.n_variants.trace_add("write", lambda *_: self._sync_var_display())

        tk.Frame(var_card, bg=MUTED, height=1).pack(fill="x", pady=(10, 8))
        self.variation_level_selector = VariationLevelSelector(var_card)
        self.variation_level_selector.pack(fill="x")

        prog_card = self._card(body, row=row_idx, label="⚙️  Progresso"); row_idx += 1
        self.progress = ttk.Progressbar(prog_card, mode="determinate", maximum=100, length=400)
        self.progress.pack(fill="x")
        self.status_lbl = tk.Label(prog_card, text="Aguardando…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self.status_lbl.pack(anchor="w", pady=(4,0))

        log_card = self._card(body, row=row_idx, label="📋  Log de processamento"); row_idx += 1
        log_frame = tk.Frame(log_card, bg=CARD)
        log_frame.pack(fill="both", expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_box = tk.Text(log_frame, height=7, font=FONT_MONO, bg="#111116", fg="#a0a0b8", insertbackground=TEXT, relief="flat", state="disabled", wrap="word")
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.log_box.config(yscrollcommand=sb2.set)

        btn_frame = tk.Frame(self, bg=DARK, pady=14)
        btn_frame.pack(fill="x", padx=24)
        self.run_btn = tk.Button(btn_frame, text="▶  PROCESSAR VÍDEO", font=("Segoe UI",11,"bold"), bg=ACCENT, fg="white", activebackground=ACC2, activeforeground="white", relief="flat", padx=28, pady=10, cursor="hand2", command=self._start_processing)
        self.run_btn.pack(side="right")
        self.preview_btn = tk.Button(btn_frame, text="🔍  Preview", font=("Segoe UI",11,"bold"), bg="#1a3a4a", fg=CYAN, relief="flat", padx=20, pady=10, cursor="hand2", state="disabled", command=self._open_preview)
        self.preview_btn.pack(side="right", padx=(0,8))
        self.trans_btn = tk.Button(btn_frame, text="🎙  Transcrever", font=("Segoe UI",11,"bold"), bg="#0f3030", fg=TEAL, relief="flat", padx=20, pady=10, cursor="hand2", command=self._open_transcription)
        self.trans_btn.pack(side="right", padx=(0,8))
        tk.Button(btn_frame, text="🗑  Limpar log", font=FONT_LABEL, bg=CARD, fg=MUTED, relief="flat", padx=14, pady=10, cursor="hand2", command=self._clear_log).pack(side="right", padx=(0,8))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, thickness=10, bordercolor=DARK, lightcolor=ACCENT)
        style.configure("Vertical.TScrollbar", troughcolor="#111116", background=MUTED, arrowcolor=MUTED, bordercolor=DARK)
        style.configure("TScale", background=CARD, troughcolor=PANEL, sliderthickness=16)
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=INPUT_BG, foreground=INPUT_FG, selectbackground=ACCENT)

    def _card(self, parent, row, label):
        outer = tk.Frame(parent, bg=DARK, pady=5)
        outer.grid(row=row, column=0, sticky="ew", pady=(0,4))
        tk.Label(outer, text=label, font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        card = tk.Frame(outer, bg=CARD, padx=14, pady=10)
        card.pack(fill="both", expand=True)
        return card

    def _file_row(self, parent, row, label, var, cmd, placeholder):
        outer = tk.Frame(parent, bg=DARK, pady=5)
        outer.grid(row=row, column=0, sticky="ew", pady=(0,4))
        tk.Label(outer, text=label, font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        card = tk.Frame(outer, bg=CARD, padx=14, pady=10)
        card.pack(fill="x")
        entry = tk.Entry(card, textvariable=var, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", disabledbackground=INPUT_BG, disabledforeground="#555555", relief="flat", bd=1)
        entry.insert(0, placeholder)
        entry.config(state="readonly")
        entry.pack(side="left", fill="x", expand=True)
        tk.Button(card, text="Escolher", font=FONT_LABEL, bg=ACCENT, fg="white", activebackground=ACC2, relief="flat", padx=10, pady=2, cursor="hand2", command=cmd).pack(side="right", padx=(8,0))

    def _dcb_slider_row(self, parent, label, var, from_, to, fmt, color):
        row = tk.Frame(parent, bg=CARD, pady=3)
        row.pack(fill="x")
        tk.Label(row, text=label, font=FONT_BOLD, bg=CARD, fg=MUTED, width=14, anchor="w").pack(side="left")
        val_lbl = tk.Label(row, text=fmt.format(var.get()), font=FONT_BOLD, bg=CARD, fg=color, width=8)
        val_lbl.pack(side="right")
        slider = ttk.Scale(row, from_=from_, to=to, variable=var, orient="horizontal",
                           command=lambda v, lbl=val_lbl, f=fmt: lbl.config(text=f.format(float(v))))
        slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._dcb_widgets.append(slider)

    def _on_mode_change(self, mode):
        if mode == "audio":
            for w in self._audio_mode_widgets:
                w.grid()
            self.run_btn.config(text="▶  PROCESSAR VÍDEO", bg=ACCENT)
        else:
            for w in self._audio_mode_widgets:
                w.grid_remove()
            self.run_btn.config(text="▶  GERAR VARIAÇÕES", bg=GREEN)

    def _increment_variants(self):
        if self.n_variants.get() < 50:
            self.n_variants.set(self.n_variants.get() + 1)

    def _decrement_variants(self):
        if self.n_variants.get() > 0:
            self.n_variants.set(self.n_variants.get() - 1)

    def _sync_var_display(self):
        n = self.n_variants.get()
        self.var_display.config(text=str(n))
        self.var_hint.config(text="sem variações" if n == 0 else f"+ {n} variação(ões)", fg=MUTED if n == 0 else WARN)
        self.var_minus_btn.config(state="normal" if n > 0 else "disabled", fg=RED if n > 0 else MUTED)

    def _toggle_cw(self):
        state = "normal" if self.cw_enabled.get() else "disabled"
        self.cw_entry.config(state=state)
        self.cw_slider.config(state=state)

    def _toggle_dcb(self):
        state = "normal" if self.dcb_enabled.get() else "disabled"
        for w in self._dcb_widgets:
            w.config(state=state)

    def _browse_input(self):
        path = filedialog.askopenfilename(title="Selecionar vídeo", filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("Todos","*.*")])
        if path:
            self.video_path.set(path)
            base, _ = os.path.splitext(path)
            self.output_path.set(base + "_audiofix.mp4")
            self._log(f"📂 Vídeo: {path}")
            self._last_original = path
            self.preview_btn.config(state="disabled")

    def _browse_output(self):
        path = filedialog.asksaveasfilename(title="Salvar como…", defaultextension=".mp4", filetypes=[("MP4","*.mp4"),("MKV","*.mkv"),("Todos","*.*")])
        if path: self.output_path.set(path)

    def _browse_cw(self):
        path = filedialog.askopenfilename(title="Selecionar WAV", filetypes=[("WAV","*.wav"),("Todos","*.*")])
        if path:
            self.cw_path.set(path)
            self._log(f"📻 Copy White: {path}")

    def _open_tts(self):
        TTSWindow(self, on_wav_ready=self._on_tts_wav_ready)

    def _on_tts_wav_ready(self, wav_path):
        self.cw_path.set(wav_path)
        self.cw_enabled.set(True)
        self._toggle_cw()
        self.tts_wav_badge.config(text=f"🎤 WAV via TTS: {os.path.basename(wav_path)}")
        children = self.cw_card.winfo_children()
        if children:
            self.tts_wav_badge.pack(fill="x", pady=(0,6), before=children[0])
        else:
            self.tts_wav_badge.pack(fill="x", pady=(0,6))
        self._log(f"🎤 Copy White (TTS): {wav_path}")
        messagebox.showinfo("Copy White atualizado!", f"WAV TTS aplicado:\n{wav_path}\n\nCopy White ativado automaticamente.")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0","end")
        self.log_box.config(state="disabled")

    def _log(self, msg):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg+"\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _set_progress(self, pct):
        self.after(0, lambda: self.progress.config(value=pct))
        labels = {20:"Extraindo áudio…",45:"Processando…",65:"Convertendo para MP3…",80:"Unindo vídeo + áudio…",60:"Copiando vídeo original…",100:"✅ Concluído!"}
        if pct in labels:
            self.after(0, lambda: self.status_lbl.config(text=labels[pct], fg=GREEN if pct==100 else TEXT))

    def _get_noise_amplitudes(self):
        return {name: ctrl.amplitude for name, ctrl in self._noise_controls.items()}

    def _open_preview(self):
        if not self._last_processed or not os.path.isfile(self._last_processed):
            messagebox.showwarning("Preview","Nenhum vídeo processado disponível."); return
        PreviewWindow(self, original_path=self._last_original, processed_path=self._last_processed, variants=self._last_variants)

    def _open_transcription(self):
        video = self.video_path.get().strip()
        TranscriptionWindow(self, video_path=video if os.path.isfile(video) else None)

    def _start_processing(self):
        if self.running: return
        if not _FFMPEG_OK:
            messagebox.showerror("ffmpeg não encontrado", _ffmpeg_install_hint()); return

        vin  = self.video_path.get().strip()
        vout = self.output_path.get().strip()
        if not vin or not os.path.isfile(vin):
            messagebox.showerror("Erro","Selecione um vídeo de entrada válido."); return
        if not vout:
            messagebox.showerror("Erro","Defina o arquivo de saída."); return

        mode  = self.mode_selector.mode
        n     = self.n_variants.get()
        level = self.variation_level_selector.level

        if mode == "audio":
            self._run_audio_mode(vin, vout, n, level)
        else:
            self._run_original_mode(vin, vout, n, level)

    def _run_audio_mode(self, vin, vout, n, level):
        noise_amps = self._get_noise_amplitudes()
        ativos     = [k for k,v in noise_amps.items() if v > 0]
        cw_path    = None
        cw_gain    = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path = self.cw_path.get().strip()
            if not cw_path or not os.path.isfile(cw_path):
                messagebox.showerror("Erro","Copy White ativo mas sem WAV válido selecionado."); return
        if not ativos and not cw_path:
            ok = messagebox.askyesno("Nenhum ruído ativo","Sem ruídos e sem Copy White.\nApenas inversão de fase será aplicada. Continuar?")
            if not ok: return
        if n > 10:
            ok = messagebox.askyesno("Confirmar",f"Você solicitou {n} variações [{level}]. Continuar?")
            if not ok: return

        self.running = True
        self.run_btn.config(state="disabled", text="⏳  Processando…", bg=MUTED)
        self.preview_btn.config(state="disabled")
        self.progress.config(value=0)
        self.status_lbl.config(text="Iniciando…", fg=TEXT)
        self._clear_log()
        self._log(f"🎛️ Modo: Manipular Áudio  |  Nível de variação: {level}")

        def worker():
            try:
                full_pipeline_audio(
                    video_path=vin, output_path=vout,
                    noise_amplitudes=noise_amps,
                    copy_white_path=cw_path, copy_white_gain=cw_gain,
                    dcb_enabled=self.dcb_enabled.get(),
                    dcb_threshold=self.dcb_threshold.get(),
                    dcb_ratio=self.dcb_ratio.get(),
                    dcb_makeup=self.dcb_makeup.get(),
                    n_variants=n, variation_level=level,
                    progress_cb=self._set_progress, log_cb=self._log,
                )
                self._last_original  = vin
                self._last_processed = vout
                self._last_variants  = []
                if n > 0:
                    base, ext = os.path.splitext(vout)
                    self._last_variants = [f"{base}_var{i:02d}{ext}" for i in range(1,n+1) if os.path.isfile(f"{base}_var{i:02d}{ext}")]
                self.after(0, lambda: self.preview_btn.config(state="normal"))
                self.after(0, lambda: messagebox.showinfo("Concluído!", f"{1+n} arquivo(s) gerado(s).\nPrincipal: {vout}\n\nClique em '🔍 Preview' para inspecionar."))
            except Exception as e:
                err_msg = str(e)
                self._log(f"❌ ERRO: {err_msg}")
                self.after(0, lambda: messagebox.showerror("Erro", err_msg))
                self.after(0, lambda: self.status_lbl.config(text=f"❌ {err_msg}", fg=RED))
            finally:
                self.running = False
                self.after(0, lambda: self.run_btn.config(state="normal", text="▶  PROCESSAR VÍDEO", bg=ACCENT))

        threading.Thread(target=worker, daemon=True).start()

    def _run_original_mode(self, vin, vout, n, level):
        self.running = True
        self.run_btn.config(state="disabled", text="⏳  Gerando…", bg=MUTED)
        self.preview_btn.config(state="disabled")
        self.progress.config(value=0)
        self.status_lbl.config(text="Iniciando…", fg=TEXT)
        self._clear_log()
        self._log(f"🎬 Modo: Áudio Original  |  Nível de variação: {level}")

        def worker():
            try:
                full_pipeline_original(
                    video_path=vin, output_path=vout,
                    n_variants=n, variation_level=level,
                    progress_cb=self._set_progress, log_cb=self._log,
                )
                self._last_original  = vin
                self._last_processed = vout
                self._last_variants  = []
                if n > 0:
                    base, ext = os.path.splitext(vout)
                    self._last_variants = [f"{base}_var{i:02d}{ext}" for i in range(1,n+1) if os.path.isfile(f"{base}_var{i:02d}{ext}")]
                self.after(0, lambda: self.preview_btn.config(state="normal"))
                self.after(0, lambda: messagebox.showinfo("Concluído!", f"{1+n} arquivo(s) gerado(s).\nPrincipal: {vout}"))
            except Exception as e:
                err_msg = str(e)
                self._log(f"❌ ERRO: {err_msg}")
                self.after(0, lambda: messagebox.showerror("Erro", err_msg))
                self.after(0, lambda: self.status_lbl.config(text=f"❌ {err_msg}", fg=RED))
            finally:
                self.running = False
                self.after(0, lambda: self.run_btn.config(state="normal", text="▶  GERAR VARIAÇÕES", bg=GREEN))

        threading.Thread(target=worker, daemon=True).start()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    splash = SplashScreen()
    threading.Thread(target=_run_loading, args=(splash,), daemon=True).start()
    splash.mainloop()
