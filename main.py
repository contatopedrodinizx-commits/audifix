#!/usr/bin/env python3
"""
AudioFix Pro — Batch Edition
=============================
Todas as funções originais + suporte a:
  • Upload de UM vídeo  (modo clássico)
  • Upload de VÁRIOS vídeos  (processamento em lote)
    - Fila visual com status por item
    - Progresso global + individual
    - Arrastar-e-soltar (.drop_files) com fallback via botão
    - Cancelar item ou toda a fila
    - Reprocessar apenas os com erro
    - Saída automática: mesma pasta + sufixo _audiofix

Requisitos: Python 3.8+, ffmpeg no PATH
"""

import sys
import os
import subprocess
import importlib
import platform
import threading
import tempfile
import random
import string
import datetime
import json
import math
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ─── Versão ───────────────────────────────────────────────────────────────────
VERSAO_ATUAL = "4.5"
GITHUB_REPO  = "contatopedrodinizx-commits/audifix"
URL_DOWNLOAD = f"https://github.com/{GITHUB_REPO}/releases/latest"

# ─── Ocultar console Windows ──────────────────────────────────────────────────
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


# ─── Helpers de instalação ────────────────────────────────────────────────────
def _pip_install(*packages):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0, r.stderr
    except Exception as e:
        return False, str(e)

