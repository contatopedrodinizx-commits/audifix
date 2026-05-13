#!/usr/bin/env python3
"""
AudioFix Pro v5.0 — Interface compacta com painéis colapsáveis
==============================================================
Todas as funcionalidades da v4.4, com UI reformulada:
  • Janela menor (680×780)
  • Seções colapsáveis (Accordion) com animação
  • Header fixo com status e modo
  • Footer fixo com botões de ação
  • Scroll apenas no conteúdo central

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
import webbrowser

# ─── Versão e URLs ────────────────────────────────────────────────────────────
VERSAO_ATUAL = "5.0"
GITHUB_REPO  = "contatopedrodinizx-commits/audifix"
URL_API      = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
URL_DOWNLOAD = f"https://github.com/{GITHUB_REPO}/releases/latest"

# ─── Ocultar console Windows ──────────────────────────────────────────────────
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

# ─── Deps silenciosas ─────────────────────────────────────────────────────────
def _pip_install(*packages):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0, r.stderr
    except Exception as e:
        return False, str(e)

def _is_importable(mod):
    try:
        importlib.import_module(mod)
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
    except Exception:
        return False

def _ffmpeg_install_hint():
    s = platform.system()
    if s == "Windows":
        return "ffmpeg não encontrado.\n\nComo instalar:\n  • winget install ffmpeg\n  • https://www.gyan.dev/ffmpeg/builds/\n\nReinicie após instalar."
    elif s == "Darwin":
        return "ffmpeg não encontrado.\n\nbrew install ffmpeg"
    else:
        return "ffmpeg não encontrado.\n\n  Ubuntu/Debian:  sudo apt install ffmpeg\n  Fedora:         sudo dnf install ffmpeg\n  Arch:           sudo pacman -S ffmpeg"

_ensure_packages()
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

_FFMPEG_OK  = _check_ffmpeg()
_GTTS_OK    = _is_importable("gtts")
_WHISPER_OK = _is_importable("faster_whisper") or _is_importable("whisper")

# ─── Paleta ───────────────────────────────────────────────────────────────────
DARK   = "#0d0d0f"
PANEL  = "#16161a"
CARD   = "#1e1e24"
CARD2  = "#23232c"
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
NOISE_DESCRIPTIONS = {
    "Rosa":    "1/f · natural",   "Branco": "uniforme",
    "Marrom":  "1/f² · grave",    "Azul":   "f · agudos",
    "Violeta": "f² · muito agudo","Cinza":  "psicoacústico",
}

FONT_UI    = ("Segoe UI", 9)
FONT_BOLD  = ("Segoe UI", 9, "bold")
FONT_MONO  = ("Consolas", 8)
FONT_SMALL = ("Segoe UI", 8)
FONT_H2    = ("Segoe UI", 11, "bold")
INPUT_BG   = "#f0f0f5"
INPUT_FG   = "black"

# ─── Geradores de ruído ───────────────────────────────────────────────────────
def generate_pink_noise(n, amp, seed=42):
    rng = np.random.default_rng(seed)
    rows = 16; pink = np.zeros(n); rs = rng.random(rows); total = rs.sum()
    for i in range(n):
        k = int(np.log2((i & -i)+1)) % rows if i > 0 else 0
        old = rs[k]; rs[k] = rng.random(); total += rs[k]-old; pink[i] = total
    pink -= pink.mean(); mx = np.abs(pink).max()
    return (pink/mx*amp if mx>0 else pink).astype(np.float64)

def generate_white_noise(n, amp, seed=43):
    rng = np.random.default_rng(seed); w = rng.standard_normal(n)
    mx = np.abs(w).max(); return (w/mx*amp if mx>0 else w).astype(np.float64)

def generate_brown_noise(n, amp, seed=44):
    rng = np.random.default_rng(seed); b = np.cumsum(rng.standard_normal(n)); b -= b.mean()
    mx = np.abs(b).max(); return (b/mx*amp if mx>0 else b).astype(np.float64)

def generate_blue_noise(n, amp, seed=45):
    rng = np.random.default_rng(seed); w = rng.standard_normal(n); b = np.diff(w, prepend=w[0])
    b -= b.mean(); mx = np.abs(b).max(); return (b/mx*amp if mx>0 else b).astype(np.float64)

def generate_violet_noise(n, amp, seed=46):
    rng = np.random.default_rng(seed); w = rng.standard_normal(n)
    v = np.diff(np.diff(w, prepend=w[0]), prepend=w[0]); v -= v.mean()
    mx = np.abs(v).max(); return (v/mx*amp if mx>0 else v).astype(np.float64)

def generate_grey_noise(n, amp, seed=47):
    rng = np.random.default_rng(seed); w = rng.standard_normal(n); fft = np.fft.rfft(w)
    f = np.maximum(np.abs(np.fft.rfftfreq(n))*44100, 1e-6)
    wt = (f/1000)**0.3/(1+(f/6000)**2+(1/(f/120+1e-6))**1.5)
    wt = np.maximum(wt,1e-6)/wt.max(); g = np.fft.irfft(fft*wt, n=n); g -= g.mean()
    mx = np.abs(g).max(); return (g/mx*amp if mx>0 else g).astype(np.float64)

NOISE_GENERATORS = {
    "Rosa": generate_pink_noise, "Branco": generate_white_noise,
    "Marrom": generate_brown_noise, "Azul": generate_blue_noise,
    "Violeta": generate_violet_noise, "Cinza": generate_grey_noise,
}

# ─── Metadados ────────────────────────────────────────────────────────────────
VARIATION_LEVELS = {
    "Normal":   {"label":"Normal",   "color":GREEN,  "title_len":4,"artist_len":4,"album_len":3,"comment_len":6, "date_range":30,   "track_range":(1,20),  "encoder_var":False},
    "Moderada": {"label":"Moderada", "color":WARN,   "title_len":6,"artist_len":5,"album_len":4,"comment_len":9, "date_range":365,  "track_range":(1,50),  "encoder_var":True},
    "Intensa":  {"label":"Intensa",  "color":ORANGE, "title_len":8,"artist_len":7,"album_len":6,"comment_len":12,"date_range":1095, "track_range":(1,99),  "encoder_var":True},
    "Brusca":   {"label":"Brusca",   "color":RED,    "title_len":12,"artist_len":10,"album_len":9,"comment_len":18,"date_range":3650,"track_range":(1,999), "encoder_var":True},
}

def _rand_str(n=8):
    return ''.join(random.choices(string.ascii_letters+string.digits, k=n))

def _rand_date(days=365):
    today = datetime.date.today(); start = today - datetime.timedelta(days=days)
    return str(start + datetime.timedelta(days=random.randint(0,(today-start).days)))

def generate_metadata_variants(n, level="Normal"):
    cfg = VARIATION_LEVELS.get(level, VARIATION_LEVELS["Normal"]); result = []
    for _ in range(n):
        m = {"title":f"Video_{_rand_str(cfg['title_len'])}","artist":f"Creator_{_rand_str(cfg['artist_len'])}",
             "album":f"Collection_{_rand_str(cfg['album_len'])}","comment":f"Processed_{_rand_str(cfg['comment_len'])}",
             "date":_rand_date(cfg['date_range']),"track":str(random.randint(*cfg['track_range']))}
        if cfg["encoder_var"]: m["encoder"] = f"Encoder_{_rand_str(4)}_{random.randint(1,99)}"
        result.append(m)
    return result

# ─── Audio processing ─────────────────────────────────────────────────────────
def load_and_resample_wav(path, target_sr=44100):
    from math import gcd
    sr, data = wavfile.read(path)
    if data.dtype == np.int16: data = data.astype(np.float64)/32768.
    elif data.dtype == np.int32: data = data.astype(np.float64)/2147483648.
    elif data.dtype == np.uint8: data = (data.astype(np.float64)-128.)/128.
    else: data = data.astype(np.float64)
    if data.ndim == 1: data = np.stack([data,data],axis=1)
    elif data.shape[1]==1: data = np.concatenate([data,data],axis=1)
    elif data.shape[1]>2: data = data[:,:2]
    if sr != target_sr:
        g = gcd(sr, target_sr); up,down = target_sr//g, sr//g
        data = np.stack([resample_poly(data[:,0],up,down),resample_poly(data[:,1],up,down)],axis=1)
    return data, target_sr

def apply_dcb(data, threshold=0.5, ratio=4.0, makeup=1.8):
    out = data.copy(); mask = np.abs(out)>threshold
    out[mask] = np.sign(out[mask])*(threshold+(np.abs(out[mask])-threshold)/ratio)
    return np.clip(out*makeup,-1.,1.)

def process_audio(input_wav, output_wav, noise_amps=None, cw_path=None, cw_gain=0.5,
                  dcb=False, dcb_thr=0.5, dcb_ratio=4., dcb_mk=1.8, sr=44100):
    from math import gcd
    if noise_amps is None: noise_amps = {}
    sr0, data = wavfile.read(input_wav)
    if data.dtype==np.int16: data=data.astype(np.float64)/32768.
    elif data.dtype==np.int32: data=data.astype(np.float64)/2147483648.
    elif data.dtype==np.uint8: data=(data.astype(np.float64)-128.)/128.
    else: data=data.astype(np.float64)
    if data.ndim==1: data=np.stack([data,data],axis=1)
    elif data.shape[1]==1: data=np.concatenate([data,data],axis=1)
    elif data.shape[1]>2: data=data[:,:2]
    if sr0!=sr:
        g=gcd(sr0,sr); up,down=sr//g,sr0//g
        data=np.stack([resample_poly(data[:,0],up,down),resample_poly(data[:,1],up,down)],axis=1)
    n=len(data); left=data[:,0].copy(); right=-data[:,0].copy()
    for idx,(name,amp) in enumerate(noise_amps.items()):
        if amp<=0: continue
        gen=NOISE_GENERATORS.get(name)
        if gen: noise=gen(n,amp,seed=42+idx); left+=noise; right+=noise
    if cw_path and os.path.isfile(cw_path):
        cw,_=load_and_resample_wav(cw_path,sr)
        m=len(cw)
        if m<n: cw=np.tile(cw,(int(np.ceil(n/m)),1))
        cw=cw[:n]; left+=cw[:,0]*cw_gain; right+=cw[:,1]*cw_gain
    left=np.clip(left,-1.,1.); right=np.clip(right,-1.,1.)
    if dcb:
        st=apply_dcb(np.stack([left,right],axis=1),dcb_thr,dcb_ratio,dcb_mk)
        left,right=st[:,0],st[:,1]
    wavfile.write(output_wav,sr,np.stack([left,right],axis=1).astype(np.float32))

def _run(cmd, log=None):
    kw = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if platform.system()=="Windows": kw["creationflags"]=subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **kw)
    for line in proc.stdout:
        if log: log(line.rstrip())
    proc.wait()
    if proc.returncode!=0: raise RuntimeError(f"Cmd falhou ({proc.returncode}): {' '.join(cmd)}")

def extract_audio(vin, wav, log=None):
    _run(["ffmpeg","-y","-i",vin,"-vn","-acodec","pcm_f32le","-ar","44100",wav],log)

def extract_audio_16k(vin, wav, log=None):
    _run(["ffmpeg","-y","-i",vin,"-vn","-acodec","pcm_s16le","-ar","16000","-ac","1",wav],log)

def wav_to_mp3(wav, mp3, log=None):
    _run(["ffmpeg","-y","-i",wav,"-acodec","libmp3lame","-b:a","192k","-ar","44100","-ac","2",mp3],log)

def merge_av(vin, ain, out, meta=None, log=None):
    cmd=["ffmpeg","-y","-i",vin,"-i",ain,"-c:v","copy","-c:a","copy","-map","0:v:0","-map","1:a:0"]
    if meta:
        for k,v in meta.items(): cmd+=["-metadata",f"{k}={v}"]
    cmd.append(out); _run(cmd,log)

def copy_video(vin, out, meta=None, log=None):
    cmd=["ffmpeg","-y","-i",vin,"-c:v","copy","-c:a","copy"]
    if meta:
        for k,v in meta.items(): cmd+=["-metadata",f"{k}={v}"]
    cmd.append(out); _run(cmd,log)

def get_video_info(path):
    try:
        cmd=["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",path]
        kw={"capture_output":True,"text":True}
        if platform.system()=="Windows": kw["creationflags"]=subprocess.CREATE_NO_WINDOW
        r=subprocess.run(cmd,**kw)
        if r.returncode==0:
            d=json.loads(r.stdout); info={}; fmt=d.get("format",{})
            info["duration"]=float(fmt.get("duration",0)); info["size_mb"]=os.path.getsize(path)/(1024*1024)
            info["bitrate"]=int(fmt.get("bit_rate",0))//1000
            for s in d.get("streams",[]):
                if s.get("codec_type")=="video":
                    info["video_codec"]=s.get("codec_name","?"); info["width"]=s.get("width",0); info["height"]=s.get("height",0)
                    try: n,d2=s.get("r_frame_rate","0/1").split("/"); info["fps"]=round(int(n)/int(d2),2)
                    except: info["fps"]=0
                elif s.get("codec_type")=="audio":
                    info["audio_codec"]=s.get("codec_name","?"); info["sample_rate"]=s.get("sample_rate","?")
                    info["channels"]=s.get("channels",0); info["channel_layout"]=s.get("channel_layout","?")
            return info
    except: pass
    return {}

def open_video_player(path):
    if sys.platform=="win32": os.startfile(path)
    elif sys.platform=="darwin": subprocess.Popen(["open",path])
    else:
        for p in ["xdg-open","vlc","mpv","mplayer"]:
            try: subprocess.Popen([p,path]); return
            except FileNotFoundError: continue

def full_pipeline_audio(vin, vout, noise_amps=None, cw_path=None, cw_gain=0.5,
                        dcb=False, dcb_thr=0.5, dcb_ratio=4., dcb_mk=1.8,
                        n_var=0, var_level="Normal", prog=None, log=None):
    def L(m):
        if log: log(m)
    if noise_amps is None: noise_amps={}
    with tempfile.TemporaryDirectory(prefix="audiofix_") as tmp:
        raw=os.path.join(tmp,"raw.wav"); proc=os.path.join(tmp,"p.wav"); mp3=os.path.join(tmp,"p.mp3")
        L("▶ Extraindo áudio…"); extract_audio(vin,raw,L)
        if prog: prog(20)
        L("▶ Processando áudio…")
        process_audio(raw,proc,noise_amps,cw_path,cw_gain,dcb,dcb_thr,dcb_ratio,dcb_mk)
        if prog: prog(45)
        L("▶ MP3…"); wav_to_mp3(proc,mp3,L)
        if prog: prog(65)
        L("▶ Unindo vídeo + áudio…"); merge_av(vin,mp3,vout,log_fn=None)
        if prog: prog(80)
        if n_var>0:
            base,ext=os.path.splitext(vout)
            for i,meta in enumerate(generate_metadata_variants(n_var,var_level),1):
                vp=f"{base}_var{i:02d}{ext}"; L(f"   [{i}/{n_var}] {os.path.basename(vp)}")
                merge_av(vin,mp3,vp,meta)
                if prog: prog(80+int((i/n_var)*18))
        if prog: prog(100)
        L(f"✅ Concluído! {1+n_var} arquivo(s). → {vout}")

def full_pipeline_original(vin, vout, n_var=0, var_level="Normal", prog=None, log=None):
    def L(m):
        if log: log(m)
    L("🎬 Modo Áudio Original"); copy_video(vin,vout,log_fn=None)
    if prog: prog(60)
    if n_var>0:
        base,ext=os.path.splitext(vout)
        for i,meta in enumerate(generate_metadata_variants(n_var,var_level),1):
            vp=f"{base}_var{i:02d}{ext}"; L(f"   [{i}/{n_var}] {os.path.basename(vp)}")
            copy_video(vin,vp,meta)
            if prog: prog(60+int((i/n_var)*38))
    if prog: prog(100)
    L(f"✅ {1+n_var} arquivo(s). → {vout}")

# Whisper helpers
def check_whisper_available():
    importlib.invalidate_caches()
    try: import faster_whisper; return "faster-whisper", faster_whisper
    except ImportError: pass
    try: import whisper; return "whisper", whisper
    except ImportError: pass
    return None, None

def format_timestamp(s):
    ms=int((s%1)*1000); sec=int(s)%60; m=int(s)//60%60; h=int(s)//3600
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

def format_ts_yt(s): return f"{int(s)//60:02d}:{int(s)%60:02d}"

def transcribe_audio(path, model="base", lang=None, prog=None, log=None):
    def L(m):
        if log: log(m)
    backend,_ = check_whisper_available()
    if not backend: raise RuntimeError("Whisper não encontrado. pip install faster-whisper")
    segs=[]
    if backend=="faster-whisper":
        from faster_whisper import WhisperModel
        L(f"⏳ Carregando modelo {model}…"); m=WhisperModel(model,device="cpu",compute_type="int8")
        if prog: prog(30)
        L("🎙 Transcrevendo…"); kw={}
        if lang: kw["language"]=lang
        segments,info=m.transcribe(path,beam_size=5,**kw)
        L(f"🌐 Idioma: {info.language}")
        if prog: prog(60)
        for s in segments: segs.append({"start":s.start,"end":s.end,"text":s.text.strip()})
    else:
        import whisper as wmod; L("⏳ Carregando modelo…"); m=wmod.load_model(model)
        if prog: prog(30)
        L("🎙 Transcrevendo…"); kw={"verbose":False}
        if lang: kw["language"]=lang
        r=m.transcribe(path,**kw); L(f"🌐 Idioma: {r.get('language','?')}")
        if prog: prog(60)
        for s in r.get("segments",[]): segs.append({"start":s["start"],"end":s["end"],"text":s["text"].strip()})
    if prog: prog(90)
    L(f"✅ {len(segs)} segmento(s).")
    return segs

def segs_to_srt(segs):
    return "\n".join(f"{i}\n{format_timestamp(s['start'])} --> {format_timestamp(s['end'])}\n{s['text']}\n" for i,s in enumerate(segs,1))

def segs_to_txt(segs): return "\n".join(s["text"] for s in segs)

def segs_to_chapters(segs, merge=30.):
    if not segs: return ""
    chaps=[]; cs=segs[0]["start"]; ct=[]
    for s in segs:
        ct.append(s["text"].strip())
        if s["end"]-cs>=merge:
            chaps.append(f"{format_ts_yt(cs)} {' '.join(ct)[:80]}"); cs=s["end"]; ct=[]
    if ct: chaps.append(f"{format_ts_yt(cs)} {' '.join(ct)[:80]}")
    if chaps and not chaps[0].startswith("00:00"): chaps.insert(0,"00:00 Introdução")
    return "\n".join(chaps)

# TTS
TTS_VOICES = [
    {"id":"pt-BR-F","label":"🇧🇷 PT-BR Feminina","lang":"pt-br","slow":True,"tld":"com.br"},
    {"id":"pt-BR-M","label":"🇧🇷 PT-BR Masculina","lang":"pt-br","slow":False,"tld":"com.br"},
    {"id":"en-US-F","label":"🇺🇸 EN-US Female","lang":"en","slow":True,"tld":"com"},
    {"id":"en-UK-F","label":"🇬🇧 EN-UK Female","lang":"en","slow":True,"tld":"co.uk"},
    {"id":"es-ES-F","label":"🇪🇸 ES Femenina","lang":"es","slow":True,"tld":"es"},
    {"id":"fr-FR-F","label":"🇫🇷 FR Féminine","lang":"fr","slow":True,"tld":"fr"},
    {"id":"de-DE-F","label":"🇩🇪 DE Weiblich","lang":"de","slow":True,"tld":"de"},
    {"id":"ja-JP-F","label":"🇯🇵 JA 女性","lang":"ja","slow":True,"tld":"co.jp"},
]

def text_to_wav(text, voice_id, out_wav, vol=0.4, log=None):
    def L(m):
        if log: log(m)
    if not _is_importable("gtts"):
        L("⏳ Instalando gTTS…"); ok,_=_pip_install("gtts")
        if not ok: raise RuntimeError("Falha ao instalar gTTS")
        importlib.invalidate_caches()
    from gtts import gTTS
    v=next((x for x in TTS_VOICES if x["id"]==voice_id),TTS_VOICES[0])
    L(f"🔊 Gerando voz: {v['label']}")
    with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f: tmp=f.name
    gTTS(text=text,lang=v["lang"],slow=v["slow"],tld=v["tld"]).save(tmp)
    vol_db=20*np.log10(max(vol,0.01))
    _run(["ffmpeg","-y","-i",tmp,"-af",f"volume={vol_db:.1f}dB","-ar","44100","-ac","2","-acodec","pcm_s16le",out_wav],log)
    try: os.unlink(tmp)
    except: pass
    L(f"✅ WAV: {os.path.basename(out_wav)}")
    return out_wav


# ═══════════════════════════════════════════════════════════════════════════════
# ─── ACCORDION WIDGET ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class AccordionSection(tk.Frame):
    """Seção colapsável com header clicável e conteúdo oculto/visível."""

    def __init__(self, parent, title, icon="▸", accent=ACCENT,
                 expanded=False, badge_var=None, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self.columnconfigure(0, weight=1)
        self._expanded = tk.BooleanVar(value=expanded)
        self._accent = accent
        self._title_str = title
        self._badge_var = badge_var

        # ── Header ──────────────────────────────────────────────────────────
        self._hdr = tk.Frame(self, bg=PANEL, cursor="hand2")
        self._hdr.grid(row=0, column=0, sticky="ew")
        self._hdr.columnconfigure(1, weight=1)

        # Barra colorida lateral
        self._bar = tk.Frame(self._hdr, bg=accent, width=3)
        self._bar.grid(row=0, column=0, sticky="ns", padx=(0, 0))

        inner_hdr = tk.Frame(self._hdr, bg=PANEL, padx=10, pady=7)
        inner_hdr.grid(row=0, column=1, sticky="ew")
        inner_hdr.columnconfigure(1, weight=1)

        self._arrow_lbl = tk.Label(inner_hdr, text="▾" if expanded else "▸",
                                    font=("Segoe UI", 10, "bold"), bg=PANEL, fg=accent)
        self._arrow_lbl.grid(row=0, column=0, padx=(0, 6))

        self._title_lbl = tk.Label(inner_hdr, text=title, font=FONT_BOLD, bg=PANEL, fg=TEXT)
        self._title_lbl.grid(row=0, column=1, sticky="w")

        if badge_var:
            self._badge = tk.Label(inner_hdr, textvariable=badge_var,
                                    font=FONT_SMALL, bg=CARD, fg=accent, padx=6, pady=1)
            self._badge.grid(row=0, column=2, padx=(6, 0))

        # Bind click no header inteiro
        for w in [self._hdr, inner_hdr, self._arrow_lbl, self._title_lbl]:
            w.bind("<Button-1>", self._toggle)

        # ── Body (conteúdo da seção) ─────────────────────────────────────────
        self._body = tk.Frame(self, bg=CARD2, padx=12, pady=8)
        if expanded:
            self._body.grid(row=1, column=0, sticky="ew")

        # Separador inferior
        self._sep = tk.Frame(self, bg="#2a2a35", height=1)
        self._sep.grid(row=2, column=0, sticky="ew")

    def _toggle(self, event=None):
        if self._expanded.get():
            self._body.grid_remove()
            self._arrow_lbl.config(text="▸")
            self._expanded.set(False)
        else:
            self._body.grid(row=1, column=0, sticky="ew")
            self._arrow_lbl.config(text="▾")
            self._expanded.set(True)

    def expand(self):
        if not self._expanded.get():
            self._toggle()

    def collapse(self):
        if self._expanded.get():
            self._toggle()

    @property
    def body(self):
        return self._body

    @property
    def expanded(self):
        return self._expanded.get()


# ═══════════════════════════════════════════════════════════════════════════════
# ─── JANELAS AUXILIARES (TTS, Transcrição, Preview) ───────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class TTSWindow(tk.Toplevel):
    def __init__(self, parent, on_wav_ready=None):
        super().__init__(parent)
        self.title("TTS — Texto para Fala")
        self.geometry("560x580"); self.minsize(480,500)
        self.configure(bg=DARK); self.resizable(True,True)
        self.transient(parent); self.lift(); self.focus_force()
        self.on_wav_ready=on_wav_ready; self._wav=None; self._running=False
        self.voice_var=tk.StringVar(value=TTS_VOICES[0]["id"])
        self.vol_var=tk.DoubleVar(value=0.40)
        self._build()

    def _build(self):
        # Header
        hdr=tk.Frame(self,bg=PANEL,pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr,text="🎤  Texto para Fala",font=("Segoe UI",12,"bold"),bg=PANEL,fg=TEXT).pack(side="left",padx=14)
        tk.Button(hdr,text="✕",font=FONT_SMALL,bg=CARD,fg=MUTED,relief="flat",padx=8,pady=3,cursor="hand2",command=self.destroy).pack(side="right",padx=10)

        body=tk.Frame(self,bg=DARK,padx=14,pady=10)
        body.pack(fill="both",expand=True)

        # Texto
        tk.Label(body,text="Texto:",font=FONT_BOLD,bg=DARK,fg=MUTED).pack(anchor="w")
        tf=tk.Frame(body,bg=CARD); tf.pack(fill="both",expand=True,pady=(3,8))
        tf.rowconfigure(0,weight=1); tf.columnconfigure(0,weight=1)
        self.txt=tk.Text(tf,height=6,font=("Consolas",9),bg="#111116",fg="#c8c8e0",
                          relief="flat",wrap="word",padx=8,pady=6,insertbackground=TEXT)
        self.txt.grid(row=0,column=0,sticky="nsew")
        sb=ttk.Scrollbar(tf,command=self.txt.yview); sb.grid(row=0,column=1,sticky="ns")
        self.txt.config(yscrollcommand=sb.set)

        # Voz
        tk.Label(body,text="Voz:",font=FONT_BOLD,bg=DARK,fg=MUTED).pack(anchor="w")
        vf=tk.Frame(body,bg=CARD,padx=10,pady=6); vf.pack(fill="x",pady=(3,8))
        for i,v in enumerate(TTS_VOICES):
            rb=tk.Radiobutton(vf,text=v["label"],variable=self.voice_var,value=v["id"],
                               font=FONT_SMALL,bg=CARD,activebackground=CARD,selectcolor="#111",
                               fg=TEXT,relief="flat",cursor="hand2")
            rb.grid(row=i//2,column=i%2,sticky="w",padx=4,pady=1)

        # Volume
        vrow=tk.Frame(body,bg=DARK); vrow.pack(fill="x",pady=(0,8))
        tk.Label(vrow,text="Volume:",font=FONT_BOLD,bg=DARK,fg=MUTED,width=8,anchor="w").pack(side="left")
        self.vol_lbl=tk.Label(vrow,text="40%",font=FONT_BOLD,bg=DARK,fg=TEAL,width=5)
        self.vol_lbl.pack(side="right")
        ttk.Scale(vrow,from_=0.1,to=1.0,variable=self.vol_var,orient="horizontal",
                  command=lambda v: self.vol_lbl.config(text=f"{int(float(v)*100)}%")).pack(side="left",fill="x",expand=True,padx=6)

        # Status
        self.prog=ttk.Progressbar(body,mode="determinate",maximum=100)
        self.prog.pack(fill="x")
        self.slbl=tk.Label(body,text="Aguardando…",font=FONT_SMALL,bg=DARK,fg=MUTED)
        self.slbl.pack(anchor="w",pady=(3,0))

        # Footer
        foot=tk.Frame(self,bg=DARK,padx=14,pady=10)
        foot.pack(fill="x",side="bottom")
        tk.Button(foot,text="🔊 Gerar",font=FONT_BOLD,bg=TEAL,fg="white",relief="flat",
                  padx=14,pady=7,cursor="hand2",command=self._gen).pack(side="right")
        self.dl_btn=tk.Button(foot,text="💾 Salvar WAV",font=FONT_UI,bg=CARD,fg=MUTED,relief="flat",
                               padx=12,pady=7,cursor="hand2",state="disabled",command=self._dl)
        self.dl_btn.pack(side="right",padx=(0,6))
        self.use_btn=tk.Button(foot,text="✅ Usar no Copy White",font=FONT_UI,bg=GREEN,fg=DARK,
                                relief="flat",padx=12,pady=7,cursor="hand2",state="disabled",command=self._use)
        self.use_btn.pack(side="right",padx=(0,6))
        tk.Button(foot,text="🗑 Limpar",font=FONT_UI,bg=CARD,fg=MUTED,relief="flat",padx=10,pady=7,
                  cursor="hand2",command=lambda:self.txt.delete("1.0","end")).pack(side="left")

    def _gen(self):
        if self._running: return
        text=self.txt.get("1.0","end").strip()
        if not text: messagebox.showerror("Erro","Insira um texto."); return
        if not _FFMPEG_OK: messagebox.showerror("ffmpeg",_ffmpeg_install_hint()); return
        self._running=True; self.prog.config(value=10)
        out=os.path.join(tempfile.gettempdir(),f"audiofix_tts_{int(time.time())}.wav")
        vid=self.voice_var.get(); vol=self.vol_var.get()
        def worker():
            try:
                text_to_wav(text,vid,out,vol,lambda m:self.after(0,lambda:self.slbl.config(text=m,fg=TEXT)))
                self._wav=out
                self.after(0,lambda:(self.dl_btn.config(state="normal"),self.use_btn.config(state="normal"),
                                      self.prog.config(value=100),self.slbl.config(text="✅ Pronto!",fg=GREEN)))
            except Exception as e:
                err=str(e); self.after(0,lambda:self.slbl.config(text=f"❌ {err}",fg=RED))
            finally:
                self._running=False
        threading.Thread(target=worker,daemon=True).start()

    def _dl(self):
        if not self._wav or not os.path.isfile(self._wav): return
        dest=filedialog.asksaveasfilename(title="Salvar WAV",defaultextension=".wav",
                                           filetypes=[("WAV","*.wav"),("Todos","*.*")])
        if dest:
            import shutil; shutil.copy2(self._wav,dest)
            messagebox.showinfo("Salvo!",f"WAV salvo em:\n{dest}")

    def _use(self):
        if self._wav and os.path.isfile(self._wav):
            if self.on_wav_ready: self.on_wav_ready(self._wav)
            self.destroy()


class TranscriptionWindow(tk.Toplevel):
    def __init__(self, parent, video_path=None):
        super().__init__(parent)
        self.title("Transcrição de Áudio")
        self.geometry("700x600"); self.minsize(600,500)
        self.configure(bg=DARK); self.resizable(True,True)
        self.transient(parent); self.lift(); self.focus_force()
        self.vpath=tk.StringVar(value=video_path or "")
        self.model=tk.StringVar(value="base"); self.lang=tk.StringVar()
        self.merge=tk.DoubleVar(value=30.); self._segs=[]; self._running=False
        self._build()

    def _build(self):
        hdr=tk.Frame(self,bg=PANEL,pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr,text="🎙  Transcrição",font=("Segoe UI",12,"bold"),bg=PANEL,fg=TEXT).pack(side="left",padx=14)
        tk.Button(hdr,text="✕",font=FONT_SMALL,bg=CARD,fg=MUTED,relief="flat",padx=8,pady=3,cursor="hand2",command=self.destroy).pack(side="right",padx=10)

        body=tk.Frame(self,bg=DARK,padx=14,pady=8)
        body.pack(fill="x")

        # Arquivo
        fr=tk.Frame(body,bg=DARK); fr.pack(fill="x",pady=(0,6))
        tk.Label(fr,text="Arquivo:",font=FONT_BOLD,bg=DARK,fg=MUTED,width=8,anchor="w").pack(side="left")
        tk.Entry(fr,textvariable=self.vpath,font=FONT_MONO,bg=INPUT_BG,fg=INPUT_FG,relief="flat",bd=1).pack(side="left",fill="x",expand=True,padx=(0,6))
        tk.Button(fr,text="…",font=FONT_UI,bg=ACCENT,fg="white",relief="flat",padx=8,pady=1,cursor="hand2",
                  command=lambda:self.vpath.set(filedialog.askopenfilename(filetypes=[("Mídia","*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.m4a"),("*","*.*")]))).pack(side="right")

        # Opções
        oc=tk.Frame(body,bg=CARD,padx=10,pady=6); oc.pack(fill="x",pady=(0,6))
        tk.Label(oc,text="Modelo:",font=FONT_BOLD,bg=CARD,fg=MUTED).grid(row=0,column=0,sticky="w",padx=(0,4))
        ttk.Combobox(oc,textvariable=self.model,values=["tiny","base","small","medium","large"],state="readonly",width=8).grid(row=0,column=1,sticky="w")
        tk.Label(oc,text="Idioma:",font=FONT_BOLD,bg=CARD,fg=MUTED).grid(row=0,column=2,sticky="w",padx=(14,4))
        tk.Entry(oc,textvariable=self.lang,font=FONT_MONO,bg=INPUT_BG,fg=INPUT_FG,relief="flat",bd=1,width=6).grid(row=0,column=3,sticky="w")
        tk.Label(oc,text="(vazio=auto)",font=FONT_SMALL,bg=CARD,fg=MUTED).grid(row=0,column=4,sticky="w",padx=(4,0))

        # Progresso
        pc=tk.Frame(body,bg=CARD,padx=10,pady=6); pc.pack(fill="x",pady=(0,6))
        self.prog=ttk.Progressbar(pc,mode="determinate",maximum=100); self.prog.pack(fill="x")
        self.slbl=tk.Label(pc,text="Aguardando…",font=FONT_SMALL,bg=CARD,fg=MUTED); self.slbl.pack(anchor="w",pady=(3,0))

        # Notebook
        nb=ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=14,pady=(0,6))
        def _tab(label):
            t=tk.Frame(nb,bg=PANEL); nb.add(t,text=label)
            t.rowconfigure(0,weight=1); t.columnconfigure(0,weight=1)
            w=tk.Text(t,font=("Consolas",9),bg="#111116",fg="#c8c8e0",relief="flat",
                       state="disabled",wrap="word",padx=8,pady=6)
            w.grid(row=0,column=0,sticky="nsew")
            sb=ttk.Scrollbar(t,command=w.yview); sb.grid(row=0,column=1,sticky="ns")
            w.config(yscrollcommand=sb.set); return w
        self.seg_txt=_tab("Segmentos"); self.srt_txt=_tab("SRT"); self.chap_txt=_tab("Capítulos"); self.plain_txt=_tab("Texto")

        # Footer
        foot=tk.Frame(self,bg=DARK,padx=14,pady=8)
        foot.pack(fill="x")
        self.trans_btn=tk.Button(foot,text="🎙 TRANSCREVER",font=FONT_BOLD,bg=TEAL,fg="white",
                                  relief="flat",padx=16,pady=7,cursor="hand2",command=self._start)
        self.trans_btn.pack(side="right")
        for lbl,fmt in [("SRT","srt"),("TXT","txt")]:
            tk.Button(foot,text=f"💾 {lbl}",font=FONT_UI,bg=CARD,fg=TEAL,relief="flat",padx=10,pady=7,
                      cursor="hand2",command=lambda f=fmt:self._export(f)).pack(side="right",padx=(0,4))
        tk.Button(foot,text="📋 Copiar",font=FONT_UI,bg=CARD,fg=MUTED,relief="flat",padx=10,pady=7,
                  cursor="hand2",command=self._copy).pack(side="left")

    def _start(self):
        if self._running: return
        path=self.vpath.get().strip()
        if not path or not os.path.isfile(path): messagebox.showerror("Erro","Arquivo inválido."); return
        bk,_=check_whisper_available()
        if not bk:
            ok,_=_pip_install("faster-whisper"); importlib.invalidate_caches()
            bk,_=check_whisper_available()
            if not bk: self.slbl.config(text="❌ Instale: pip install faster-whisper",fg=RED); return
        self._running=True; self.trans_btn.config(state="disabled",text="⏳…",bg=MUTED)
        self.prog.config(value=0)
        is_vid=path.lower().endswith((".mp4",".mkv",".avi",".mov",".webm",".flv",".ts",".m4v"))
        model=self.model.get(); lang=self.lang.get().strip() or None
        def worker():
            try:
                wp=path; tmp=None
                if is_vid:
                    tmp=tempfile.mkdtemp(prefix="audiofix_tr_"); wp=os.path.join(tmp,"a.wav")
                    self.after(0,lambda:self.slbl.config(text="▶ Extraindo áudio…",fg=TEXT))
                    extract_audio_16k(path,wp)
                segs=transcribe_audio(wp,model,lang,
                                       prog=lambda p:self.after(0,lambda:self.prog.config(value=p)),
                                       log=lambda m:self.after(0,lambda:self.slbl.config(text=m,fg=TEXT)))
                self._segs=segs
                if tmp:
                    import shutil; shutil.rmtree(tmp,ignore_errors=True)
                self.after(0,lambda:self._fill(segs))
            except Exception as e:
                err=str(e); self.after(0,lambda:self.slbl.config(text=f"❌ {err}",fg=RED))
            finally:
                self._running=False
                self.after(0,lambda:self.trans_btn.config(state="normal",text="🎙 TRANSCREVER",bg=TEAL))
        threading.Thread(target=worker,daemon=True).start()

    def _fill(self,segs):
        def _set(w,txt):
            w.config(state="normal"); w.delete("1.0","end"); w.insert("1.0",txt); w.config(state="disabled")
        _set(self.seg_txt, "\n".join(f"[{format_ts_yt(s['start'])}]  {s['text']}" for s in segs))
        _set(self.srt_txt, segs_to_srt(segs))
        _set(self.chap_txt, segs_to_chapters(segs,self.merge.get()))
        _set(self.plain_txt, segs_to_txt(segs))
        self.slbl.config(text=f"✅ {len(segs)} segmento(s)",fg=GREEN)
        self.prog.config(value=100)

    def _export(self,fmt):
        if not self._segs: return
        content=segs_to_srt(self._segs) if fmt=="srt" else segs_to_txt(self._segs)
        p=filedialog.asksaveasfilename(defaultextension=f".{fmt}",filetypes=[(fmt.upper(),f"*.{fmt}"),("*","*.*")])
        if p:
            with open(p,"w",encoding="utf-8") as f: f.write(content)
            messagebox.showinfo("Exportado!",f"Salvo:\n{p}")

    def _copy(self):
        if self._segs:
            self.clipboard_clear(); self.clipboard_append(segs_to_txt(self._segs))
            messagebox.showinfo("Copiado!","Texto copiado.")


class PreviewWindow(tk.Toplevel):
    def __init__(self, parent, orig, proc, variants=None):
        super().__init__(parent)
        self.title("Preview"); self.geometry("560x400"); self.minsize(480,340)
        self.configure(bg=DARK); self.resizable(True,True); self.transient(parent)
        self.lift(); self.focus_force()
        self._orig=orig; self._proc=proc; self._vars=variants or []
        self._build(); self._load()

    def _build(self):
        hdr=tk.Frame(self,bg=PANEL,pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr,text="🔍  Preview & Info",font=("Segoe UI",11,"bold"),bg=PANEL,fg=TEXT).pack(side="left",padx=14)
        tk.Button(hdr,text="✕",font=FONT_SMALL,bg=CARD,fg=MUTED,relief="flat",padx=8,pady=3,cursor="hand2",command=self.destroy).pack(side="right",padx=10)

        body=tk.Frame(self,bg=DARK,padx=14,pady=10)
        body.pack(fill="both",expand=True)
        body.columnconfigure(0,weight=1); body.columnconfigure(1,weight=1)

        for col,(label,path,color,attr) in enumerate([
            ("📁 Original",self._orig,TEXT,"orig_info"),
            ("✅ Processado",self._proc,GREEN,"proc_info"),
        ]):
            f=tk.Frame(body,bg=DARK); f.grid(row=0,column=col,sticky="nsew",padx=(0,4) if col==0 else (4,0))
            tk.Label(f,text=label,font=FONT_BOLD,bg=DARK,fg=MUTED).pack(anchor="w",pady=(0,3))
            card=tk.Frame(f,bg=CARD,padx=10,pady=8); card.pack(fill="both",expand=True)
            w=tk.Text(card,height=8,font=FONT_MONO,bg=CARD,fg=color,relief="flat",state="disabled",wrap="word",bd=0)
            w.pack(fill="both",expand=True)
            setattr(self,attr,w)
            p=path
            tk.Button(f,text=f"▶ Abrir",font=FONT_SMALL,bg=ACCENT if col else "#2a2a35",fg="white" if col else TEXT,
                       relief="flat",padx=10,pady=4,cursor="hand2",command=lambda p=p:open_video_player(p)).pack(fill="x",pady=(4,0))

        body.rowconfigure(0,weight=1)
        btm=tk.Frame(body,bg=DARK); btm.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(10,0))
        tk.Button(btm,text="▶▶ Abrir Ambos",font=FONT_BOLD,bg="#1a3a2a",fg=GREEN,relief="flat",padx=14,pady=6,
                  cursor="hand2",command=lambda:(open_video_player(self._orig),self.after(600,lambda:open_video_player(self._proc)))).pack(side="left")
        if self._vars:
            tk.Button(btm,text=f"🎲 {len(self._vars)} variação(ões)",font=FONT_UI,bg="#1a1a2e",fg=CYAN,relief="flat",padx=12,pady=6,
                      cursor="hand2",command=self._show_vars).pack(side="left",padx=(6,0))
        self.diff_lbl=tk.Label(btm,text="",font=FONT_SMALL,bg=DARK,fg=MUTED)
        self.diff_lbl.pack(side="right")

    def _load(self):
        def worker():
            oi=get_video_info(self._orig); pi=get_video_info(self._proc)
            self.after(0,lambda:self._fill(self.orig_info,oi,TEXT))
            self.after(0,lambda:self._fill(self.proc_info,pi,GREEN))
            if oi and pi:
                om,pm=oi.get("size_mb",0),pi.get("size_mb",0)
                if om>0:
                    pct=((pm-om)/om)*100; sign="+" if pct>=0 else ""
                    self.after(0,lambda:self.diff_lbl.config(text=f"Δ tamanho: {sign}{pct:.1f}%  ({om:.2f}→{pm:.2f} MB)",fg=WARN if abs(pct)>5 else GREEN))
        threading.Thread(target=worker,daemon=True).start()

    def _fill(self,w,info,color):
        def fd(s):
            m,sec=divmod(int(s),60); h,m=divmod(m,60)
            return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
        rows=[("Duração",fd(info.get("duration",0))),("Tamanho",f"{info.get('size_mb',0):.2f} MB"),
              ("Bitrate",f"{info.get('bitrate','?')} kbps"),("Resolução",f"{info.get('width','?')}×{info.get('height','?')}"),
              ("Vídeo",f"{info.get('video_codec','?')} @ {info.get('fps','?')} fps"),
              ("Áudio",f"{info.get('audio_codec','?')} {info.get('sample_rate','?')}Hz")]
        w.config(state="normal"); w.delete("1.0","end")
        for k,v in rows: w.insert("end",f"{k+':':<12}{v}\n")
        w.config(state="disabled")

    def _show_vars(self):
        win=tk.Toplevel(self); win.title("Variações"); win.geometry("400x280")
        win.configure(bg=DARK); win.transient(self); win.lift()
        tk.Label(win,text=f"🎲 {len(self._vars)} variação(ões)",font=FONT_BOLD,bg=DARK,fg=TEXT,pady=10).pack()
        f=tk.Frame(win,bg=DARK,padx=12); f.pack(fill="both",expand=True)
        for i,p in enumerate(self._vars,1):
            r=tk.Frame(f,bg=CARD,padx=8,pady=4); r.pack(fill="x",pady=2)
            tk.Label(r,text=f"Var {i:02d}: {os.path.basename(p)}",font=FONT_MONO,bg=CARD,fg=ACC2).pack(side="left")
            tk.Button(r,text="▶",font=FONT_SMALL,bg=ACCENT,fg="white",relief="flat",padx=6,pady=1,cursor="hand2",
                      command=lambda p=p:open_video_player(p)).pack(side="right")
        tk.Button(win,text="Fechar",font=FONT_UI,bg=CARD,fg=MUTED,relief="flat",padx=12,pady=5,cursor="hand2",command=win.destroy).pack(pady=8)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── APP PRINCIPAL ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class AudioFixApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AudioFix Pro")
        self.geometry("680x820")
        self.minsize(600, 700)
        self.configure(bg=DARK)
        self.resizable(True, True)

        # Variáveis de estado
        self.video_path   = tk.StringVar()
        self.output_path  = tk.StringVar()
        self.n_variants   = tk.IntVar(value=0)
        self.var_level    = tk.StringVar(value="Normal")
        self.mode         = tk.StringVar(value="audio")
        self.running      = False

        self.cw_path      = tk.StringVar()
        self.cw_enabled   = tk.BooleanVar(value=False)
        self.cw_gain      = tk.DoubleVar(value=0.40)

        self.dcb_enabled  = tk.BooleanVar(value=False)
        self.dcb_thr      = tk.DoubleVar(value=0.50)
        self.dcb_ratio    = tk.DoubleVar(value=4.0)
        self.dcb_makeup   = tk.DoubleVar(value=1.80)

        self._noise_ctrls = {}
        self._last_orig   = None
        self._last_proc   = None
        self._last_vars   = []

        self._build_ui()
        if not _FFMPEG_OK:
            self.after(500, self._warn_ffmpeg)

    def _warn_ffmpeg(self):
        messagebox.showwarning("ffmpeg não encontrado", _ffmpeg_install_hint())

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._apply_styles()

        # ── Header compacto ───────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, pady=8)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x")  # topo colorido

        hdr_inner = tk.Frame(hdr, bg=PANEL, padx=14, pady=4)
        hdr_inner.pack(fill="x")
        hdr_inner.columnconfigure(1, weight=1)

        tk.Label(hdr_inner, text="🎛️  AudioFix Pro",
                 font=("Segoe UI", 13, "bold"), bg=PANEL, fg=TEXT).grid(row=0, column=0, sticky="w")
        tk.Label(hdr_inner, text=f"v{VERSAO_ATUAL}",
                 font=FONT_SMALL, bg=PANEL, fg=MUTED).grid(row=0, column=1, sticky="w", padx=(8,0))

        # Status badges
        badges = tk.Frame(hdr_inner, bg=PANEL)
        badges.grid(row=0, column=2, sticky="e")
        for txt, ok in [("ffmpeg", _FFMPEG_OK), ("whisper", _WHISPER_OK), ("gTTS", _GTTS_OK)]:
            tk.Label(badges, text=("✔ " if ok else "— ")+txt,
                     font=FONT_SMALL, bg=PANEL,
                     fg=GREEN if ok else MUTED).pack(side="left", padx=4)

        # ── Seletor de modo ───────────────────────────────────────────────
        mode_bar = tk.Frame(hdr, bg=DARK, padx=14, pady=6)
        mode_bar.pack(fill="x")
        for val, lbl, color, desc in [
            ("audio",    "🎛️  Manipular Áudio", ACCENT, "Fase · Ruídos · Copy White · DCB"),
            ("original", "🎬  Áudio Original",  GREEN,  "Apenas variações de metadados"),
        ]:
            self._mode_btn(mode_bar, val, lbl, color, desc)

        # ── Arquivos (sempre visível, compacto) ───────────────────────────
        file_bar = tk.Frame(self, bg=DARK, padx=14, pady=6)
        file_bar.pack(fill="x")
        file_bar.columnconfigure(1, weight=1)

        for r, (lbl, var, cmd) in enumerate([
            ("📂 Entrada:", self.video_path,  self._browse_in),
            ("💾 Saída:",   self.output_path, self._browse_out),
        ]):
            tk.Label(file_bar, text=lbl, font=FONT_BOLD, bg=DARK, fg=MUTED,
                     width=10, anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            tk.Entry(file_bar, textvariable=var, font=FONT_MONO, bg=INPUT_BG,
                     fg=INPUT_FG, relief="flat", bd=1, state="readonly").grid(
                row=r, column=1, sticky="ew", padx=(0,6), pady=2)
            tk.Button(file_bar, text="…", font=FONT_UI, bg=ACCENT, fg="white",
                      relief="flat", padx=8, pady=1, cursor="hand2",
                      command=cmd).grid(row=r, column=2, pady=2)

        # ── Scroll body com accordions ────────────────────────────────────
        outer = tk.Frame(self, bg=DARK)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=DARK)
        _win = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        self._scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(_win, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        sf = self._scroll_frame
        sf.columnconfigure(0, weight=1)

        # ── Seção: Ruídos coloridos ────────────────────────────────────────
        self._sec_noise = AccordionSection(sf, "🎨  Ruídos Coloridos",
                                            accent=PINK, expanded=True)
        self._sec_noise.grid(row=0, column=0, sticky="ew")
        self._build_noise_section(self._sec_noise.body)

        # ── Seção: Copy White ─────────────────────────────────────────────
        self._sec_cw = AccordionSection(sf, "📻  Copy White / TTS",
                                         accent=CYAN, expanded=False)
        self._sec_cw.grid(row=1, column=0, sticky="ew")
        self._build_cw_section(self._sec_cw.body)

        # ── Seção: DCB ────────────────────────────────────────────────────
        self._sec_dcb = AccordionSection(sf, "🎚  DCB — Dynamic Compression Boost",
                                          accent=GOLD, expanded=False)
        self._sec_dcb.grid(row=2, column=0, sticky="ew")
        self._build_dcb_section(self._sec_dcb.body)

        # ── Seção: Variações ──────────────────────────────────────────────
        self._var_badge = tk.StringVar(value="0 var.")
        self._sec_var = AccordionSection(sf, "🎲  Variações de Metadados",
                                          accent=PURPLE, expanded=False,
                                          badge_var=self._var_badge)
        self._sec_var.grid(row=3, column=0, sticky="ew")
        self._build_var_section(self._sec_var.body)

        # ── Seção: Log / Progresso ────────────────────────────────────────
        self._sec_log = AccordionSection(sf, "📋  Log & Progresso",
                                          accent=TEAL, expanded=True)
        self._sec_log.grid(row=4, column=0, sticky="ew")
        self._build_log_section(self._sec_log.body)

        # ── Audio-mode-only sections list ─────────────────────────────────
        self._audio_sections = [self._sec_noise, self._sec_cw, self._sec_dcb]

        # ── Footer com botões de ação ─────────────────────────────────────
        footer = tk.Frame(self, bg=PANEL, padx=14, pady=10)
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, bg=TEAL, height=2).pack(fill="x")

        btn_row = tk.Frame(footer, bg=PANEL, pady=6)
        btn_row.pack(fill="x")

        tk.Button(btn_row, text="🗑 Log",
                  font=FONT_UI, bg=CARD, fg=MUTED, relief="flat",
                  padx=10, pady=7, cursor="hand2",
                  command=self._clear_log).pack(side="left")

        tk.Button(btn_row, text="🎙 Transcrever",
                  font=FONT_UI, bg="#0f2f2f", fg=TEAL, relief="flat",
                  padx=12, pady=7, cursor="hand2",
                  command=self._open_transcription).pack(side="left", padx=(6,0))

        self.preview_btn = tk.Button(btn_row, text="🔍 Preview",
                                      font=FONT_UI, bg="#0f2f40", fg=CYAN,
                                      relief="flat", padx=12, pady=7, cursor="hand2",
                                      state="disabled",
                                      command=self._open_preview)
        self.preview_btn.pack(side="left", padx=(6,0))

        self.run_btn = tk.Button(btn_row, text="▶  PROCESSAR",
                                  font=("Segoe UI", 10, "bold"),
                                  bg=ACCENT, fg="white",
                                  activebackground=ACC2, activeforeground="white",
                                  relief="flat", padx=22, pady=7, cursor="hand2",
                                  command=self._start)
        self.run_btn.pack(side="right")

    def _mode_btn(self, parent, val, lbl, color, desc):
        """Cria botão de modo no header."""
        def select():
            self.mode.set(val)
            self._refresh_mode()
        f = tk.Frame(parent, bg=DARK, padx=4, pady=2, cursor="hand2")
        f.pack(side="left", padx=(0, 4))
        inner = tk.Frame(f, bg=CARD, padx=10, pady=5, cursor="hand2")
        inner.pack()
        name_lbl = tk.Label(inner, text=lbl, font=FONT_BOLD, bg=CARD, fg=TEXT, cursor="hand2")
        name_lbl.pack(anchor="w")
        desc_lbl = tk.Label(inner, text=desc, font=FONT_SMALL, bg=CARD, fg=MUTED, cursor="hand2")
        desc_lbl.pack(anchor="w")
        line = tk.Frame(inner, bg=MUTED, height=2)
        line.pack(fill="x", pady=(3,0))

        # Guardar refs para highlight
        key = f"_mode_ref_{val}"
        setattr(self, key, (f, inner, name_lbl, desc_lbl, line, color))

        for w in [f, inner, name_lbl, desc_lbl, line]:
            w.bind("<Button-1>", lambda e: select())

        # Selecionar o inicial
        if val == self.mode.get():
            line.config(bg=color); name_lbl.config(fg=color)

    def _refresh_mode(self):
        for val in ["audio", "original"]:
            key = f"_mode_ref_{val}"
            ref = getattr(self, key, None)
            if ref:
                f, inner, name_lbl, desc_lbl, line, color = ref
                selected = self.mode.get() == val
                line.config(bg=color if selected else MUTED)
                name_lbl.config(fg=color if selected else TEXT)

        if self.mode.get() == "audio":
            for sec in self._audio_sections:
                sec.grid()
            self.run_btn.config(text="▶  PROCESSAR", bg=ACCENT)
        else:
            for sec in self._audio_sections:
                sec.grid_remove()
            self.run_btn.config(text="▶  GERAR VARIAÇÕES", bg=GREEN)

    # ── Construção de seções ──────────────────────────────────────────────────

    def _build_noise_section(self, body):
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        defaults = {"Rosa":0.003,"Branco":0.,"Marrom":0.,"Azul":0.,"Violeta":0.,"Cinza":0.}
        for idx, name in enumerate(NOISE_GENERATORS.keys()):
            f = tk.Frame(body, bg=CARD, padx=8, pady=5)
            f.grid(row=idx//2, column=idx%2, sticky="ew",
                   padx=(0,3) if idx%2==0 else (3,0), pady=2)
            f.columnconfigure(1, weight=1)

            enabled = tk.BooleanVar(value=defaults.get(name,0)>0)
            amp     = tk.DoubleVar(value=defaults.get(name,0.003))
            color   = NOISE_COLORS[name]

            tk.Checkbutton(f, variable=enabled, bg=CARD, activebackground=CARD,
                           fg=color, selectcolor="#111", relief="flat", bd=0, cursor="hand2",
                           command=lambda e=enabled,s=f,c=color,n=name: self._toggle_noise_row(e,s,c,n)
                          ).grid(row=0, column=0, sticky="w")

            name_lbl = tk.Label(f, text=name, font=FONT_BOLD, bg=CARD,
                                fg=color if defaults.get(name,0)>0 else MUTED)
            name_lbl.grid(row=0, column=1, sticky="w")

            amp_lbl = tk.Label(f, text=f"{amp.get():.4f}", font=FONT_MONO,
                               bg=CARD, fg=color, width=7, anchor="e")
            amp_lbl.grid(row=0, column=2, sticky="e")

            sl = ttk.Scale(f, from_=0.0001, to=0.02, variable=amp, orient="horizontal",
                           command=lambda v, lbl=amp_lbl: lbl.config(text=f"{float(v):.4f}"),
                           style="Thin.Horizontal.TScale")
            sl.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2,0))

            desc = tk.Label(f, text=NOISE_DESCRIPTIONS.get(name,""),
                            font=FONT_SMALL, bg=CARD, fg=MUTED)
            desc.grid(row=2, column=0, columnspan=3, sticky="w")

            if not enabled.get():
                sl.config(state="disabled")

            self._noise_ctrls[name] = {"enabled": enabled, "amp": amp, "slider": sl,
                                        "name_lbl": name_lbl, "amp_lbl": amp_lbl, "color": color}

    def _toggle_noise_row(self, enabled_var, frame, color, name):
        ctrl = self._noise_ctrls.get(name, {})
        if enabled_var.get():
            ctrl.get("slider", {}) and ctrl["slider"].config(state="normal")
            ctrl.get("name_lbl") and ctrl["name_lbl"].config(fg=color)
            ctrl.get("amp_lbl") and ctrl["amp_lbl"].config(fg=color)
        else:
            ctrl.get("slider") and ctrl["slider"].config(state="disabled")
            ctrl.get("name_lbl") and ctrl["name_lbl"].config(fg=MUTED)
            ctrl.get("amp_lbl") and ctrl["amp_lbl"].config(fg=MUTED)

    def _build_cw_section(self, body):
        body.columnconfigure(0, weight=1)

        # Recomendação compacta
        rec = tk.Frame(body, bg="#0d1f1f", padx=8, pady=5)
        rec.pack(fill="x", pady=(0,6))
        tk.Label(rec, text="💡 Ganho recomendado: 0.30–0.50  •  Ative o DCB para nivelar",
                 font=FONT_SMALL, bg="#0d1f1f", fg=TEAL).pack(anchor="w")

        # Checkbox + TTS
        row1 = tk.Frame(body, bg=CARD2)
        row1.pack(fill="x", pady=(0,4))
        tk.Checkbutton(row1, variable=self.cw_enabled, text="Ativar Copy White",
                       font=FONT_BOLD, bg=CARD2, activebackground=CARD2,
                       fg=CYAN, selectcolor="#111", relief="flat", cursor="hand2",
                       command=self._toggle_cw).pack(side="left", padx=(4,8), pady=4)
        tk.Button(row1, text="🎤 Abrir TTS", font=FONT_SMALL, bg=TEAL, fg="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._open_tts).pack(side="right", padx=4, pady=4)

        # Arquivo WAV
        row2 = tk.Frame(body, bg=CARD2)
        row2.pack(fill="x", pady=(0,4))
        row2.columnconfigure(1, weight=1)
        tk.Label(row2, text="WAV:", font=FONT_BOLD, bg=CARD2, fg=MUTED,
                 width=5, anchor="w").grid(row=0, column=0, sticky="w", padx=(4,4), pady=3)
        self.cw_entry = tk.Entry(row2, textvariable=self.cw_path, font=FONT_MONO,
                                  bg=INPUT_BG, fg=INPUT_FG, relief="flat", bd=1, state="disabled")
        self.cw_entry.grid(row=0, column=1, sticky="ew", padx=(0,4), pady=3)
        tk.Button(row2, text="…", font=FONT_UI, bg=CYAN, fg=DARK,
                  relief="flat", padx=8, pady=1, cursor="hand2",
                  command=self._browse_cw).grid(row=0, column=2, padx=(0,4), pady=3)

        # Ganho
        row3 = tk.Frame(body, bg=CARD2)
        row3.pack(fill="x")
        tk.Label(row3, text="Ganho:", font=FONT_BOLD, bg=CARD2, fg=MUTED,
                 width=7, anchor="w").pack(side="left", padx=(4,4), pady=3)
        self.cw_gain_lbl = tk.Label(row3, text=f"{self.cw_gain.get():.2f}",
                                     font=FONT_BOLD, bg=CARD2, fg=CYAN, width=5)
        self.cw_gain_lbl.pack(side="right", padx=(0,4))
        self.cw_slider = ttk.Scale(row3, from_=0.05, to=1.0, variable=self.cw_gain,
                                    orient="horizontal",
                                    command=lambda v: self.cw_gain_lbl.config(text=f"{float(v):.2f}"))
        self.cw_slider.pack(side="left", fill="x", expand=True, padx=(0,4), pady=3)
        self.cw_slider.config(state="disabled")

        self._cw_tts_badge = tk.Label(body, text="", font=FONT_SMALL, bg=CARD2,
                                       fg=TEAL, padx=8, pady=2)

    def _toggle_cw(self):
        en = self.cw_enabled.get()
        self.cw_entry.config(state="normal" if en else "disabled")
        self.cw_slider.config(state="normal" if en else "disabled")

    def _build_dcb_section(self, body):
        body.columnconfigure(0, weight=1)

        rec = tk.Frame(body, bg="#1a1500", padx=8, pady=5)
        rec.pack(fill="x", pady=(0,6))
        tk.Label(rec, text="💡 Threshold: 0.40–0.55  •  Ratio: 3:1–6:1  •  Makeup: 1.5×–2.2×",
                 font=FONT_SMALL, bg="#1a1500", fg=GOLD).pack(anchor="w")
        tk.Label(rec, text="⚠️  Makeup > 2.5× pode distorcer",
                 font=FONT_SMALL, bg="#1a1500", fg=RED).pack(anchor="w")

        row0 = tk.Frame(body, bg=CARD2)
        row0.pack(fill="x", pady=(0,4))
        tk.Checkbutton(row0, variable=self.dcb_enabled, text="Ativar DCB",
                       font=FONT_BOLD, bg=CARD2, activebackground=CARD2,
                       fg=GOLD, selectcolor="#111", relief="flat", cursor="hand2",
                       command=self._toggle_dcb).pack(side="left", padx=(4,0), pady=4)

        self._dcb_sliders = []
        for lbl, var, lo, hi, fmt, color in [
            ("Threshold",   self.dcb_thr,    0.10, 0.90, "{:.2f}",  GOLD),
            ("Ratio",       self.dcb_ratio,  1.0,  10.0, "{:.1f}:1",GOLD),
            ("Makeup Gain", self.dcb_makeup, 0.5,  3.0,  "{:.2f}×", WARN),
        ]:
            row = tk.Frame(body, bg=CARD2)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl+":", font=FONT_BOLD, bg=CARD2, fg=MUTED,
                     width=12, anchor="w").pack(side="left", padx=(4,4))
            val_lbl = tk.Label(row, text=fmt.format(var.get()), font=FONT_BOLD,
                               bg=CARD2, fg=color, width=7)
            val_lbl.pack(side="right", padx=(0,4))
            sl = ttk.Scale(row, from_=lo, to=hi, variable=var, orient="horizontal",
                           command=lambda v, l=val_lbl, f=fmt: l.config(text=f.format(float(v))))
            sl.pack(side="left", fill="x", expand=True, padx=(0,4), pady=3)
            sl.config(state="disabled")
            self._dcb_sliders.append(sl)

    def _toggle_dcb(self):
        en = self.dcb_enabled.get()
        for sl in self._dcb_sliders:
            sl.config(state="normal" if en else "disabled")

    def _build_var_section(self, body):
        body.columnconfigure(0, weight=1)

        # Contador compacto
        spin = tk.Frame(body, bg=CARD2)
        spin.pack(fill="x", pady=(0,6))
        tk.Button(spin, text=" − ", font=("Segoe UI",10,"bold"), bg="#2a1a1a", fg=RED,
                  relief="flat", cursor="hand2", padx=4, pady=3,
                  command=self._dec_var).pack(side="left", padx=(4,0))
        self.var_lbl = tk.Label(spin, text="0", font=("Segoe UI",12,"bold"),
                                bg=CARD2, fg=TEXT, width=4, anchor="center")
        self.var_lbl.pack(side="left", padx=4)
        tk.Button(spin, text=" + ", font=("Segoe UI",10,"bold"), bg="#1a2a1a", fg=GREEN,
                  relief="flat", cursor="hand2", padx=4, pady=3,
                  command=self._inc_var).pack(side="left")
        self.var_hint = tk.Label(spin, text="sem variações",
                                  font=FONT_SMALL, bg=CARD2, fg=MUTED)
        self.var_hint.pack(side="left", padx=(8,0))

        # Nível
        tk.Label(body, text="Nível:", font=FONT_BOLD, bg=CARD2, fg=MUTED).pack(anchor="w", pady=(0,3))
        lv_row = tk.Frame(body, bg=CARD2)
        lv_row.pack(fill="x")
        lv_row.columnconfigure(0, weight=1); lv_row.columnconfigure(1, weight=1)
        lv_row.columnconfigure(2, weight=1); lv_row.columnconfigure(3, weight=1)
        self._lv_btns = {}
        for idx, (lv, cfg) in enumerate(VARIATION_LEVELS.items()):
            col = cfg["color"]
            f = tk.Frame(lv_row, bg=MUTED, padx=1, pady=1, cursor="hand2")
            f.grid(row=0, column=idx, sticky="ew", padx=(0,2) if idx<3 else 0)
            inner = tk.Frame(f, bg=CARD, padx=6, pady=5, cursor="hand2")
            inner.pack(fill="both")
            n_lbl = tk.Label(inner, text=cfg["label"], font=FONT_BOLD, bg=CARD, fg=TEXT, cursor="hand2")
            n_lbl.pack(anchor="center")
            bar = tk.Frame(inner, bg=col, height=2)
            bar.pack(fill="x", pady=(3,0))
            self._lv_btns[lv] = (f, inner, n_lbl, bar, col)
            for w in [f, inner, n_lbl, bar]:
                w.bind("<Button-1>", lambda e, l=lv: self._select_level(l))
        self._refresh_level()

        # Preview de metadado
        self._lv_ex = tk.Label(body, text="", font=FONT_MONO, bg="#111116", fg=ACC2,
                                padx=8, pady=4)
        self._lv_ex.pack(fill="x", pady=(4,0))

    def _select_level(self, level):
        self.var_level.set(level)
        self._refresh_level()

    def _refresh_level(self):
        sel = self.var_level.get()
        for lv, (f, inner, n_lbl, bar, col) in self._lv_btns.items():
            is_sel = lv == sel
            try:
                f.config(bg=col if is_sel else MUTED)
                inner.config(bg="#181818" if is_sel else CARD)
                n_lbl.config(bg="#181818" if is_sel else CARD, fg=col if is_sel else TEXT)
            except: pass
        ex = generate_metadata_variants(1, sel)[0]
        self._lv_ex.config(text=f"  title: {ex['title']}   date: {ex['date']}   track: {ex['track']}")

    def _inc_var(self):
        n = self.n_variants.get()
        if n < 50:
            self.n_variants.set(n+1)
            self._sync_var()

    def _dec_var(self):
        n = self.n_variants.get()
        if n > 0:
            self.n_variants.set(n-1)
            self._sync_var()

    def _sync_var(self):
        n = self.n_variants.get()
        self.var_lbl.config(text=str(n))
        self.var_hint.config(text="sem variações" if n==0 else f"+ {n} variação(ões)",
                              fg=MUTED if n==0 else WARN)
        self._var_badge.set(f"{n} var.")

    def _build_log_section(self, body):
        body.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0,4))
        self.status_lbl = tk.Label(body, text="Aguardando…",
                                    font=FONT_SMALL, bg=CARD2, fg=MUTED)
        self.status_lbl.pack(anchor="w", pady=(0,4))

        log_f = tk.Frame(body, bg=CARD2)
        log_f.pack(fill="both", expand=True)
        log_f.rowconfigure(0, weight=1); log_f.columnconfigure(0, weight=1)
        self.log_box = tk.Text(log_f, height=6, font=FONT_MONO, bg="#111116",
                                fg="#a0a0b8", relief="flat", state="disabled",
                                wrap="word", padx=6, pady=4)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(log_f, command=self.log_box.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_box.config(yscrollcommand=sb.set)

    # ── Navegação / helpers ───────────────────────────────────────────────────

    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Horizontal.TProgressbar",
                         troughcolor=PANEL, background=ACCENT,
                         thickness=8, bordercolor=DARK, lightcolor=ACCENT)
        style.configure("Vertical.TScrollbar",
                         troughcolor="#111116", background=MUTED,
                         arrowcolor=MUTED, bordercolor=DARK)
        style.configure("TScale", background=CARD, troughcolor=PANEL, sliderthickness=14)
        style.configure("Thin.Horizontal.TScale", sliderthickness=12)
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=INPUT_BG,
                         foreground=INPUT_FG, selectbackground=ACCENT)
        style.configure("TNotebook", background=DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=MUTED,
                         padding=[10,4], font=FONT_BOLD)
        style.map("TNotebook.Tab",
                   background=[("selected",PANEL)],
                   foreground=[("selected",TEXT)])

    def _browse_in(self):
        p = filedialog.askopenfilename(title="Selecionar vídeo",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("*","*.*")])
        if p:
            self.video_path.set(p)
            base,_ = os.path.splitext(p)
            self.output_path.set(base+"_audiofix.mp4")
            self._last_orig = p; self.preview_btn.config(state="disabled")
            self._log(f"📂 {p}")

    def _browse_out(self):
        p = filedialog.asksaveasfilename(title="Salvar como…",
            defaultextension=".mp4",
            filetypes=[("MP4","*.mp4"),("MKV","*.mkv"),("*","*.*")])
        if p: self.output_path.set(p)

    def _browse_cw(self):
        p = filedialog.askopenfilename(title="Selecionar WAV",
            filetypes=[("WAV","*.wav"),("*","*.*")])
        if p:
            self.cw_path.set(p); self._log(f"📻 Copy White: {p}")

    def _open_tts(self):
        TTSWindow(self, on_wav_ready=self._on_tts_ready)

    def _on_tts_ready(self, wav_path):
        self.cw_path.set(wav_path); self.cw_enabled.set(True)
        self._toggle_cw(); self._sec_cw.expand()
        self._log(f"🎤 TTS WAV: {wav_path}")
        messagebox.showinfo("Copy White!", f"WAV TTS aplicado:\n{os.path.basename(wav_path)}")

    def _open_preview(self):
        if not self._last_proc or not os.path.isfile(self._last_proc):
            messagebox.showwarning("Preview","Nenhum vídeo processado."); return
        PreviewWindow(self, self._last_orig, self._last_proc, self._last_vars)

    def _open_transcription(self):
        v = self.video_path.get().strip()
        TranscriptionWindow(self, video_path=v if os.path.isfile(v) else None)

    def _clear_log(self):
        self.log_box.config(state="normal"); self.log_box.delete("1.0","end")
        self.log_box.config(state="disabled")

    def _log(self, msg):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg+"\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _set_prog(self, pct):
        self.after(0, lambda: self.progress.config(value=pct))
        labels = {20:"Extraindo áudio…",45:"Processando…",65:"Convertendo MP3…",
                  80:"Unindo vídeo…",60:"Copiando vídeo…",100:"✅ Concluído!"}
        if pct in labels:
            c = GREEN if pct==100 else TEXT
            self.after(0, lambda: self.status_lbl.config(text=labels[pct], fg=c))

    def _get_noise_amps(self):
        return {n: (c["amp"].get() if c["enabled"].get() else 0.)
                for n,c in self._noise_ctrls.items()}

    # ── Processamento ─────────────────────────────────────────────────────────

    def _start(self):
        if self.running: return
        if not _FFMPEG_OK:
            messagebox.showerror("ffmpeg", _ffmpeg_install_hint()); return
        vin  = self.video_path.get().strip()
        vout = self.output_path.get().strip()
        if not vin or not os.path.isfile(vin):
            messagebox.showerror("Erro","Selecione um vídeo de entrada."); return
        if not vout:
            messagebox.showerror("Erro","Defina o arquivo de saída."); return

        mode = self.mode.get()
        n    = self.n_variants.get()
        lv   = self.var_level.get()

        if mode == "audio":
            self._start_audio(vin, vout, n, lv)
        else:
            self._start_original(vin, vout, n, lv)

    def _start_audio(self, vin, vout, n, lv):
        noise_amps = self._get_noise_amps()
        ativos     = [k for k,v in noise_amps.items() if v>0]
        cw_path    = None; cw_gain = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path = self.cw_path.get().strip()
            if not cw_path or not os.path.isfile(cw_path):
                messagebox.showerror("Copy White","Nenhum WAV válido selecionado."); return
        if not ativos and not cw_path:
            if not messagebox.askyesno("Confirmar","Sem ruídos e sem Copy White.\nApenas inversão de fase. Continuar?"): return
        if n > 10:
            if not messagebox.askyesno("Confirmar",f"{n} variações [{lv}]. Continuar?"): return

        self.running = True
        self.run_btn.config(state="disabled", text="⏳ Processando…", bg=MUTED)
        self.preview_btn.config(state="disabled")
        self.progress.config(value=0); self.status_lbl.config(text="Iniciando…", fg=TEXT)
        self._clear_log()
        self._sec_log.expand()
        self._log(f"🎛️ Modo: Áudio  |  Variações: {n}  |  Nível: {lv}")

        def worker():
            try:
                full_pipeline_audio(vin, vout,
                    noise_amps, cw_path, cw_gain,
                    self.dcb_enabled.get(), self.dcb_thr.get(),
                    self.dcb_ratio.get(), self.dcb_makeup.get(),
                    n, lv, self._set_prog, self._log)
                self._last_orig = vin; self._last_proc = vout
                base,ext = os.path.splitext(vout)
                self._last_vars = [f"{base}_var{i:02d}{ext}" for i in range(1,n+1)
                                    if os.path.isfile(f"{base}_var{i:02d}{ext}")]
                self.after(0, lambda: self.preview_btn.config(state="normal"))
                self.after(0, lambda: messagebox.showinfo("Concluído!",
                    f"{1+n} arquivo(s) gerado(s).\n{vout}"))
            except Exception as e:
                err=str(e); self._log(f"❌ {err}")
                self.after(0,lambda:messagebox.showerror("Erro",err))
                self.after(0,lambda:self.status_lbl.config(text=f"❌ {err}",fg=RED))
            finally:
                self.running=False
                self.after(0,lambda:self.run_btn.config(state="normal",text="▶  PROCESSAR",bg=ACCENT))
        threading.Thread(target=worker, daemon=True).start()

    def _start_original(self, vin, vout, n, lv):
        self.running = True
        self.run_btn.config(state="disabled", text="⏳ Gerando…", bg=MUTED)
        self.preview_btn.config(state="disabled")
        self.progress.config(value=0); self.status_lbl.config(text="Iniciando…", fg=TEXT)
        self._clear_log()
        self._sec_log.expand()
        self._log(f"🎬 Modo: Original  |  Variações: {n}  |  Nível: {lv}")

        def worker():
            try:
                full_pipeline_original(vin, vout, n, lv, self._set_prog, self._log)
                self._last_orig = vin; self._last_proc = vout
                base,ext = os.path.splitext(vout)
                self._last_vars = [f"{base}_var{i:02d}{ext}" for i in range(1,n+1)
                                    if os.path.isfile(f"{base}_var{i:02d}{ext}")]
                self.after(0, lambda: self.preview_btn.config(state="normal"))
                self.after(0, lambda: messagebox.showinfo("Concluído!",
                    f"{1+n} arquivo(s).\n{vout}"))
            except Exception as e:
                err=str(e); self._log(f"❌ {err}")
                self.after(0,lambda:messagebox.showerror("Erro",err))
                self.after(0,lambda:self.status_lbl.config(text=f"❌ {err}",fg=RED))
            finally:
                self.running=False
                self.after(0,lambda:self.run_btn.config(state="normal",text="▶  GERAR VARIAÇÕES",bg=GREEN))
        threading.Thread(target=worker, daemon=True).start()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = AudioFixApp()
    app.mainloop()