def _is_importable(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False

def _ensure_packages():
    missing = [(p, p) for p in ["numpy", "scipy"] if not _is_importable(p)]
    if missing:
        _pip_install(*[p for p, _ in missing])
        importlib.invalidate_caches()

def _check_ffmpeg():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def _ffmpeg_install_hint():
    s = platform.system()
    if s == "Windows":
        return ("ffmpeg não encontrado.\n\nComo instalar:\n"
                "  • winget install ffmpeg\n"
                "  • ou: https://www.gyan.dev/ffmpeg/builds/\n\nApós instalar, reinicie o app.")
    elif s == "Darwin":
        return "ffmpeg não encontrado.\n\nbrew install ffmpeg"
    else:
        return ("ffmpeg não encontrado.\n\n"
                "  Ubuntu/Debian:  sudo apt install ffmpeg\n"
                "  Fedora:         sudo dnf install ffmpeg\n"
                "  Arch:           sudo pacman -S ffmpeg")

def _check_gtts_silent():   return _is_importable("gtts")
def _check_whisper_silent(): return _is_importable("faster_whisper") or _is_importable("whisper")

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

# ─── Variáveis globais ────────────────────────────────────────────────────────
_FFMPEG_OK  = False
_WHISPER_OK = False
_GTTS_OK    = False

# ─── Geradores de ruído ───────────────────────────────────────────────────────
def generate_pink_noise(n_samples, amplitude, seed=42):
    import numpy as np
    rng = np.random.default_rng(seed)
    n_rows = 16; pink = np.zeros(n_samples)
    running_sum = rng.random(n_rows); total = running_sum.sum()
    for i in range(n_samples):
        k = int(np.log2((i & -i) + 1)) % n_rows if i > 0 else 0
        old_val = running_sum[k]; running_sum[k] = rng.random()
        total += running_sum[k] - old_val; pink[i] = total
    pink -= pink.mean(); mx = np.abs(pink).max()
    if mx > 0: pink = pink / mx * amplitude
    return pink.astype(np.float64)

def generate_white_noise(n_samples, amplitude, seed=43):
    import numpy as np
    rng = np.random.default_rng(seed); noise = rng.standard_normal(n_samples)
    mx = np.abs(noise).max()
    if mx > 0: noise = noise / mx * amplitude
    return noise.astype(np.float64)

def generate_brown_noise(n_samples, amplitude, seed=44):
    import numpy as np
    rng = np.random.default_rng(seed); brown = np.cumsum(rng.standard_normal(n_samples))
    brown -= brown.mean(); mx = np.abs(brown).max()
    if mx > 0: brown = brown / mx * amplitude
    return brown.astype(np.float64)

def generate_blue_noise(n_samples, amplitude, seed=45):
    import numpy as np
    rng = np.random.default_rng(seed); white = rng.standard_normal(n_samples)
    blue = np.diff(white, prepend=white[0]); blue -= blue.mean()
    mx = np.abs(blue).max()
    if mx > 0: blue = blue / mx * amplitude
    return blue.astype(np.float64)

def generate_violet_noise(n_samples, amplitude, seed=46):
    import numpy as np
    rng = np.random.default_rng(seed); white = rng.standard_normal(n_samples)
    violet = np.diff(np.diff(white, prepend=white[0]), prepend=white[0])
    violet -= violet.mean(); mx = np.abs(violet).max()
    if mx > 0: violet = violet / mx * amplitude
    return violet.astype(np.float64)

def generate_grey_noise(n_samples, amplitude, seed=47):
    import numpy as np
    rng = np.random.default_rng(seed); white = rng.standard_normal(n_samples)
    fft = np.fft.rfft(white)
    freqs_hz = np.abs(np.fft.rfftfreq(n_samples)) * 44100; eps = 1e-6
    f = np.maximum(freqs_hz, eps)
    weight = (f/1000.0)**0.3 / (1.0+(f/6000.0)**2.0+(1.0/(f/120.0+eps))**1.5)
    weight = np.maximum(weight, eps) / weight.max()
    grey = np.fft.irfft(fft * weight, n=n_samples); grey -= grey.mean()
    mx = np.abs(grey).max()
    if mx > 0: grey = grey / mx * amplitude
    return grey.astype(np.float64)

NOISE_GENERATORS = {
    "Rosa": generate_pink_noise, "Branco": generate_white_noise,
    "Marrom": generate_brown_noise, "Azul": generate_blue_noise,
    "Violeta": generate_violet_noise, "Cinza": generate_grey_noise,
}
NOISE_DESCRIPTIONS = {
    "Rosa": "1/f · equilíbrio natural", "Branco": "energia uniforme em todas as freq.",
    "Marrom": "1/f² · grave e profundo", "Azul": "f · ênfase nos agudos",
    "Violeta": "f² · agudos muito acentuados", "Cinza": "eq. psicoacústica (equal loudness)",
}

# ─── Variação de metadados ────────────────────────────────────────────────────
VARIATION_LEVELS = {
    "Normal":   {"label":"Normal",   "desc":"Mudanças sutis · título leve · data próxima",      "color":"#4ade80","title_len":4,"artist_len":4,"album_len":3,"comment_len":6, "date_range":30,  "track_range":(1,20), "encoder_var":False},
    "Moderada": {"label":"Moderada", "desc":"Alterações médias · campos misturados",            "color":"#fbbf24","title_len":6,"artist_len":5,"album_len":4,"comment_len":9, "date_range":365, "track_range":(1,50), "encoder_var":True},
    "Intensa":  {"label":"Intensa",  "desc":"Metadados bem distintos · datas variadas",         "color":"#f97316","title_len":8,"artist_len":7,"album_len":6,"comment_len":12,"date_range":1095,"track_range":(1,99), "encoder_var":True},
    "Brusca":   {"label":"Brusca",   "desc":"Metadados completamente aleatórios · máx. diverg.","color":"#f87171","title_len":12,"artist_len":10,"album_len":9,"comment_len":18,"date_range":3650,"track_range":(1,999),"encoder_var":True},
}

def _rand_str(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def _rand_date(max_days_back=365):
    today = datetime.date.today(); start = today - datetime.timedelta(days=max_days_back)
    return str(start + datetime.timedelta(days=random.randint(0, (today - start).days)))

def generate_metadata_variants(n, level="Normal"):
    cfg = VARIATION_LEVELS.get(level, VARIATION_LEVELS["Normal"]); result = []
    for _ in range(n):
        meta = {"title":f"Video_{_rand_str(cfg['title_len'])}","artist":f"Creator_{_rand_str(cfg['artist_len'])}",
                "album":f"Collection_{_rand_str(cfg['album_len'])}","comment":f"Processed_{_rand_str(cfg['comment_len'])}",
                "date":_rand_date(cfg['date_range']),"track":str(random.randint(*cfg['track_range']))}
        if cfg["encoder_var"]: meta["encoder"] = f"Encoder_{_rand_str(4)}_{random.randint(1,99)}"
        result.append(meta)
    return result

# ─── Processamento de áudio ───────────────────────────────────────────────────
def load_and_resample_wav(path, target_sr=44100):
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    from math import gcd
    sr, data = wavfile.read(path)
    if data.dtype == np.int16: data = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32: data = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.uint8: data = (data.astype(np.float64) - 128.0) / 128.0
    else: data = data.astype(np.float64)
    if data.ndim == 1: data = np.stack([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] == 1: data = np.concatenate([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] > 2: data = data[:, :2]
    if sr != target_sr:
        g = gcd(sr, target_sr); up, down = target_sr // g, sr // g
        data = np.stack([resample_poly(data[:, 0], up, down), resample_poly(data[:, 1], up, down)], axis=1)
    return data, target_sr

def apply_dcb(data, threshold=0.5, ratio=4.0, makeup_gain=1.8):
    import numpy as np
    out = data.copy(); mask = np.abs(out) > threshold
    excess = np.abs(out[mask]) - threshold
    out[mask] = np.sign(out[mask]) * (threshold + excess / ratio)
    return np.clip(out * makeup_gain, -1.0, 1.0)

def process_audio(input_wav, output_wav, noise_amplitudes=None,
                  copy_white_path=None, copy_white_gain=0.5,
                  dcb_enabled=False, dcb_threshold=0.5,
                  dcb_ratio=4.0, dcb_makeup=1.8, target_sr=44100):
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    from math import gcd
    if noise_amplitudes is None: noise_amplitudes = {"Rosa": 0.003}
    sr, data = wavfile.read(input_wav)
    if data.dtype == np.int16: data = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32: data = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.uint8: data = (data.astype(np.float64) - 128.0) / 128.0
    else: data = data.astype(np.float64)
    if data.ndim == 1: data = np.stack([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] == 1: data = np.concatenate([data, data], axis=1)
    elif data.ndim == 2 and data.shape[1] > 2: data = data[:, :2]
    if sr != target_sr:
        g = gcd(sr, target_sr); up, down = target_sr // g, sr // g
        data = np.stack([resample_poly(data[:, 0], up, down), resample_poly(data[:, 1], up, down)], axis=1)
        sr = target_sr
    n = len(data); left = data[:, 0].copy(); right = -data[:, 0].copy()
    for idx, (name, amp) in enumerate(noise_amplitudes.items()):
        if amp <= 0: continue
        gen = NOISE_GENERATORS.get(name)
        if gen is None: continue
        noise = gen(n, amp, seed=42+idx); left += noise; right += noise
    if copy_white_path and os.path.isfile(copy_white_path):
        cw, _ = load_and_resample_wav(copy_white_path, target_sr)
        cw_len = len(cw)
        if cw_len < n:
            import math as _math
            repeats = int(_math.ceil(n / cw_len))
            cw = np.tile(cw, (repeats, 1))
        cw = cw[:n]
        left  += cw[:, 0] * copy_white_gain
        right += cw[:, 1] * copy_white_gain
    left = np.clip(left, -1.0, 1.0); right = np.clip(right, -1.0, 1.0)
    if dcb_enabled:
        stereo = apply_dcb(np.stack([left, right], axis=1), dcb_threshold, dcb_ratio, dcb_makeup)
        left, right = stereo[:, 0], stereo[:, 1]
    wavfile.write(output_wav, sr, np.stack([left, right], axis=1).astype(np.float32))

def _run_cmd(cmd, log_fn=None):
    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, creationflags=flags)
    for line in proc.stdout:
        if log_fn: log_fn(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Comando falhou (código {proc.returncode}): {' '.join(cmd)}")

def extract_audio(video_path, wav_path, log_fn=None):
    _run_cmd(["ffmpeg","-y","-i",video_path,"-vn","-acodec","pcm_f32le","-ar","44100",wav_path], log_fn)

def wav_to_mp3(wav_path, mp3_path, log_fn=None):
    _run_cmd(["ffmpeg","-y","-i",wav_path,"-acodec","libmp3lame","-b:a","192k","-ar","44100","-ac","2",mp3_path], log_fn)

def merge_audio_video(video_path, audio_path, output_path, metadata=None, log_fn=None):
    cmd = ["ffmpeg","-y","-i",video_path,"-i",audio_path,"-c:v","copy","-c:a","copy","-map","0:v:0","-map","1:a:0"]
    if metadata:
        for k, v in metadata.items(): cmd += ["-metadata", f"{k}={v}"]
    cmd.append(output_path); _run_cmd(cmd, log_fn)

def copy_video_only(video_path, output_path, metadata=None, log_fn=None):
    cmd = ["ffmpeg","-y","-i",video_path,"-c:v","copy","-c:a","copy"]
    if metadata:
        for k, v in metadata.items(): cmd += ["-metadata", f"{k}={v}"]
    cmd.append(output_path); _run_cmd(cmd, log_fn)

def get_video_info(path):
    try:
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        cmd = ["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",path]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
        if result.returncode == 0:
            data = json.loads(result.stdout); info = {}
            fmt = data.get("format", {}); info["duration"] = float(fmt.get("duration",0))
            info["size_mb"] = os.path.getsize(path)/(1024*1024); info["bitrate"] = int(fmt.get("bit_rate",0))//1000
            for stream in data.get("streams",[]):
                if stream.get("codec_type") == "video":
                    info["video_codec"] = stream.get("codec_name","?"); info["width"] = stream.get("width",0)
                    info["height"] = stream.get("height",0)
                    try: n, d = stream.get("r_frame_rate","0/1").split("/"); info["fps"] = round(int(n)/int(d),2)
                    except: info["fps"] = 0
                elif stream.get("codec_type") == "audio":
                    info["audio_codec"] = stream.get("codec_name","?"); info["sample_rate"] = stream.get("sample_rate","?")
                    info["channels"] = stream.get("channels",0); info["channel_layout"] = stream.get("channel_layout","?")
            return info
    except: pass
    return {}

def open_video_player(path):
    if sys.platform == "win32": os.startfile(path)
    elif sys.platform == "darwin": subprocess.Popen(["open", path])
    else:
        for p in ["xdg-open","vlc","mpv","mplayer","totem"]:
            try: subprocess.Popen([p, path]); return
            except FileNotFoundError: continue

def full_pipeline_audio(video_path, output_path, noise_amplitudes=None,
                        copy_white_path=None, copy_white_gain=0.5,
                        dcb_enabled=False, dcb_threshold=0.5,
                        dcb_ratio=4.0, dcb_makeup=1.8,
                        n_variants=0, variation_level="Normal",
                        progress_cb=None, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    if noise_amplitudes is None: noise_amplitudes = {"Rosa": 0.003}
    with tempfile.TemporaryDirectory(prefix="audiofix_") as tmp:
        raw_wav = os.path.join(tmp, "raw.wav"); proc_wav = os.path.join(tmp, "processed.wav")
        out_mp3 = os.path.join(tmp, "processed.mp3")
        log("▶ Extraindo áudio…"); extract_audio(video_path, raw_wav, log)
        if progress_cb: progress_cb(20)
        log("▶ Aplicando inversão de fase + ruídos + DCB…")
        process_audio(raw_wav, proc_wav, noise_amplitudes=noise_amplitudes,
                      copy_white_path=copy_white_path, copy_white_gain=copy_white_gain,
                      dcb_enabled=dcb_enabled, dcb_threshold=dcb_threshold,
                      dcb_ratio=dcb_ratio, dcb_makeup=dcb_makeup)
        if progress_cb: progress_cb(45)
        log("▶ Convertendo para MP3…"); wav_to_mp3(proc_wav, out_mp3, log)
        if progress_cb: progress_cb(65)
        log("▶ Unindo áudio + vídeo…"); merge_audio_video(video_path, out_mp3, output_path, log_fn=log)
        if progress_cb: progress_cb(80)
        if n_variants > 0:
            base, ext = os.path.splitext(output_path)
            for idx, meta in enumerate(generate_metadata_variants(n_variants, variation_level), 1):
                vp = f"{base}_var{idx:02d}{ext}"
                log(f"   [{idx}/{n_variants}] → {os.path.basename(vp)}")
                merge_audio_video(video_path, out_mp3, vp, metadata=meta, log_fn=log)
                if progress_cb: progress_cb(80 + int((idx/n_variants)*18))
        if progress_cb: progress_cb(100)
        log(f"✅ {1+n_variants} arquivo(s) gerado(s). → {output_path}")

def full_pipeline_original(video_path, output_path, n_variants=0, variation_level="Normal",
                           progress_cb=None, log_cb=None):
    def log(msg):
        if log_cb: log_cb(msg)
    copy_video_only(video_path, output_path, log_fn=log)
    if progress_cb: progress_cb(60)
    if n_variants > 0:
        base, ext = os.path.splitext(output_path)
        for idx, meta in enumerate(generate_metadata_variants(n_variants, variation_level), 1):
            vp = f"{base}_var{idx:02d}{ext}"
            copy_video_only(video_path, vp, metadata=meta, log_fn=log)
            if progress_cb: progress_cb(60 + int((idx/n_variants)*38))
    if progress_cb: progress_cb(100)
    log(f"✅ {1+n_variants} arquivo(s) gerado(s).")


# ═══════════════════════════════════════════════════════════════════════════════
#   WIDGETS REUTILIZÁVEIS
# ═══════════════════════════════════════════════════════════════════════════════

class NoiseControl(tk.Frame):
    def __init__(self, parent, name, color, default_amp=0.0, **kwargs):
        super().__init__(parent, bg=CARD, padx=10, pady=8, **kwargs)
        self.name = name; self.color = color
        self._enabled = tk.BooleanVar(value=default_amp > 0)
        self._amp = tk.DoubleVar(value=default_amp if default_amp > 0 else 0.003)
        top = tk.Frame(self, bg=CARD); top.pack(fill="x")
        tk.Checkbutton(top, variable=self._enabled, bg=CARD, activebackground=CARD, fg=color,
                       selectcolor="#111116", relief="flat", bd=0, cursor="hand2",
                       command=self._toggle).pack(side="left")
        self._name_lbl = tk.Label(top, text=f"Ruído {name}", font=FONT_BOLD, bg=CARD, fg=color)
        self._name_lbl.pack(side="left")
        tk.Label(top, text=f"  ·  {NOISE_DESCRIPTIONS.get(name,'')}", font=FONT_SMALL, bg=CARD, fg=MUTED).pack(side="left")
        self._amp_lbl = tk.Label(top, text=f"{self._amp.get():.4f}", font=FONT_BOLD, bg=CARD, fg=color, width=7)
        self._amp_lbl.pack(side="right")
        self._slider = ttk.Scale(self, from_=0.0001, to=0.02, variable=self._amp, orient="horizontal", command=self._on_slide)
        self._slider.pack(fill="x", pady=(4,0)); self._toggle()

    def _toggle(self):
        state = "normal" if self._enabled.get() else "disabled"; self._slider.config(state=state)
        fg = self.color if self._enabled.get() else MUTED
        self._name_lbl.config(fg=fg); self._amp_lbl.config(fg=fg)

    def _on_slide(self, *_): self._amp_lbl.config(text=f"{self._amp.get():.4f}")

    @property
    def amplitude(self): return self._amp.get() if self._enabled.get() else 0.0


class VariationLevelSelector(tk.Frame):
    LEVELS = list(VARIATION_LEVELS.keys())
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=CARD, **kwargs)
        self._level = tk.StringVar(value="Normal"); self._btns = {}; self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=CARD); hdr.pack(fill="x", pady=(0,8))
        tk.Label(hdr, text="📊  Nível de variação dos metadados:", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(side="left")
        self._desc_lbl = tk.Label(hdr, text="", font=FONT_SMALL, bg=CARD, fg=MUTED); self._desc_lbl.pack(side="right")
        btn_row = tk.Frame(self, bg=CARD); btn_row.pack(fill="x")
        for i in range(4): btn_row.columnconfigure(i, weight=1)
        for idx, level_name in enumerate(self.LEVELS):
            cfg = VARIATION_LEVELS[level_name]; col = cfg["color"]
            btn_outer = tk.Frame(btn_row, bg=MUTED, padx=1, pady=1)
            btn_outer.grid(row=0, column=idx, sticky="ew", padx=(0,3) if idx < 3 else 0)
            btn_inner = tk.Frame(btn_outer, bg=CARD, padx=8, pady=8, cursor="hand2"); btn_inner.pack(fill="both", expand=True)
            name_lbl = tk.Label(btn_inner, text=cfg["label"], font=FONT_BOLD, bg=CARD, fg=TEXT); name_lbl.pack(anchor="center")
            line = tk.Frame(btn_inner, bg=col, height=3); line.pack(fill="x", pady=(4,0))
            rb = tk.Radiobutton(btn_inner, variable=self._level, value=level_name, bg=CARD, activebackground=CARD,
                                selectcolor="#111116", relief="flat", bd=0, cursor="hand2", command=self._refresh)
            rb.pack(anchor="e")
            for w in [btn_outer, btn_inner, name_lbl, line]: w.bind("<Button-1>", lambda e, lv=level_name: self._select(lv))
            self._btns[level_name] = (btn_outer, btn_inner, name_lbl, line, rb)
        ex_card = tk.Frame(self, bg="#111116", padx=10, pady=8); ex_card.pack(fill="x", pady=(8,0))
        self._ex_title = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=ACC2); self._ex_title.pack(anchor="w")
        self._ex_date  = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=MUTED);  self._ex_date.pack(anchor="w")
        self._refresh()

    def _select(self, level_name): self._level.set(level_name); self._refresh()

    def _refresh(self):
        selected = self._level.get(); cfg = VARIATION_LEVELS[selected]
        for lv_name, (outer, inner, name_lbl, line, rb) in self._btns.items():
            is_sel = lv_name == selected; lv_cfg = VARIATION_LEVELS[lv_name]
            try:
                if is_sel:
                    outer.config(bg=lv_cfg["color"]); inner.config(bg="#181818")
                    name_lbl.config(bg="#181818", fg=lv_cfg["color"]); line.config(bg=lv_cfg["color"])
                    rb.config(bg="#181818", selectcolor="#0d0d0d", activebackground="#181818")
                else:
                    outer.config(bg=MUTED); inner.config(bg=CARD)
                    name_lbl.config(bg=CARD, fg=TEXT); line.config(bg=lv_cfg["color"])
                    rb.config(bg=CARD, selectcolor="#111116", activebackground=CARD)
            except Exception: pass
        self._desc_lbl.config(text=cfg["desc"], fg=cfg["color"])
        ex_meta = generate_metadata_variants(1, selected)[0]
        self._ex_title.config(text=f"  title:  {ex_meta['title']}")
        self._ex_date.config(text=f"  date:   {ex_meta['date']}")

    @property
    def level(self): return self._level.get()


# ═══════════════════════════════════════════════════════════════════════════════
#   ITEM DA FILA (BatchQueueItem)
# ═══════════════════════════════════════════════════════════════════════════════

class BatchQueueItem(tk.Frame):
    """Uma linha na fila de lote com: ícone de status, nome, barra de progresso, botão remover."""

    STATUS_PENDING    = "pending"
    STATUS_RUNNING    = "running"
    STATUS_DONE       = "done"
    STATUS_ERROR      = "error"
    STATUS_CANCELLED  = "cancelled"

    STATUS_COLORS = {
        STATUS_PENDING:   MUTED,
        STATUS_RUNNING:   ACCENT,
        STATUS_DONE:      GREEN,
        STATUS_ERROR:     RED,
        STATUS_CANCELLED: WARN,
    }
    STATUS_ICONS = {
        STATUS_PENDING:   "⏳",
        STATUS_RUNNING:   "⚙️",
        STATUS_DONE:      "✅",
        STATUS_ERROR:     "❌",
        STATUS_CANCELLED: "⚠️",
    }

    def __init__(self, parent, video_path, on_remove=None, **kwargs):
        super().__init__(parent, bg=CARD, padx=10, pady=8, **kwargs)
        self.video_path = video_path
        self.on_remove  = on_remove
        self._status    = self.STATUS_PENDING
        self._output_path = None
        self._error_msg   = None
        self._build()

    def _build(self):
        self.config(relief="flat", bd=0)
        # Linha superior
        top = tk.Frame(self, bg=CARD); top.pack(fill="x")
        self._icon_lbl = tk.Label(top, text="⏳", font=("Segoe UI Emoji", 12),
                                  bg=CARD, fg=MUTED, width=3)
        self._icon_lbl.pack(side="left")
        name_frame = tk.Frame(top, bg=CARD); name_frame.pack(side="left", fill="x", expand=True, padx=(4,0))
        basename = os.path.basename(self.video_path)
        self._name_lbl = tk.Label(name_frame, text=basename, font=FONT_BOLD, bg=CARD, fg=TEXT,
                                  anchor="w", wraplength=0)
        self._name_lbl.pack(anchor="w")
        dir_text = os.path.dirname(self.video_path)
        if len(dir_text) > 60: dir_text = "…" + dir_text[-57:]
        tk.Label(name_frame, text=dir_text, font=FONT_SMALL, bg=CARD, fg=MUTED, anchor="w").pack(anchor="w")

        self._remove_btn = tk.Button(top, text="✕", font=FONT_SMALL, bg="#2a1a1a", fg=RED,
                                     relief="flat", padx=8, pady=2, cursor="hand2",
                                     command=self._do_remove)
        self._remove_btn.pack(side="right")

        # Barra de progresso
        self._prog = ttk.Progressbar(self, mode="determinate", maximum=100, length=200)
        self._prog.pack(fill="x", pady=(6,0))

        # Status
        self._status_lbl = tk.Label(self, text="Na fila…", font=FONT_STATUS, bg=CARD, fg=MUTED, anchor="w")
        self._status_lbl.pack(anchor="w", pady=(2,0))

        # Separador
        tk.Frame(self, bg="#2a2a35", height=1).pack(fill="x", pady=(8,0))

    def _do_remove(self):
        if self._status == self.STATUS_RUNNING: return
        if self.on_remove: self.on_remove(self)

    def set_status(self, status, message="", progress=None):
        self._status = status
        color = self.STATUS_COLORS.get(status, MUTED)
        icon  = self.STATUS_ICONS.get(status, "•")
        self._icon_lbl.config(text=icon, fg=color)
        self._status_lbl.config(text=message or status, fg=color)
        self._name_lbl.config(fg=TEXT if status != self.STATUS_CANCELLED else MUTED)
        if progress is not None:
            mode = "indeterminate" if progress < 0 else "determinate"
            self._prog.config(mode=mode)
            if progress >= 0:
                self._prog.config(value=progress)
            else:
                self._prog.start(12)
        if status != self.STATUS_RUNNING:
            try: self._prog.stop()
            except: pass
        self._remove_btn.config(state="disabled" if status == self.STATUS_RUNNING else "normal")

    def set_output(self, path): self._output_path = path
    def set_error(self, msg):   self._error_msg = msg

    @property
    def status(self):      return self._status
    @property
    def output_path(self): return self._output_path
    @property
    def error_msg(self):   return self._error_msg


# ═══════════════════════════════════════════════════════════════════════════════
#   PAINEL DE FILA EM LOTE (BatchQueuePanel)
# ═══════════════════════════════════════════════════════════════════════════════

class BatchQueuePanel(tk.Frame):
    """Painel completo de fila com drag-and-drop, botões e scroll."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._items: list[BatchQueueItem] = []
        self._build()

    def _build(self):
        # Cabeçalho
        hdr = tk.Frame(self, bg=DARK); hdr.pack(fill="x", pady=(0,8))
        tk.Label(hdr, text="📂  Fila de Vídeos", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="0 vídeos", font=FONT_SMALL, bg=DARK, fg=MUTED)
        self._count_lbl.pack(side="left", padx=(8,0))

        btn_row = tk.Frame(hdr, bg=DARK); btn_row.pack(side="right")
        tk.Button(btn_row, text="➕  Adicionar vídeos", font=FONT_LABEL, bg=ACCENT, fg="white",
                  activebackground=ACC2, relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._browse_add).pack(side="left", padx=(0,6))
        tk.Button(btn_row, text="📁  Adicionar pasta", font=FONT_LABEL, bg="#2a2a35", fg=ACC2,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._browse_folder).pack(side="left", padx=(0,6))
        tk.Button(btn_row, text="🗑  Limpar fila", font=FONT_LABEL, bg="#2a1a1a", fg=RED,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._clear_queue).pack(side="left")

        # Drop zone
        self._drop_zone = tk.Frame(self, bg="#1a1a22", relief="flat", bd=0)
        self._drop_zone.pack(fill="x", pady=(0,8))
        self._drop_lbl = tk.Label(
            self._drop_zone,
            text="🎬  Arraste vídeos aqui  ou  clique em 'Adicionar vídeos'",
            font=("Segoe UI", 10), bg="#1a1a22", fg=MUTED, pady=20,
        )
        self._drop_lbl.pack()

        # Tentar registrar drop (funciona com tkinterdnd2 se instalado)
        self._setup_dnd()

        # Scroll area
        outer = tk.Frame(self, bg=DARK); outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0, height=280)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self._canvas.pack(side="left", fill="both", expand=True)
        self._list_frame = tk.Frame(self._canvas, bg=DARK)
        self._win_id = self._canvas.create_window((0,0), window=self._list_frame, anchor="nw")
        self._list_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._win_id, width=e.width))
        self._canvas.bind_all("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Estatísticas
        stats = tk.Frame(self, bg=CARD, padx=12, pady=8); stats.pack(fill="x", pady=(8,0))
        stats.columnconfigure((0,1,2,3), weight=1)
        self._stat_total    = self._stat_cell(stats, 0, "Total",        "0", TEXT)
        self._stat_pending  = self._stat_cell(stats, 1, "Na fila",      "0", MUTED)
        self._stat_done     = self._stat_cell(stats, 2, "Concluídos",   "0", GREEN)
        self._stat_error    = self._stat_cell(stats, 3, "Com erro",     "0", RED)

    def _stat_cell(self, parent, col, label, value, color):
        frame = tk.Frame(parent, bg=CARD); frame.grid(row=0, column=col, sticky="ew", padx=4)
        val_lbl = tk.Label(frame, text=value, font=("Segoe UI",16,"bold"), bg=CARD, fg=color)
        val_lbl.pack(); tk.Label(frame, text=label, font=FONT_SMALL, bg=CARD, fg=MUTED).pack()
        return val_lbl

    def _setup_dnd(self):
        """Tenta configurar drag-and-drop via tkinterdnd2."""
        try:
            from tkinterdnd2 import DND_FILES
            self._drop_zone.drop_target_register(DND_FILES)
            self._drop_zone.dnd_bind("<<Drop>>", self._on_drop)
            self._drop_lbl.config(text="🎬  Arraste vídeos aqui  (ou clique em 'Adicionar vídeos')", fg=CYAN)
        except Exception:
            pass  # tkinterdnd2 não instalado — não é obrigatório

    def _on_drop(self, event):
        paths = event.data
        # tkinterdnd2 retorna paths entre {} em Windows
        import re
        files = re.findall(r'\{([^}]+)\}|(\S+)', paths)
        for match in files:
            path = match[0] or match[1]
            if path and os.path.isfile(path): self.add_video(path)

    def _browse_add(self):
        paths = filedialog.askopenfilenames(
            title="Selecionar vídeo(s)",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"), ("Todos","*.*")]
        )
        for p in paths: self.add_video(p)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Selecionar pasta com vídeos")
        if not folder: return
        VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".webm",".flv",".ts",".m4v"}
        added = 0
        for f in sorted(os.listdir(folder)):
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                self.add_video(os.path.join(folder, f)); added += 1
        if added == 0:
            messagebox.showinfo("Pasta vazia", "Nenhum vídeo encontrado na pasta selecionada.")

    def _clear_queue(self):
        running = [i for i in self._items if i.status == BatchQueueItem.STATUS_RUNNING]
        if running:
            messagebox.showwarning("Processamento em andamento", "Aguarde o processamento atual terminar."); return
        for item in list(self._items): item.destroy()
        self._items.clear(); self._update_stats()

    def add_video(self, path):
        # Evita duplicatas
        existing = [i.video_path for i in self._items]
        if path in existing: return
        item = BatchQueueItem(self._list_frame, video_path=path, on_remove=self._remove_item)
        item.pack(fill="x", padx=4, pady=(0,4))
        self._items.append(item); self._update_stats()
        # Esconde drop zone se há itens
        self._drop_zone.pack_forget()

    def _remove_item(self, item: BatchQueueItem):
        item.destroy(); self._items.remove(item); self._update_stats()
        if not self._items: self._drop_zone.pack(fill="x", pady=(0,8), before=self._canvas.master if hasattr(self._canvas, 'master') else None)

    def _update_stats(self):
        total   = len(self._items)
        pending = sum(1 for i in self._items if i.status in (BatchQueueItem.STATUS_PENDING,))
        done    = sum(1 for i in self._items if i.status == BatchQueueItem.STATUS_DONE)
        errors  = sum(1 for i in self._items if i.status == BatchQueueItem.STATUS_ERROR)
        self._count_lbl.config(text=f"{total} vídeo{'s' if total != 1 else ''}")
        self._stat_total.config(text=str(total))
        self._stat_pending.config(text=str(pending))
        self._stat_done.config(text=str(done))
        self._stat_error.config(text=str(errors), fg=RED if errors > 0 else MUTED)

    def get_pending_items(self):
        return [i for i in self._items if i.status in (BatchQueueItem.STATUS_PENDING, BatchQueueItem.STATUS_ERROR)]

    def get_all_items(self): return list(self._items)
    def has_videos(self):    return len(self._items) > 0
    def update_stats(self):  self._update_stats()


# ═══════════════════════════════════════════════════════════════════════════════
#   APP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class AudioFixApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AudioFix Pro — Batch Edition")
        self.geometry("900x1050")
        self.minsize(780, 860)
        self.configure(bg=DARK)
        self.resizable(True, True)

        # Estado
        self.running          = False
        self._batch_cancel    = False
        self._noise_controls: dict = {}
        self._dcb_widgets     = []
        self._audio_mode_widgets = []

        # Variáveis
        self.output_dir      = tk.StringVar()
        self.n_variants      = tk.IntVar(value=0)
        self.cw_path         = tk.StringVar()
        self.cw_enabled      = tk.BooleanVar(value=False)
        self.cw_gain         = tk.DoubleVar(value=0.40)
        self.dcb_enabled     = tk.BooleanVar(value=False)
        self.dcb_threshold   = tk.DoubleVar(value=0.50)
        self.dcb_ratio       = tk.DoubleVar(value=4.0)
        self.dcb_makeup      = tk.DoubleVar(value=1.80)
        self._mode           = tk.StringVar(value="audio")

        self._build_ui()
        if not _FFMPEG_OK:
            self.after(600, lambda: messagebox.showwarning("ffmpeg não encontrado", _ffmpeg_install_hint()))

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Cabeçalho ─────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, pady=16); hdr.pack(fill="x")
        tk.Label(hdr, text="AudioFix Pro", font=FONT_TITLE, bg=PANEL, fg=TEXT).pack()
        tk.Label(hdr, text="Processamento em lote · Inversão de fase · Ruídos coloridos · Copy White · DCB",
                 font=FONT_STATUS, bg=PANEL, fg=MUTED).pack(pady=(2,0))
        dep_frame = tk.Frame(hdr, bg=PANEL); dep_frame.pack(pady=(6,0))
        gtts_ok = _is_importable("gtts")
        for text, color in [
            ("ffmpeg ✔" if _FFMPEG_OK else "ffmpeg ✖", GREEN if _FFMPEG_OK else RED),
            ("  |  ",MUTED),("whisper ✔" if _WHISPER_OK else "whisper —", GREEN if _WHISPER_OK else MUTED),
            ("  |  ",MUTED),("gTTS ✔" if gtts_ok else "gTTS —", GREEN if gtts_ok else MUTED),
            ("  |  ",MUTED),(f"v{VERSAO_ATUAL}",MUTED),
        ]:
            tk.Label(dep_frame, text=text, font=FONT_SMALL, bg=PANEL, fg=color).pack(side="left")

        # ── Scroll wrapper ────────────────────────────────────────────────────
        outer = tk.Frame(self, bg=DARK); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        body_frame = tk.Frame(canvas, bg=DARK)
        body_win = canvas.create_window((0,0), window=body_frame, anchor="nw")
        body_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        body = tk.Frame(body_frame, bg=DARK, padx=24, pady=18); body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        row_idx = 0

        # ── MODO: um vídeo / lote ─────────────────────────────────────────────
        mode_outer = tk.Frame(body, bg=DARK, pady=5)
        mode_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,6)); row_idx += 1
        tk.Label(mode_outer, text="⚙️  Modo de entrada", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,6))
        mc = tk.Frame(mode_outer, bg=DARK); mc.pack(fill="x")
        mc.columnconfigure(0, weight=1); mc.columnconfigure(1, weight=1)
        self._btn_single_outer = tk.Frame(mc, bg=ACCENT, padx=2, pady=2)
        self._btn_single_outer.grid(row=0, column=0, sticky="nsew", padx=(0,4))
        self._btn_single_inner = tk.Frame(self._btn_single_outer, bg="#1a1830", padx=14, pady=12, cursor="hand2")
        self._btn_single_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_single_inner, text="🎬  Um vídeo", font=("Segoe UI",11,"bold"), bg="#1a1830", fg=ACC2).pack(anchor="w")
        tk.Label(self._btn_single_inner, text="Selecione um arquivo\ne defina a saída manualmente",
                 font=FONT_SMALL, bg="#1a1830", fg=MUTED, justify="left").pack(anchor="w", pady=(4,0))
        self._btn_batch_outer = tk.Frame(mc, bg=MUTED, padx=2, pady=2)
        self._btn_batch_outer.grid(row=0, column=1, sticky="nsew", padx=(4,0))
        self._btn_batch_inner = tk.Frame(self._btn_batch_outer, bg=CARD, padx=14, pady=12, cursor="hand2")
        self._btn_batch_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_batch_inner, text="📦  Vários vídeos (lote)", font=("Segoe UI",11,"bold"), bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self._btn_batch_inner, text="Adicione múltiplos arquivos\ne processe todos em sequência",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, justify="left").pack(anchor="w", pady=(4,0))
        for w in [self._btn_single_outer, self._btn_single_inner] + list(self._btn_single_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_input_mode("single"))
        for w in [self._btn_batch_outer, self._btn_batch_inner] + list(self._btn_batch_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_input_mode("batch"))

        # ── PAINEL ÚNICO ──────────────────────────────────────────────────────
        self._single_outer = tk.Frame(body, bg=DARK, pady=5)
        self._single_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        self._single_video  = tk.StringVar()
        self._single_output = tk.StringVar()
        self._file_row_widget(self._single_outer, 0, "🎬  Vídeo de entrada", self._single_video, self._browse_single_input, "Nenhum vídeo selecionado…")
        self._file_row_widget(self._single_outer, 1, "💾  Arquivo de saída", self._single_output, self._browse_single_output, "Onde salvar o vídeo processado…")
        self._single_outer.columnconfigure(0, weight=1)

        # ── PAINEL LOTE ───────────────────────────────────────────────────────
        self._batch_outer = tk.Frame(body, bg=DARK, pady=5)
        self._batch_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        self.batch_queue = BatchQueuePanel(self._batch_outer)
        self.batch_queue.pack(fill="both", expand=True)
        # Pasta de saída para lote
        out_dir_card = tk.Frame(self._batch_outer, bg=CARD, padx=14, pady=10); out_dir_card.pack(fill="x", pady=(8,0))
        out_dir_row = tk.Frame(out_dir_card, bg=CARD); out_dir_row.pack(fill="x")
        tk.Label(out_dir_row, text="📁  Pasta de saída (lote):", font=FONT_BOLD, bg=CARD, fg=MUTED, width=22, anchor="w").pack(side="left")
        tk.Entry(out_dir_row, textvariable=self.output_dir, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG,
                 insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(out_dir_row, text="Escolher pasta", font=FONT_LABEL, bg=ACCENT, fg="white",
                  relief="flat", padx=10, pady=2, cursor="hand2", command=self._browse_output_dir).pack(side="right")
        tk.Label(out_dir_card, text="  Deixe em branco para salvar na mesma pasta do vídeo com sufixo _audiofix",
                 font=FONT_SMALL, bg=CARD, fg=MUTED).pack(anchor="w", pady=(4,0))

        # ── Modo de processamento (áudio vs original) ─────────────────────────
        proc_outer = tk.Frame(body, bg=DARK, pady=5)
        proc_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(proc_outer, text="⚙️  Modo de processamento", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,6))
        pc = tk.Frame(proc_outer, bg=DARK); pc.pack(fill="x")
        pc.columnconfigure(0, weight=1); pc.columnconfigure(1, weight=1)
        self._proc_audio_outer = tk.Frame(pc, bg=ACCENT, padx=2, pady=2)
        self._proc_audio_outer.grid(row=0, column=0, sticky="nsew", padx=(0,4))
        self._proc_audio_inner = tk.Frame(self._proc_audio_outer, bg="#1a1830", padx=14, pady=12, cursor="hand2")
        self._proc_audio_inner.pack(fill="both", expand=True)
        tk.Label(self._proc_audio_inner, text="🎛️  Manipular Áudio", font=("Segoe UI",11,"bold"), bg="#1a1830", fg=ACC2).pack(anchor="w")
        tk.Label(self._proc_audio_inner, text="Inversão de fase · Ruídos · Copy White · DCB",
                 font=FONT_SMALL, bg="#1a1830", fg=MUTED, justify="left").pack(anchor="w", pady=(4,0))
        self._proc_orig_outer = tk.Frame(pc, bg=MUTED, padx=2, pady=2)
        self._proc_orig_outer.grid(row=0, column=1, sticky="nsew", padx=(4,0))
        self._proc_orig_inner = tk.Frame(self._proc_orig_outer, bg=CARD, padx=14, pady=12, cursor="hand2")
        self._proc_orig_inner.pack(fill="both", expand=True)
        tk.Label(self._proc_orig_inner, text="🎬  Áudio Original", font=("Segoe UI",11,"bold"), bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self._proc_orig_inner, text="Sem processamento · só variações de metadados",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, justify="left").pack(anchor="w", pady=(4,0))
        for w in [self._proc_audio_outer, self._proc_audio_inner] + list(self._proc_audio_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_proc_mode("audio"))
        for w in [self._proc_orig_outer, self._proc_orig_inner] + list(self._proc_orig_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_proc_mode("original"))

        # ── Ruídos ────────────────────────────────────────────────────────────
        noise_outer = tk.Frame(body, bg=DARK, pady=5)
        noise_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(noise_outer, text="🎨  Mistura de ruídos coloridos", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,6))
        noise_grid = tk.Frame(noise_outer, bg=DARK); noise_grid.pack(fill="x")
        noise_grid.columnconfigure(0, weight=1); noise_grid.columnconfigure(1, weight=1)
        defaults = {"Rosa":0.003,"Branco":0.0,"Marrom":0.0,"Azul":0.0,"Violeta":0.0,"Cinza":0.0}
        for idx, name in enumerate(NOISE_GENERATORS.keys()):
            ctrl = NoiseControl(noise_grid, name=name, color=NOISE_COLORS[name], default_amp=defaults.get(name,0.0))
            ctrl.grid(row=idx//2, column=idx%2, sticky="ew", padx=(0,4) if idx%2==0 else (4,0), pady=2)
            self._noise_controls[name] = ctrl
        self._audio_mode_widgets.append(noise_outer)

        # ── Copy White ────────────────────────────────────────────────────────
        cw_outer = tk.Frame(body, bg=DARK, pady=5)
        cw_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        cw_hdr = tk.Frame(cw_outer, bg=DARK); cw_hdr.pack(fill="x")
        tk.Checkbutton(cw_hdr, variable=self.cw_enabled, bg=DARK, activebackground=DARK, fg=CYAN,
                       selectcolor="#111116", relief="flat", bd=0, cursor="hand2",
                       command=self._toggle_cw).pack(side="left")
        tk.Label(cw_hdr, text="📻  Copy White — sobreposição de áudio externo", font=FONT_BOLD, bg=DARK, fg=CYAN).pack(side="left")
        self.cw_card = tk.Frame(cw_outer, bg=CARD, padx=14, pady=12); self.cw_card.pack(fill="x")
        file_row_cw = tk.Frame(self.cw_card, bg=CARD); file_row_cw.pack(fill="x", pady=(0,8))
        tk.Label(file_row_cw, text="Áudio WAV:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_entry = tk.Entry(file_row_cw, textvariable=self.cw_path, font=FONT_MONO,
                                 bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1)
        self.cw_entry.pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(file_row_cw, text="Escolher WAV", font=FONT_LABEL, bg=CYAN, fg=DARK,
                  relief="flat", padx=10, pady=2, cursor="hand2", command=self._browse_cw).pack(side="right")
        gain_row = tk.Frame(self.cw_card, bg=CARD); gain_row.pack(fill="x")
        tk.Label(gain_row, text="Ganho mix:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_gain_lbl = tk.Label(gain_row, text=f"{self.cw_gain.get():.2f}", font=FONT_BOLD, bg=CARD, fg=CYAN, width=5)
        self.cw_gain_lbl.pack(side="right")
        self.cw_slider = ttk.Scale(gain_row, from_=0.05, to=1.0, variable=self.cw_gain, orient="horizontal",
                                   command=lambda v: self.cw_gain_lbl.config(text=f"{float(v):.2f}"))
        self.cw_slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._toggle_cw()
        self._audio_mode_widgets.append(cw_outer)

        # ── DCB ───────────────────────────────────────────────────────────────
        dcb_outer = tk.Frame(body, bg=DARK, pady=5)
        dcb_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        dcb_hdr = tk.Frame(dcb_outer, bg=DARK); dcb_hdr.pack(fill="x")
        tk.Checkbutton(dcb_hdr, variable=self.dcb_enabled, bg=DARK, activebackground=DARK, fg=GOLD,
                       selectcolor="#111116", relief="flat", bd=0, cursor="hand2",
                       command=self._toggle_dcb).pack(side="left")
        tk.Label(dcb_hdr, text="🎚  DCB — Dynamic Compression Boost", font=FONT_BOLD, bg=DARK, fg=GOLD).pack(side="left")
        self.dcb_card = tk.Frame(dcb_outer, bg=CARD, padx=14, pady=12); self.dcb_card.pack(fill="x")
        dcb_ctrl = tk.Frame(self.dcb_card, bg=CARD); dcb_ctrl.pack(fill="x")
        self._dcb_slider_row(dcb_ctrl, "Threshold",   self.dcb_threshold, 0.10, 0.90, "{:.2f}",   GOLD)
        self._dcb_slider_row(dcb_ctrl, "Ratio",       self.dcb_ratio,     1.0,  10.0, "{:.1f}:1", GOLD)
        self._dcb_slider_row(dcb_ctrl, "Makeup Gain", self.dcb_makeup,    0.5,  3.0,  "{:.2f}×",  WARN)
        self._toggle_dcb()
        self._audio_mode_widgets.append(dcb_outer)

        # ── Variações ─────────────────────────────────────────────────────────
        var_outer = tk.Frame(body, bg=DARK, pady=5)
        var_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(var_outer, text="🎲  Variações de metadados", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        var_card = tk.Frame(var_outer, bg=CARD, padx=14, pady=12); var_card.pack(fill="x")
        spin_frame = tk.Frame(var_card, bg=CARD); spin_frame.pack(fill="x")
        self.var_minus_btn = tk.Button(spin_frame, text="  −  ", font=("Segoe UI",12,"bold"), bg="#2a1a1a", fg=RED,
                                       relief="flat", cursor="hand2", padx=6, pady=4, command=self._decrement_variants)
        self.var_minus_btn.pack(side="left")
        self.var_display = tk.Label(spin_frame, text="0", font=("Segoe UI",14,"bold"), bg=CARD, fg=TEXT, width=4, anchor="center")
        self.var_display.pack(side="left", padx=4)
        self.var_plus_btn = tk.Button(spin_frame, text="  +  ", font=("Segoe UI",12,"bold"), bg="#1a2a1a", fg=GREEN,
                                      relief="flat", cursor="hand2", padx=6, pady=4, command=self._increment_variants)
        self.var_plus_btn.pack(side="left")
        self.var_hint = tk.Label(spin_frame, text="sem variações", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self.var_hint.pack(side="left", padx=(10,0))
        self.n_variants.trace_add("write", lambda *_: self._sync_var_display())
        tk.Frame(var_card, bg=MUTED, height=1).pack(fill="x", pady=(10,8))
        self.variation_level_selector = VariationLevelSelector(var_card)
        self.variation_level_selector.pack(fill="x")

        # ── Progresso global ──────────────────────────────────────────────────
        prog_outer = tk.Frame(body, bg=DARK, pady=5)
        prog_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(prog_outer, text="⚙️  Progresso global", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        prog_card = tk.Frame(prog_outer, bg=CARD, padx=14, pady=10); prog_card.pack(fill="x")
        self.global_progress = ttk.Progressbar(prog_card, mode="determinate", maximum=100, length=400)
        self.global_progress.pack(fill="x")
        self.global_status = tk.Label(prog_card, text="Aguardando…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self.global_status.pack(anchor="w", pady=(4,0))

        # ── Log ───────────────────────────────────────────────────────────────
        log_outer = tk.Frame(body, bg=DARK, pady=5)
        log_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(log_outer, text="📋  Log de processamento", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        log_card = tk.Frame(log_outer, bg=CARD, padx=14, pady=10); log_card.pack(fill="both", expand=True)
        log_inner = tk.Frame(log_card, bg=CARD); log_inner.pack(fill="both", expand=True)
        log_inner.rowconfigure(0, weight=1); log_inner.columnconfigure(0, weight=1)
        self.log_box = tk.Text(log_inner, height=8, font=FONT_MONO, bg="#111116", fg="#a0a0b8",
                               insertbackground=TEXT, relief="flat", state="disabled", wrap="word")
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(log_inner, command=self.log_box.yview); sb2.grid(row=0, column=1, sticky="ns")
        self.log_box.config(yscrollcommand=sb2.set)

        # ── Botões de ação ─────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=DARK, pady=14); btn_frame.pack(fill="x", padx=24)
        self.run_btn = tk.Button(btn_frame, text="▶  PROCESSAR", font=("Segoe UI",11,"bold"),
                                 bg=ACCENT, fg="white", activebackground=ACC2, activeforeground="white",
                                 relief="flat", padx=28, pady=10, cursor="hand2", command=self._start_processing)
        self.run_btn.pack(side="right")
        self.cancel_btn = tk.Button(btn_frame, text="⏹  Cancelar lote", font=("Segoe UI",11,"bold"),
                                    bg="#2a1a1a", fg=RED, relief="flat", padx=18, pady=10, cursor="hand2",
                                    state="disabled", command=self._cancel_batch)
        self.cancel_btn.pack(side="right", padx=(0,8))
        tk.Button(btn_frame, text="🗑  Limpar log", font=FONT_LABEL, bg=CARD, fg=MUTED,
                  relief="flat", padx=14, pady=10, cursor="hand2", command=self._clear_log).pack(side="right", padx=(0,8))

        # Estilos
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, thickness=10, bordercolor=DARK, lightcolor=ACCENT)
        style.configure("Vertical.TScrollbar",     troughcolor="#111116", background=MUTED, arrowcolor=MUTED, bordercolor=DARK)
        style.configure("TScale", background=CARD, troughcolor=PANEL, sliderthickness=16)

        # Estado inicial
        self._input_mode = "single"
        self._proc_mode  = "audio"
        self._set_input_mode("single")
        self._set_proc_mode("audio")

    # ── Helpers de UI ─────────────────────────────────────────────────────────

    def _file_row_widget(self, parent, grid_row, label, var, cmd, placeholder):
        outer = tk.Frame(parent, bg=DARK, pady=3)
        outer.grid(row=grid_row, column=0, sticky="ew", pady=(0,4))
        tk.Label(outer, text=label, font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        card = tk.Frame(outer, bg=CARD, padx=14, pady=10); card.pack(fill="x")
        entry = tk.Entry(card, textvariable=var, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG,
                         insertbackground="black", relief="flat", bd=1)
        entry.pack(side="left", fill="x", expand=True)
        tk.Button(card, text="Escolher", font=FONT_LABEL, bg=ACCENT, fg="white",
                  activebackground=ACC2, relief="flat", padx=10, pady=2, cursor="hand2",
                  command=cmd).pack(side="right", padx=(8,0))

    def _dcb_slider_row(self, parent, label, var, from_, to, fmt, color):
        row = tk.Frame(parent, bg=CARD, pady=3); row.pack(fill="x")
        tk.Label(row, text=label, font=FONT_BOLD, bg=CARD, fg=MUTED, width=14, anchor="w").pack(side="left")
        val_lbl = tk.Label(row, text=fmt.format(var.get()), font=FONT_BOLD, bg=CARD, fg=color, width=8)
        val_lbl.pack(side="right")
        slider = ttk.Scale(row, from_=from_, to=to, variable=var, orient="horizontal",
                           command=lambda v, lbl=val_lbl, f=fmt: lbl.config(text=f.format(float(v))))
        slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._dcb_widgets.append(slider)

    # ── Modos ─────────────────────────────────────────────────────────────────

    def _set_input_mode(self, mode):
        self._input_mode = mode
        if mode == "single":
            self._btn_single_outer.config(bg=ACCENT); self._btn_single_inner.config(bg="#1a1830")
            for w in self._btn_single_inner.winfo_children(): 
                try: w.config(bg="#1a1830")
                except: pass
            self._btn_batch_outer.config(bg=MUTED); self._btn_batch_inner.config(bg=CARD)
            for w in self._btn_batch_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
            self._single_outer.grid(); self._batch_outer.grid_remove()
        else:
            self._btn_batch_outer.config(bg=ACCENT); self._btn_batch_inner.config(bg="#1a1830")
            for w in self._btn_batch_inner.winfo_children():
                try: w.config(bg="#1a1830")
                except: pass
            self._btn_single_outer.config(bg=MUTED); self._btn_single_inner.config(bg=CARD)
            for w in self._btn_single_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
            self._single_outer.grid_remove(); self._batch_outer.grid()

    def _set_proc_mode(self, mode):
        self._proc_mode = mode
        if mode == "audio":
            self._proc_audio_outer.config(bg=ACCENT); self._proc_audio_inner.config(bg="#1a1830")
            for w in self._proc_audio_inner.winfo_children():
                try: w.config(bg="#1a1830")
                except: pass
            self._proc_orig_outer.config(bg=MUTED); self._proc_orig_inner.config(bg=CARD)
            for w in self._proc_orig_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
            for w in self._audio_mode_widgets: w.grid()
        else:
            self._proc_orig_outer.config(bg=GREEN); self._proc_orig_inner.config(bg="#0d1a12")
            for w in self._proc_orig_inner.winfo_children():
                try: w.config(bg="#0d1a12")
                except: pass
            self._proc_audio_outer.config(bg=MUTED); self._proc_audio_inner.config(bg=CARD)
            for w in self._proc_audio_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
            for w in self._audio_mode_widgets: w.grid_remove()

    # ── Browse handlers ───────────────────────────────────────────────────────

    def _browse_single_input(self):
        path = filedialog.askopenfilename(title="Selecionar vídeo",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("Todos","*.*")])
        if path:
            self._single_video.set(path)
            base, _ = os.path.splitext(path)
            self._single_output.set(base + "_audiofix.mp4")
            self._log(f"📂 Vídeo: {path}")

    def _browse_single_output(self):
        path = filedialog.asksaveasfilename(title="Salvar como…", defaultextension=".mp4",
            filetypes=[("MP4","*.mp4"),("MKV","*.mkv"),("Todos","*.*")])
        if path: self._single_output.set(path)

    def _browse_output_dir(self):
        folder = filedialog.askdirectory(title="Pasta de saída para o lote")
        if folder: self.output_dir.set(folder)

    def _browse_cw(self):
        path = filedialog.askopenfilename(title="Selecionar WAV", filetypes=[("WAV","*.wav"),("Todos","*.*")])
        if path: self.cw_path.set(path); self._log(f"📻 Copy White: {path}")

    def _toggle_cw(self):
        state = "normal" if self.cw_enabled.get() else "disabled"
        self.cw_entry.config(state=state); self.cw_slider.config(state=state)

    def _toggle_dcb(self):
        state = "normal" if self.dcb_enabled.get() else "disabled"
        for w in self._dcb_widgets: w.config(state=state)

    # ── Variantes ─────────────────────────────────────────────────────────────

    def _increment_variants(self):
        if self.n_variants.get() < 50: self.n_variants.set(self.n_variants.get() + 1)

    def _decrement_variants(self):
        if self.n_variants.get() > 0: self.n_variants.set(self.n_variants.get() - 1)

    def _sync_var_display(self):
        n = self.n_variants.get(); self.var_display.config(text=str(n))
        self.var_hint.config(text="sem variações" if n == 0 else f"+ {n} variação(ões)", fg=MUTED if n == 0 else WARN)
        self.var_minus_btn.config(state="normal" if n > 0 else "disabled", fg=RED if n > 0 else MUTED)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, msg):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg+"\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self.log_box.config(state="normal"); self.log_box.delete("1.0","end"); self.log_box.config(state="disabled")

    def _set_global_status(self, msg, color=None, pct=None):
        def _do():
            self.global_status.config(text=msg, fg=color or TEXT)
            if pct is not None: self.global_progress.config(value=pct)
        self.after(0, _do)

    # ── Processar ─────────────────────────────────────────────────────────────

    def _get_noise_amplitudes(self):
        return {name: ctrl.amplitude for name, ctrl in self._noise_controls.items()}

    def _build_output_path(self, video_path):
        base, ext = os.path.splitext(video_path)
        out_dir = self.output_dir.get().strip()
        if out_dir and os.path.isdir(out_dir):
            name = os.path.basename(base) + "_audiofix" + (ext or ".mp4")
            return os.path.join(out_dir, name)
        return base + "_audiofix" + (ext or ".mp4")

    def _start_processing(self):
        if self.running: return
        if not _FFMPEG_OK:
            messagebox.showerror("ffmpeg não encontrado", _ffmpeg_install_hint()); return

        if self._input_mode == "single":
            self._process_single()
        else:
            self._process_batch()

    def _process_single(self):
        vin  = self._single_video.get().strip()
        vout = self._single_output.get().strip()
        if not vin or not os.path.isfile(vin):
            messagebox.showerror("Erro", "Selecione um vídeo de entrada válido."); return
        if not vout:
            messagebox.showerror("Erro", "Defina o arquivo de saída."); return

        n     = self.n_variants.get()
        level = self.variation_level_selector.level
        noise = self._get_noise_amplitudes()
        cw_path  = None; cw_gain = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path = self.cw_path.get().strip()
            if not cw_path or not os.path.isfile(cw_path):
                messagebox.showerror("Erro","Copy White ativo mas sem WAV válido."); return

        self.running = True; self._batch_cancel = False
        self.run_btn.config(state="disabled", text="⏳  Processando…", bg=MUTED)
        self.cancel_btn.config(state="normal")
        self.global_progress.config(value=0)
        self._set_global_status("Iniciando processamento…", TEXT, 0)
        self._clear_log()

        def progress_cb(pct): self._set_global_status(f"Processando… {pct}%", TEXT, pct)

        def worker():
            try:
                if self._proc_mode == "audio":
                    full_pipeline_audio(vin, vout, noise_amplitudes=noise,
                                        copy_white_path=cw_path, copy_white_gain=cw_gain,
                                        dcb_enabled=self.dcb_enabled.get(),
                                        dcb_threshold=self.dcb_threshold.get(),
                                        dcb_ratio=self.dcb_ratio.get(),
                                        dcb_makeup=self.dcb_makeup.get(),
                                        n_variants=n, variation_level=level,
                                        progress_cb=progress_cb, log_cb=self._log)
                else:
                    full_pipeline_original(vin, vout, n_variants=n, variation_level=level,
                                           progress_cb=progress_cb, log_cb=self._log)
                self._set_global_status(f"✅ Concluído! → {os.path.basename(vout)}", GREEN, 100)
                self.after(0, lambda: messagebox.showinfo("Concluído!", f"{1+n} arquivo(s).\n→ {vout}"))
            except Exception as e:
                self._set_global_status(f"❌ {e}", RED, 0); self._log(f"❌ ERRO: {e}")
                self.after(0, lambda: messagebox.showerror("Erro", str(e)))
            finally:
                self.running = False
                self.after(0, lambda: self.run_btn.config(state="normal", text="▶  PROCESSAR", bg=ACCENT))
                self.after(0, lambda: self.cancel_btn.config(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def _process_batch(self):
        items = self.batch_queue.get_pending_items()
        if not items:
            messagebox.showinfo("Fila vazia", "Adicione vídeos à fila antes de processar."); return

        n     = self.n_variants.get()
        level = self.variation_level_selector.level
        noise = self._get_noise_amplitudes()
        cw_path  = None; cw_gain = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path = self.cw_path.get().strip()
            if not cw_path or not os.path.isfile(cw_path):
                messagebox.showerror("Erro","Copy White ativo mas sem WAV válido."); return

        self.running = True; self._batch_cancel = False
        self.run_btn.config(state="disabled", text="⏳  Processando lote…", bg=MUTED)
        self.cancel_btn.config(state="normal")
        self.global_progress.config(value=0)
        self._clear_log()
        total = len(items)
        self._set_global_status(f"Lote iniciado: {total} vídeo(s)…", TEXT, 0)

        def worker():
            done = 0; errors = 0
            for idx, item in enumerate(items):
                if self._batch_cancel:
                    item.set_status(BatchQueueItem.STATUS_CANCELLED, "Cancelado pelo usuário")
                    for remaining in items[idx:]:
                        if remaining.status == BatchQueueItem.STATUS_PENDING:
                            remaining.set_status(BatchQueueItem.STATUS_CANCELLED, "Cancelado")
                    break

                vout = self._build_output_path(item.video_path)
                item.set_output(vout)

                def item_progress(pct, _item=item, _idx=idx, _total=total):
                    _item.set_status(BatchQueueItem.STATUS_RUNNING, f"Processando… {pct}%", pct)
                    global_pct = int((_idx / _total) * 100 + (pct / _total))
                    self._set_global_status(f"[{_idx+1}/{_total}] {os.path.basename(_item.video_path)}  {pct}%", TEXT, global_pct)

                def item_log(msg, _item=item):
                    self._log(f"[{os.path.basename(_item.video_path)}] {msg}")

                item.set_status(BatchQueueItem.STATUS_RUNNING, "Iniciando…", -1)
                try:
                    if self._proc_mode == "audio":
                        full_pipeline_audio(item.video_path, vout, noise_amplitudes=noise,
                                            copy_white_path=cw_path, copy_white_gain=cw_gain,
                                            dcb_enabled=self.dcb_enabled.get(),
                                            dcb_threshold=self.dcb_threshold.get(),
                                            dcb_ratio=self.dcb_ratio.get(),
                                            dcb_makeup=self.dcb_makeup.get(),
                                            n_variants=n, variation_level=level,
                                            progress_cb=item_progress, log_cb=item_log)
                    else:
                        full_pipeline_original(item.video_path, vout, n_variants=n, variation_level=level,
                                               progress_cb=item_progress, log_cb=item_log)
                    item.set_status(BatchQueueItem.STATUS_DONE, f"✅ Pronto → {os.path.basename(vout)}", 100)
                    done += 1
                except Exception as e:
                    item.set_error(str(e))
                    item.set_status(BatchQueueItem.STATUS_ERROR, f"❌ {str(e)[:80]}", 0)
                    errors += 1
                    self._log(f"❌ ERRO [{os.path.basename(item.video_path)}]: {e}")

                self.after(0, self.batch_queue.update_stats)

            self.running = False
            summary = f"✅ Lote concluído: {done}/{total} OK" + (f"  ·  {errors} erro(s)" if errors else "")
            self._set_global_status(summary, GREEN if errors == 0 else WARN, 100)
            self._log(f"\n{'='*50}\n{summary}\n{'='*50}")
            self.after(0, lambda: self.run_btn.config(state="normal", text="▶  PROCESSAR", bg=ACCENT))
            self.after(0, lambda: self.cancel_btn.config(state="disabled"))
            if not self._batch_cancel:
                self.after(0, lambda: messagebox.showinfo("Lote concluído",
                    f"{done} de {total} vídeos processados com sucesso." +
                    (f"\n\n{errors} erro(s) — clique em 'Processar' para reprocessar os com erro." if errors else "")))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_batch(self):
        if not self.running: return
        if messagebox.askyesno("Cancelar lote?", "Deseja cancelar o processamento em lote?\n\nO vídeo atual será finalizado antes de parar."):
            self._batch_cancel = True
            self._set_global_status("⚠️  Cancelamento solicitado…", WARN)
            self.cancel_btn.config(state="disabled", text="Cancelando…")


# ═══════════════════════════════════════════════════════════════════════════════
#   SPLASH SCREEN
# ═══════════════════════════════════════════════════════════════════════════════

_DARK_S   = "#0d0d0f"
_PANEL_S  = "#16161a"
_CARD_S   = "#1e1e24"
_ACCENT_S = "#7c6af7"
_ACC2_S   = "#a89cf7"
_TEXT_S   = "#e8e8f0"
_MUTED_S  = "#6b6b80"
_TEAL_S   = "#14b8a6"

class SplashScreen(tk.Tk):
    WIDTH = 520; HEIGHT = 340
    def __init__(self):
        super().__init__()
        self.overrideredirect(True); self.configure(bg=_DARK_S)
        self.attributes("-topmost", True); self.resizable(False, False)
        try: self.attributes("-alpha", 0.0)
        except: pass
        self._center(); self._pct = 0.0; self._done = False; self._angle = 0.0
        self._build(); self._fade_in()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2; y = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _build(self):
        self.canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT, bg=_DARK_S, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        steps = 18
        for i in range(steps):
            t = i/steps; r_c = int(0x0d+(0x16-0x0d)*t); g_c = r_c; b_c = int(0x0f+(0x1a-0x0f)*t)
            self.canvas.create_rectangle(0, int(i*self.HEIGHT/steps), self.WIDTH, int((i+1)*self.HEIGHT/steps), fill=f"#{r_c:02x}{g_c:02x}{b_c:02x}", outline="")
        cx, cy = self.WIDTH//2, 110; r = 44
        self._ring_id = self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=300, outline=_ACCENT_S, width=5, style="arc")
        self._ring2_id = self.canvas.create_arc(cx-r+4, cy-r+4, cx+r-4, cy+r-4, start=60, extent=200, outline=_ACC2_S, width=2, style="arc")
        self.canvas.create_text(cx, cy, text="🎛️", font=("Segoe UI Emoji", 24), fill=_TEXT_S, anchor="center")
        self.canvas.create_text(self.WIDTH//2, 170, text="AudioFix Pro — Batch Edition", font=("Segoe UI",18,"bold"), fill=_TEXT_S, anchor="center")
        self.canvas.create_text(self.WIDTH//2, 193, text="Processamento em lote · v" + VERSAO_ATUAL, font=("Segoe UI",9), fill=_MUTED_S, anchor="center")
        bar_x1, bar_y1, bar_x2, bar_y2 = 60, 218, self.WIDTH-60, 232
        self.canvas.create_rectangle(bar_x1, bar_y1, bar_x2, bar_y2, fill=_PANEL_S, outline=_CARD_S, width=1)
        self._bar_x1 = bar_x1; self._bar_y1 = bar_y1; self._bar_x2 = bar_x2; self._bar_y2 = bar_y2; self._bar_w = bar_x2-bar_x1
        self._bar_fill  = self.canvas.create_rectangle(bar_x1, bar_y1, bar_x1, bar_y2, fill=_ACCENT_S, outline="")
        self._pct_text  = self.canvas.create_text(self.WIDTH//2, 244, text="0%", font=("Segoe UI",9,"bold"), fill=_ACCENT_S, anchor="center")
        self._step_text = self.canvas.create_text(self.WIDTH//2, 262, text="Iniciando…", font=("Segoe UI",9), fill=_MUTED_S, anchor="center")
        self.canvas.create_text(self.WIDTH//2, self.HEIGHT-12, text=f"Python + ffmpeg  ·  v{VERSAO_ATUAL}  ·  © 2025 AudioFix", font=("Segoe UI",8), fill=_MUTED_S, anchor="center")
        self.canvas.create_rectangle(0, 0, self.WIDTH, 3, fill=_ACCENT_S, outline="")
        self.canvas.create_rectangle(0, self.HEIGHT-3, self.WIDTH, self.HEIGHT, fill=_TEAL_S, outline="")

    def _fade_in(self, alpha=0.0):
        try: self.attributes("-alpha", alpha)
        except: pass
        if alpha < 1.0: self.after(16, lambda: self._fade_in(min(alpha+0.07, 1.0)))
        else: self._animate_ring()

    def _animate_ring(self):
        if self._done: return
        self._angle = (self._angle + 4) % 360
        try:
            self.canvas.itemconfig(self._ring_id,  start=self._angle)
            self.canvas.itemconfig(self._ring2_id, start=(self._angle+60)%360)
        except: pass
        self.after(18, self._animate_ring)

    def update_progress(self, pct, label=""):
        fill_w = int(self._bar_w * pct / 100)
        try:
            self.canvas.coords(self._bar_fill, self._bar_x1, self._bar_y1, self._bar_x1+fill_w, self._bar_y2)
            self.canvas.itemconfig(self._pct_text, text=f"{int(pct)}%")
            if label: self.canvas.itemconfig(self._step_text, text=label)
        except: pass

    def finish(self, callback):
        self._done = True; self._fade_out(1.0, callback)

    def _fade_out(self, alpha, callback):
        try: self.attributes("-alpha", alpha)
        except: pass
        if alpha > 0.0: self.after(16, lambda: self._fade_out(max(alpha-0.08, 0.0), callback))
        else: self.destroy(); callback()


def _run_loading(splash: SplashScreen):
    def step(pct, label, delay=0.0):
        splash.after(0, lambda: splash.update_progress(pct, label))
        if delay: time.sleep(delay)

    step(0,  "Iniciando AudioFix Pro…",   0.2)
    step(15, "Verificando Python 3.8+…",  0.1)
    if sys.version_info < (3,8): sys.exit(1)
    step(30, "Carregando numpy / scipy…", 0.1)
    _ensure_packages()
    step(50, "Verificando ffmpeg…",       0.15)
    global _FFMPEG_OK, _GTTS_OK, _WHISPER_OK
    _FFMPEG_OK  = _check_ffmpeg()
    step(65, "Verificando gTTS…",         0.1)
    _GTTS_OK    = _check_gtts_silent()
    step(78, "Verificando Whisper…",      0.1)
    _WHISPER_OK = _check_whisper_silent()
    step(88, "Construindo interface…",    0.2)
    import numpy; from scipy.io import wavfile  # noqa: força import
    step(95, "Finalizando…",              0.15)
    step(100,"Pronto!",                   0.35)
    splash.after(0, lambda: splash.finish(_launch_main))

def _launch_main():
    app = AudioFixApp()
    app.mainloop()


if __name__ == "__main__":
    splash = SplashScreen()
    threading.Thread(target=_run_loading, args=(splash,), daemon=True).start()
    splash.mainloop()
