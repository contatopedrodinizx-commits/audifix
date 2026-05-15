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
import asyncio
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

# ─── Versão ───────────────────────────────────────────────────────────────────
VERSAO_ATUAL = "5.4"
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
    missing = [p for p in ["numpy", "scipy"] if not _is_importable(p)]
    if missing:
        _pip_install(*missing)
        importlib.invalidate_caches()

def _ensure_edge_tts():
    """Instala edge-tts silenciosamente se necessário."""
    if not _is_importable("edge_tts"):
        ok, _ = _pip_install("edge-tts")
        importlib.invalidate_caches()
        return ok
    return True

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

def _check_gtts_silent():     return _is_importable("gtts")
def _check_whisper_silent():  return _is_importable("faster_whisper") or _is_importable("whisper")
def _check_edge_tts_silent(): return _is_importable("edge_tts")
def _check_requests_silent(): return _is_importable("requests")

# ─── Paleta ───────────────────────────────────────────────────────────────────
DARK   = "#0d0d0f"
PANEL  = "#16161a"
CARD   = "#1e1e24"
CARD2  = "#252530"
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
INDIGO = "#818cf8"

NOISE_COLORS = {
    "Rosa": "#f472b6", "Branco": "#e8e8f0", "Marrom": "#d97706",
    "Azul": "#38bdf8", "Violeta": "#c084fc", "Cinza": "#94a3b8",
}

FONT_TITLE  = ("Segoe UI", 18, "bold")
FONT_LABEL  = ("Segoe UI", 9)
FONT_BOLD   = ("Segoe UI", 9, "bold")
FONT_MONO   = ("Consolas", 8)
FONT_STATUS = ("Segoe UI", 8)
FONT_SMALL  = ("Segoe UI", 7)
FONT_H3     = ("Segoe UI", 8, "bold")
FONT_TAB    = ("Segoe UI", 9, "bold")
INPUT_FG    = "black"
INPUT_BG    = "#f0f0f5"

# ─── Variáveis globais ────────────────────────────────────────────────────────
_FFMPEG_OK    = False
_WHISPER_OK   = False
_GTTS_OK      = False
_EDGE_TTS_OK  = False
_REQUESTS_OK  = False


# ═══════════════════════════════════════════════════════════════════════════════
#   SISTEMA DE ATUALIZAÇÃO AUTOMÁTICA
# ═══════════════════════════════════════════════════════════════════════════════

def _versao_maior(v_remota: str, v_local: str) -> bool:
    """
    Retorna True se v_remota for estritamente maior que v_local.
    Suporta formatos: "5.3", "5.3.1", "v5.3", "v5.3.1"
    """
    def _parse(v):
        v = v.strip().lstrip("vV")
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)
    return _parse(v_remota) > _parse(v_local)


def _buscar_ultima_versao_github() -> dict | None:
    """
    Consulta a API do GitHub para obter a release mais recente.
    Retorna dict com 'tag_name', 'body' (notas), 'assets' ou None em caso de falha.
    """
    import urllib.request
    import urllib.error
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"AudioFix/{VERSAO_ATUAL}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception:
        return None


def _baixar_e_substituir(asset_url: str, destino: str,
                          progresso_cb=None, log_cb=None) -> bool:
    """
    Baixa o arquivo .py da release e substitui o executável atual.
    - asset_url : URL direta do asset no GitHub (ex: .../audifix_app.py)
    - destino   : caminho do script atual (sys.argv[0] ou __file__)
    - progresso_cb(pct: int)  : callback de progresso 0–100
    - log_cb(msg: str)        : callback de log
    Retorna True em caso de sucesso.
    """
    import urllib.request

    def log(m):
        if log_cb: log_cb(m)

    try:
        log(f"⬇  Baixando de: {asset_url}")
        if progresso_cb: progresso_cb(5)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="audifix_update_")
        os.close(tmp_fd)

        def _reporthook(block_num, block_size, total_size):
            if total_size > 0 and progresso_cb:
                pct = min(90, int(block_num * block_size / total_size * 85) + 5)
                progresso_cb(pct)

        req = urllib.request.Request(
            asset_url,
            headers={"User-Agent": f"AudioFix/{VERSAO_ATUAL}"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            baixado = 0
            bloco = 8192
            while True:
                chunk = resp.read(bloco)
                if not chunk:
                    break
                f.write(chunk)
                baixado += len(chunk)
                if total > 0 and progresso_cb:
                    pct = min(90, int(baixado / total * 85) + 5)
                    progresso_cb(pct)

        log("✅  Download concluído. Substituindo arquivo…")
        if progresso_cb: progresso_cb(92)

        # Validação mínima: o arquivo baixado deve conter a string VERSAO_ATUAL
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            conteudo = f.read(200)
        if "VERSAO_ATUAL" not in conteudo and "import" not in conteudo:
            log("❌  Arquivo baixado parece inválido (não é um script Python).")
            os.unlink(tmp_path)
            return False

        # Cria backup do arquivo atual antes de substituir
        backup_path = destino + ".bak"
        try:
            import shutil
            shutil.copy2(destino, backup_path)
            log(f"💾  Backup salvo em: {backup_path}")
        except Exception as e:
            log(f"⚠  Não foi possível criar backup: {e}")

        # Substitui o arquivo atual pelo novo
        import shutil
        shutil.move(tmp_path, destino)
        if progresso_cb: progresso_cb(100)
        log(f"✅  Arquivo atualizado: {destino}")
        return True

    except Exception as e:
        log(f"❌  Falha no download: {e}")
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass
        return False


def _reiniciar_app(destino: str):
    """Reinicia o aplicativo executando o script atualizado."""
    try:
        subprocess.Popen([sys.executable, destino])
    except Exception:
        pass
    # Encerra o processo atual
    os._exit(0)


class UpdateDialog(tk.Toplevel):
    """
    Janela modal de notificação de atualização.
    Mostra versão atual vs nova, notas de release e botões Sim/Não.
    """

    def __init__(self, parent, versao_nova: str, notas: str,
                 asset_url: str, script_path: str):
        super().__init__(parent)
        self.title("Atualização disponível")
        self.configure(bg=DARK)
        self.resizable(False, False)
        self.grab_set()           # modal
        self.attributes("-topmost", True)

        self._versao_nova  = versao_nova
        self._notas        = notas
        self._asset_url    = asset_url
        self._script_path  = script_path
        self._updating     = False

        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = 560, 420
        self.geometry(f"{w}x{h}+{pw - w//2}+{ph - h//2}")

    def _build(self):
        # ── Cabeçalho ─────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg="#14141f", pady=16); hdr.pack(fill="x")
        tk.Label(hdr, text="🚀  Nova versão disponível!",
                 font=("Segoe UI", 13, "bold"), bg="#14141f", fg=ACC2).pack()
        tk.Label(hdr,
                 text=f"Versão atual: v{VERSAO_ATUAL}   →   Nova versão: v{self._versao_nova}",
                 font=("Segoe UI", 9), bg="#14141f", fg=TEXT).pack(pady=(4, 0))

        # ── Notas de release ──────────────────────────────────────────────
        notes_frame = tk.Frame(self, bg=CARD, padx=14, pady=10)
        notes_frame.pack(fill="both", expand=True, padx=14, pady=(10, 6))
        tk.Label(notes_frame, text="📋  O que há de novo:",
                 font=FONT_BOLD, bg=CARD, fg=MUTED, anchor="w").pack(anchor="w")
        notes_txt = tk.Text(notes_frame, height=8,
                            font=("Consolas", 8), bg="#111116", fg=TEXT,
                            relief="flat", state="normal", wrap="word",
                            selectbackground=ACCENT)
        notes_txt.pack(fill="both", expand=True, pady=(4, 0))
        notas_display = self._notas.strip() if self._notas.strip() else "Sem notas de release."
        notes_txt.insert("1.0", notas_display)
        notes_txt.config(state="disabled")

        # ── Barra de progresso (oculta inicialmente) ─────────────────────
        self._prog_frame = tk.Frame(self, bg=DARK, padx=14, pady=4)
        self._prog_frame.pack(fill="x")
        self._prog_bar = ttk.Progressbar(self._prog_frame, mode="determinate",
                                          maximum=100, length=530)
        self._prog_bar.pack(fill="x")
        self._prog_lbl = tk.Label(self._prog_frame, text="",
                                   font=FONT_STATUS, bg=DARK, fg=CYAN, anchor="w")
        self._prog_lbl.pack(anchor="w", pady=(2, 0))
        # Oculta até iniciar o download
        self._prog_frame.pack_forget()

        # ── Botões ────────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=DARK, pady=10); btn_row.pack(fill="x", padx=14)

        self._sim_btn = tk.Button(
            btn_row,
            text="✅  Sim, atualizar agora",
            font=("Segoe UI", 9, "bold"),
            bg=GREEN, fg=DARK,
            activebackground=LIME,
            relief="flat", padx=16, pady=7,
            cursor="hand2",
            command=self._iniciar_atualizacao
        )
        self._sim_btn.pack(side="left")

        self._nao_btn = tk.Button(
            btn_row,
            text="✖  Não, continuar assim",
            font=FONT_LABEL,
            bg=CARD2, fg=MUTED,
            relief="flat", padx=12, pady=7,
            cursor="hand2",
            command=self.destroy
        )
        self._nao_btn.pack(side="left", padx=(8, 0))

        tk.Label(btn_row,
                 text="O app será reiniciado automaticamente após a atualização.",
                 font=FONT_SMALL, bg=DARK, fg=MUTED).pack(side="right")

    def _iniciar_atualizacao(self):
        if self._updating:
            return
        self._updating = True
        self._sim_btn.config(state="disabled", text="⏳  Atualizando…", bg=MUTED)
        self._nao_btn.config(state="disabled")
        self._prog_frame.pack(fill="x")
        self.update_idletasks()

        def _prog(pct):
            self.after(0, lambda: self._prog_bar.config(value=pct))

        def _log(msg):
            self.after(0, lambda: self._prog_lbl.config(text=msg))

        def worker():
            ok = _baixar_e_substituir(
                self._asset_url,
                self._script_path,
                progresso_cb=_prog,
                log_cb=_log
            )
            if ok:
                _log("🔄  Reiniciando aplicativo…")
                self.after(800, lambda: _reiniciar_app(self._script_path))
            else:
                self.after(0, lambda: self._sim_btn.config(
                    state="normal", text="🔄  Tentar novamente", bg=WARN, fg=DARK))
                self.after(0, lambda: self._nao_btn.config(state="normal"))
                self._updating = False

        threading.Thread(target=worker, daemon=True).start()


def verificar_atualizacao(parent_window, silencioso: bool = True):
    """
    Verifica se há uma nova versão no GitHub.
    - silencioso=True : não mostra nada se já estiver na versão mais recente
    - silencioso=False: mostra aviso mesmo se estiver atualizado
    Deve ser chamado em thread separada para não travar a UI.
    """
    def _worker():
        dados = _buscar_ultima_versao_github()
        if dados is None:
            if not silencioso:
                parent_window.after(0, lambda: messagebox.showwarning(
                    "Verificação de atualização",
                    "Não foi possível verificar atualizações.\nVerifique sua conexão com a internet."
                ))
            return

        versao_remota = dados.get("tag_name", "").strip().lstrip("vV")
        notas         = dados.get("body", "")

        if not versao_remota:
            return

        if not _versao_maior(versao_remota, VERSAO_ATUAL):
            if not silencioso:
                parent_window.after(0, lambda: messagebox.showinfo(
                    "AudioFix Pro — Atualizado",
                    f"Você já está na versão mais recente (v{VERSAO_ATUAL}). ✅"
                ))
            return

        # Procura asset .py na release
        assets     = dados.get("assets", [])
        asset_url  = None
        asset_name = None
        for a in assets:
            nome = a.get("name", "")
            if nome.lower().endswith(".py"):
                asset_url  = a.get("browser_download_url")
                asset_name = nome
                break

        if not asset_url:
            # Sem asset .py: direciona para a página da release
            def _sem_asset():
                ir = messagebox.askyesno(
                    "Atualização disponível",
                    f"Nova versão v{versao_remota} disponível!\n\n"
                    f"O download automático não está disponível para esta release.\n"
                    f"Deseja abrir a página de download no navegador?"
                )
                if ir:
                    import webbrowser
                    webbrowser.open(URL_DOWNLOAD)
            parent_window.after(0, _sem_asset)
            return

        # Determina o caminho do script atual
        script_path = os.path.abspath(
            sys.argv[0] if sys.argv[0].endswith(".py")
            else __file__
        )

        def _mostrar_dialog():
            UpdateDialog(
                parent_window,
                versao_nova  = versao_remota,
                notas        = notas,
                asset_url    = asset_url,
                script_path  = script_path,
            )

        parent_window.after(0, _mostrar_dialog)

    threading.Thread(target=_worker, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#   TTS — MOTORES E VOZES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── gTTS (Google TTS, via scraping — gratuito, sem API key) ──────────────────
TTS_VOICES = {
    # ── Português BR ──────────────────────────────────────────────────────────
    "🇧🇷 Feminina Natural — PT-BR":     {"lang":"pt","tld":"com.br","pitch":1.12,"rate":1.00,"eq":"treble=g=3:f=6000",           "gender":"F"},
    "🇧🇷 Feminina Jovem — PT-BR":       {"lang":"pt","tld":"com.br","pitch":1.22,"rate":1.05,"eq":"treble=g=5:f=7000",           "gender":"F"},
    "🇧🇷 Feminina Suave — PT-BR":       {"lang":"pt","tld":"com.br","pitch":1.08,"rate":0.93,"eq":"bass=g=2:f=120",              "gender":"F"},
    "🇧🇷 Feminina Animada — PT-BR":     {"lang":"pt","tld":"com.br","pitch":1.18,"rate":1.10,"eq":"treble=g=4:f=8000",           "gender":"F"},
    "🇧🇷 Feminina Grave — PT-BR":       {"lang":"pt","tld":"com.br","pitch":1.00,"rate":0.97,"eq":"bass=g=3:f=200",              "gender":"F"},
    "🇧🇷 Feminina Radialista — PT-BR":  {"lang":"pt","tld":"com.br","pitch":1.14,"rate":1.03,"eq":"treble=g=2:f=5500,bass=g=1:f=180","gender":"F"},
    "🇧🇷 Masculina Natural — PT-BR":    {"lang":"pt","tld":"com.br","pitch":0.82,"rate":1.00,"eq":"bass=g=4:f=150",              "gender":"M"},
    "🇧🇷 Masculina Grave — PT-BR":      {"lang":"pt","tld":"com.br","pitch":0.72,"rate":0.95,"eq":"bass=g=6:f=100",              "gender":"M"},
    "🇧🇷 Masculina Jovem — PT-BR":      {"lang":"pt","tld":"com.br","pitch":0.88,"rate":1.05,"eq":"bass=g=2:f=180",              "gender":"M"},
    "🇧🇷 Masculina Suave — PT-BR":      {"lang":"pt","tld":"com.br","pitch":0.85,"rate":0.92,"eq":"bass=g=5:f=120",              "gender":"M"},
    "🇧🇷 Masculina Animada — PT-BR":    {"lang":"pt","tld":"com.br","pitch":0.90,"rate":1.08,"eq":"treble=g=2:f=5000",           "gender":"M"},
    "🇧🇷 Masculina Profunda — PT-BR":   {"lang":"pt","tld":"com.br","pitch":0.68,"rate":0.90,"eq":"bass=g=8:f=80",               "gender":"M"},
    "🇧🇷 Narrador — PT-BR":             {"lang":"pt","tld":"com.br","pitch":0.78,"rate":0.94,"eq":"bass=g=3:f=130,treble=g=1:f=5000","gender":"M"},
    "🇧🇷 Narrador Grave — PT-BR":       {"lang":"pt","tld":"com.br","pitch":0.70,"rate":0.91,"eq":"bass=g=7:f=90,treble=g=1:f=4000", "gender":"M"},
    "🇧🇷 Locutor Rádio — PT-BR":        {"lang":"pt","tld":"com.br","pitch":0.80,"rate":0.97,"eq":"bass=g=5:f=110,treble=g=2:f=5500","gender":"M"},
    "🇵🇹 Feminina — PT-PT":             {"lang":"pt","tld":"pt",    "pitch":1.08,"rate":1.00,"eq":"treble=g=2:f=6000",           "gender":"F"},
    "🇵🇹 Masculina — PT-PT":            {"lang":"pt","tld":"pt",    "pitch":0.80,"rate":1.00,"eq":"bass=g=3:f=150",              "gender":"M"},
    "🇺🇸 Female Natural — EN-US":       {"lang":"en","tld":"com",   "pitch":1.10,"rate":1.00,"eq":"treble=g=3:f=6000",           "gender":"F"},
    "🇺🇸 Female Young — EN-US":         {"lang":"en","tld":"com",   "pitch":1.20,"rate":1.06,"eq":"treble=g=5:f=7000",           "gender":"F"},
    "🇺🇸 Male Natural — EN-US":         {"lang":"en","tld":"com",   "pitch":0.82,"rate":1.00,"eq":"bass=g=4:f=150",              "gender":"M"},
    "🇺🇸 Male Deep — EN-US":            {"lang":"en","tld":"com",   "pitch":0.72,"rate":0.95,"eq":"bass=g=7:f=90",               "gender":"M"},
    "🇬🇧 Female — EN-UK":               {"lang":"en","tld":"co.uk", "pitch":1.12,"rate":1.00,"eq":"treble=g=3:f=6500",           "gender":"F"},
    "🇬🇧 Male — EN-UK":                 {"lang":"en","tld":"co.uk", "pitch":0.78,"rate":1.00,"eq":"bass=g=4:f=140",              "gender":"M"},
    "🇪🇸 Feminina — ES":                {"lang":"es","tld":"com",   "pitch":1.10,"rate":1.00,"eq":"treble=g=2:f=6000",           "gender":"F"},
    "🇫🇷 Féminine — FR":                {"lang":"fr","tld":"fr",    "pitch":1.10,"rate":1.00,"eq":"treble=g=2:f=6000",           "gender":"F"},
}

TTS_VOICE_GROUPS_GTTS = {
    "🇧🇷 Português BR": [k for k,v in TTS_VOICES.items() if v["tld"]=="com.br"],
    "🇵🇹 Português PT": [k for k,v in TTS_VOICES.items() if v["tld"]=="pt"],
    "🇺🇸 Inglês US":    [k for k,v in TTS_VOICES.items() if v["tld"]=="com" and v["lang"]=="en"],
    "🇬🇧 Inglês UK":    [k for k,v in TTS_VOICES.items() if v["tld"]=="co.uk"],
    "🌍 Outros":         [k for k,v in TTS_VOICES.items() if v["lang"] not in ("pt","en")],
}


# ─── Edge TTS (Microsoft Azure Neural — 100% gratuito, ~300 vozes) ────────────
EDGE_TTS_VOICES = {
    "🇧🇷 Francisca (Feminina Neural) — PT-BR":   {"voice_id":"pt-BR-FranciscaNeural",   "lang":"pt-BR","gender":"F","desc":"Voz feminina natural, calorosa"},
    "🇧🇷 Thalita (Feminina Jovem) — PT-BR":      {"voice_id":"pt-BR-ThalitaNeural",      "lang":"pt-BR","gender":"F","desc":"Jovem e expressiva"},
    "🇧🇷 Antonio (Masculino Neural) — PT-BR":    {"voice_id":"pt-BR-AntonioNeural",      "lang":"pt-BR","gender":"M","desc":"Voz masculina confiante"},
    "🇵🇹 Raquel (Feminina Neural) — PT-PT":      {"voice_id":"pt-PT-RaquelNeural",       "lang":"pt-PT","gender":"F","desc":"Portuguesa europeia, clara"},
    "🇵🇹 Duarte (Masculino Neural) — PT-PT":     {"voice_id":"pt-PT-DuarteNeural",       "lang":"pt-PT","gender":"M","desc":"Português europeu, formal"},
    "🇵🇹 Fernanda (Feminina) — PT-PT":           {"voice_id":"pt-PT-FernandaNeural",     "lang":"pt-PT","gender":"F","desc":"Voz feminina suave"},
    "🇺🇸 Jenny (Feminina Casual) — EN-US":       {"voice_id":"en-US-JennyNeural",        "lang":"en-US","gender":"F","desc":"Casual e amigável"},
    "🇺🇸 Aria (Feminina Expressiva) — EN-US":    {"voice_id":"en-US-AriaNeural",         "lang":"en-US","gender":"F","desc":"Expressiva, múltiplos estilos"},
    "🇺🇸 Sara (Feminina Suave) — EN-US":         {"voice_id":"en-US-SaraNeural",         "lang":"en-US","gender":"F","desc":"Tom suave e tranquilo"},
    "🇺🇸 Nancy (Feminina Profissional) — EN-US": {"voice_id":"en-US-NancyNeural",        "lang":"en-US","gender":"F","desc":"Profissional, podcast"},
    "🇺🇸 Michelle (Feminina Quente) — EN-US":    {"voice_id":"en-US-MichelleNeural",     "lang":"en-US","gender":"F","desc":"Tom quente e envolvente"},
    "🇺🇸 Elizabeth (Feminina Madura) — EN-US":   {"voice_id":"en-US-ElizabethNeural",    "lang":"en-US","gender":"F","desc":"Madura e sofisticada"},
    "🇺🇸 Guy (Masculino Natural) — EN-US":       {"voice_id":"en-US-GuyNeural",          "lang":"en-US","gender":"M","desc":"Natural e direto"},
    "🇺🇸 Davis (Masculino Casual) — EN-US":      {"voice_id":"en-US-DavisNeural",        "lang":"en-US","gender":"M","desc":"Casual e jovem"},
    "🇺🇸 Tony (Masculino Entusiasmado) — EN-US": {"voice_id":"en-US-TonyNeural",         "lang":"en-US","gender":"M","desc":"Entusiasmado, energia alta"},
    "🇺🇸 Jason (Masculino Sério) — EN-US":       {"voice_id":"en-US-JasonNeural",        "lang":"en-US","gender":"M","desc":"Sério e profissional"},
    "🇺🇸 Brandon (Masculino Jovem) — EN-US":     {"voice_id":"en-US-BrandonNeural",      "lang":"en-US","gender":"M","desc":"Tom jovem e dinâmico"},
    "🇺🇸 Christopher (Masculino Grave) — EN-US": {"voice_id":"en-US-ChristopherNeural",  "lang":"en-US","gender":"M","desc":"Grave e autoritário"},
    "🇺🇸 Roger (Masculino Maduro) — EN-US":      {"voice_id":"en-US-RogerNeural",        "lang":"en-US","gender":"M","desc":"Maduro, narrador clássico"},
    "🇺🇸 Steffan (Masculino Narrador) — EN-US":  {"voice_id":"en-US-SteffanNeural",      "lang":"en-US","gender":"M","desc":"Ideal para narração"},
    "🇬🇧 Sonia (Feminina Neural) — EN-GB":       {"voice_id":"en-GB-SoniaNeural",        "lang":"en-GB","gender":"F","desc":"Britânica natural"},
    "🇬🇧 Mia (Feminina Jovem) — EN-GB":          {"voice_id":"en-GB-MiaNeural",          "lang":"en-GB","gender":"F","desc":"Jovem britânica"},
    "🇬🇧 Ryan (Masculino Neural) — EN-GB":       {"voice_id":"en-GB-RyanNeural",         "lang":"en-GB","gender":"M","desc":"Britânico expressivo"},
    "🇬🇧 Thomas (Masculino Maduro) — EN-GB":     {"voice_id":"en-GB-ThomasNeural",       "lang":"en-GB","gender":"M","desc":"Britânico clássico"},
    "🇦🇺 Natasha (Feminina) — EN-AU":            {"voice_id":"en-AU-NatashaNeural",      "lang":"en-AU","gender":"F","desc":"Australiana natural"},
    "🇦🇺 William (Masculino) — EN-AU":           {"voice_id":"en-AU-WilliamNeural",      "lang":"en-AU","gender":"M","desc":"Australiano confiante"},
    "🇨🇦 Clara (Feminina) — EN-CA":              {"voice_id":"en-CA-ClaraNeural",        "lang":"en-CA","gender":"F","desc":"Canadense amigável"},
    "🇨🇦 Liam (Masculino) — EN-CA":              {"voice_id":"en-CA-LiamNeural",         "lang":"en-CA","gender":"M","desc":"Canadense casual"},
    "🇮🇪 Emily (Feminina) — EN-IE":              {"voice_id":"en-IE-EmilyNeural",        "lang":"en-IE","gender":"F","desc":"Irlandesa suave"},
    "🇮🇪 Connor (Masculino) — EN-IE":            {"voice_id":"en-IE-ConnorNeural",       "lang":"en-IE","gender":"M","desc":"Irlandês caloroso"},
    "🇪🇸 Elvira (Feminina) — ES-ES":             {"voice_id":"es-ES-ElviraNeural",       "lang":"es-ES","gender":"F","desc":"Espanhola clára"},
    "🇪🇸 Alvaro (Masculino) — ES-ES":            {"voice_id":"es-ES-AlvaroNeural",       "lang":"es-ES","gender":"M","desc":"Espanhol profissional"},
    "🇲🇽 Dalia (Feminina) — ES-MX":              {"voice_id":"es-MX-DaliaNeural",        "lang":"es-MX","gender":"F","desc":"Mexicana calorosa"},
    "🇲🇽 Jorge (Masculino) — ES-MX":             {"voice_id":"es-MX-JorgeNeural",        "lang":"es-MX","gender":"M","desc":"Mexicano natural"},
    "🇫🇷 Denise (Feminina) — FR-FR":             {"voice_id":"fr-FR-DeniseNeural",       "lang":"fr-FR","gender":"F","desc":"Francesa elegante"},
    "🇫🇷 Henri (Masculino) — FR-FR":             {"voice_id":"fr-FR-HenriNeural",        "lang":"fr-FR","gender":"M","desc":"Francês natural"},
    "🇮🇹 Elsa (Feminina) — IT-IT":               {"voice_id":"it-IT-ElsaNeural",         "lang":"it-IT","gender":"F","desc":"Italiana expressiva"},
    "🇮🇹 Diego (Masculino) — IT-IT":             {"voice_id":"it-IT-DiegoNeural",        "lang":"it-IT","gender":"M","desc":"Italiano confiante"},
    "🇩🇪 Katja (Feminina) — DE-DE":              {"voice_id":"de-DE-KatjaNeural",        "lang":"de-DE","gender":"F","desc":"Alemã profissional"},
    "🇩🇪 Conrad (Masculino) — DE-DE":            {"voice_id":"de-DE-ConradNeural",       "lang":"de-DE","gender":"M","desc":"Alemão claro"},
    "🇯🇵 Nanami (Feminina) — JA-JP":             {"voice_id":"ja-JP-NanamiNeural",       "lang":"ja-JP","gender":"F","desc":"Japonesa suave"},
    "🇯🇵 Keita (Masculino) — JA-JP":             {"voice_id":"ja-JP-KeitaNeural",        "lang":"ja-JP","gender":"M","desc":"Japonês natural"},
    "🇰🇷 Sun-Hi (Feminina) — KO-KR":             {"voice_id":"ko-KR-SunHiNeural",        "lang":"ko-KR","gender":"F","desc":"Coreana expressiva"},
    "🇰🇷 InJoon (Masculino) — KO-KR":            {"voice_id":"ko-KR-InJoonNeural",       "lang":"ko-KR","gender":"M","desc":"Coreano profissional"},
}

EDGE_TTS_VOICE_GROUPS = {
    "🇧🇷 Português BR": [k for k,v in EDGE_TTS_VOICES.items() if v["lang"]=="pt-BR"],
    "🇵🇹 Português PT": [k for k,v in EDGE_TTS_VOICES.items() if v["lang"]=="pt-PT"],
    "🇺🇸 Inglês US":    [k for k,v in EDGE_TTS_VOICES.items() if v["lang"]=="en-US"],
    "🇬🇧 Inglês UK":    [k for k,v in EDGE_TTS_VOICES.items() if v["lang"]=="en-GB"],
    "🌏 Outros":         [k for k,v in EDGE_TTS_VOICES.items() if v["lang"] not in ("pt-BR","pt-PT","en-US","en-GB")],
}

# ─── ElevenLabs ───────────────────────────────────────────────────────────────
ELEVENLABS_VOICES = {
    "Rachel (Feminina Calma)":        {"voice_id":"21m00Tcm4TlvDq8ikWAM", "gender":"F","desc":"Calma e profissional"},
    "Domi (Feminina Forte)":          {"voice_id":"AZnzlk1XvdvUeBnXmlld", "gender":"F","desc":"Confiante, forte"},
    "Bella (Feminina Suave)":         {"voice_id":"EXAVITQu4vr4xnSDxMaL", "gender":"F","desc":"Suave e calorosa"},
    "Elli (Feminina Jovem)":          {"voice_id":"MF3mGyEYCl7XYWbV9V6O", "gender":"F","desc":"Jovem e expressiva"},
    "Emily (Feminina Serena)":        {"voice_id":"LcfcDJNUP1GQjkzn1xUU", "gender":"F","desc":"Serena, meditação"},
    "Freya (Feminina Animada)":       {"voice_id":"jsCqWAovK2LkecY7zXl4", "gender":"F","desc":"Animada e dinâmica"},
    "Grace (Feminina Madura)":        {"voice_id":"oWAxZDx7w5VEj9dCyTzz", "gender":"F","desc":"Madura e elegante"},
    "Gigi (Feminina Descontraída)":   {"voice_id":"jBpfuIE2acCmo8TfEwPz", "gender":"F","desc":"Descontraída, casual"},
    "Glinda (Feminina Cálida)":       {"voice_id":"z9fAnlkpzviPz146aGWa", "gender":"F","desc":"Cálida e amigável"},
    "Adam (Masculino Profundo)":      {"voice_id":"pNInz6obpgDQGcFmaJgB", "gender":"M","desc":"Grave e autoritário"},
    "Antoni (Masculino Natural)":     {"voice_id":"ErXwobaYiN019PkySvjV", "gender":"M","desc":"Bem balanceado"},
    "Arnold (Masculino Crisp)":       {"voice_id":"VR6AewLTigWG4xSOukaG", "gender":"M","desc":"Nítido e firme"},
    "Callum (Masculino Intenso)":     {"voice_id":"N2lVS1w4EtoT3dr4eOWO", "gender":"M","desc":"Intenso e dramático"},
    "Charlie (Masculino Casual)":     {"voice_id":"IKne3meq5aSn9XLyUdCD", "gender":"M","desc":"Casual, australiano"},
    "Clyde (Masculino Guerreiro)":    {"voice_id":"2EiwWnXFnvU5JabPnv8n", "gender":"M","desc":"Forte, gaming"},
    "Daniel (Masculino Narrador)":    {"voice_id":"onwK4e9ZLuTAKqWW03F9", "gender":"M","desc":"Voz de notícia britânica"},
    "Dave (Masculino Britânico)":     {"voice_id":"CYw3kZ02Hs0563khs1Fj", "gender":"M","desc":"Britânico, casual"},
    "Ethan (Masculino Sussurrado)":   {"voice_id":"g5CIjZEefAph4nQFvHAz", "gender":"M","desc":"Sussurrado e próximo"},
    "Fin (Masculino Irlandês)":       {"voice_id":"D38z5RcWu1voky8WS1ja", "gender":"M","desc":"Irlandês caloroso"},
    "Liam (Masculino Americano)":     {"voice_id":"TX3LPaxmHKxFdv7VOQHJ", "gender":"M","desc":"Americano jovem"},
    "Sam (Masculino Confiável)":      {"voice_id":"yoZ06aMxZJJ28mfd3POQ", "gender":"M","desc":"Confiável e direto"},
    "Serena (Feminina Premium)":      {"voice_id":"pMsXgVXv3BLzUgSXRplE", "gender":"F","desc":"Premium, sofisticada"},
    "Nicole (Feminina Sussurrada)":   {"voice_id":"piTKgcLEGmPE4e6mEKli", "gender":"F","desc":"Sussurrada e íntima"},
    "Patrick (Masculino Confiante)":  {"voice_id":"ODq5zmih8GrVes37Dizd", "gender":"M","desc":"Confiante, storytelling"},
}

# ─── Velocidades de fala ──────────────────────────────────────────────────────
TTS_RATE_PRESETS = {
    "Muito Lenta":  0.78,
    "Lenta":        0.88,
    "Normal":       1.00,
    "Rápida":       1.12,
    "Muito Rápida": 1.25,
    "Ultra Rápida": 1.45,
}

EDGE_TTS_RATE_MAP = {
    "Muito Lenta":  "-30%",
    "Lenta":        "-15%",
    "Normal":       "+0%",
    "Rápida":       "+15%",
    "Muito Rápida": "+30%",
    "Ultra Rápida": "+50%",
}

# ─── Presets de EQ ────────────────────────────────────────────────────────────
EQ_PRESETS = {
    "Nenhum":          "",
    "Presença vocal":  "equalizer=f=3000:width_type=o:width=1:g=4,equalizer=f=250:width_type=o:width=1:g=-2",
    "Brilho (airyness)":"treble=g=5:f=8000,treble=g=3:f=12000",
    "Grave profundo":  "bass=g=8:f=100,bass=g=4:f=200",
    "Radio/telefone":  "highpass=f=300,lowpass=f=3400,equalizer=f=1200:width_type=o:width=1:g=4",
    "Podcast warmth":  "bass=g=3:f=180,equalizer=f=2500:width_type=o:width=1:g=2,treble=g=-1:f=10000",
    "Narrador cinema": "bass=g=4:f=100,equalizer=f=3000:width_type=o:width=1:g=3,treble=g=2:f=7000",
    "Megafone":        "highpass=f=800,lowpass=f=2800,equalizer=f=1500:width_type=o:width=1:g=6",
    "Voz dramática":   "bass=g=6:f=80,equalizer=f=400:width_type=o:width=1:g=-3,equalizer=f=3500:width_type=o:width=1:g=5",
    "Lo-fi vocal":     "highpass=f=200,lowpass=f=6000,equalizer=f=800:width_type=o:width=1:g=3",
}

# ─── Presets de reverb ────────────────────────────────────────────────────────
REVERB_PRESETS = {
    "Sem reverb":       None,
    "Sala pequena":     "aecho=0.8:0.9:40:0.3",
    "Sala média":       "aecho=0.8:0.88:60:0.4",
    "Sala grande":      "aecho=0.8:0.85:100:0.5",
    "Auditório":        "aecho=0.8:0.82:200:0.6",
    "Catedral":         "aecho=0.8:0.78:400:0.7",
    "Quarto (íntimo)":  "aecho=0.9:0.95:25:0.2",
    "Caverna":          "aecho=0.7:0.75:500:0.65",
    "Estúdio dry":      "aecho=0.85:0.92:30:0.15",
}

# ─── Templates de texto ───────────────────────────────────────────────────────
TTS_TEXT_TEMPLATES = [
    ("Vazio", ""),
    ("Apresentação curta",
     "Olá! Seja muito bem-vindo ao nosso canal. Não se esqueça de se inscrever e ativar o sininho!"),
    ("Call to action",
     "Aproveite essa oportunidade incrível! Clique no link da bio e garanta o seu agora, antes que acabe!"),
    ("Narração de produto",
     "Apresentamos o produto revolucionário que vai transformar a sua rotina. Tecnologia de ponta, resultado garantido."),
    ("Intro podcast",
     "Você está ouvindo o nosso podcast. Hoje vamos falar sobre um tema que vai mudar a sua perspectiva. Fique com a gente!"),
    ("Encerramento vídeo",
     "É isso por hoje! Se gostou do conteúdo, deixe seu like e compartilhe com os amigos. Até o próximo vídeo!"),
    ("Short EN — Hook",
     "Wait — before you scroll, you need to hear this. This one tip changed everything for me."),
    ("Short EN — CTA",
     "Drop a comment below and let me know what you think! And don't forget to follow for more content like this."),
    ("Anúncio produto BR",
     "Promoção imperdível só hoje! Até 70% de desconto em toda a linha. Não perca essa chance única!"),
    ("Narrador documentário",
     "Em um mundo onde tudo muda rapidamente, apenas os mais preparados sobrevivem. Esta é a história de quem não desistiu."),
]


# ═══════════════════════════════════════════════════════════════════════════════
#   GERAÇÃO TTS — MOTORES
# ═══════════════════════════════════════════════════════════════════════════════

def _atempo_chain(r):
    filters = []
    while r < 0.5:
        filters.append("atempo=0.5"); r /= 0.5
    while r > 2.0:
        filters.append("atempo=2.0"); r /= 2.0
    filters.append(f"atempo={r:.4f}")
    return ",".join(filters)


def _apply_ffmpeg_processing(input_path, output_wav,
                             pitch_factor=1.0,
                             rate_factor=1.0,
                             volume_db=0.0,
                             eq_filter="",
                             reverb_filter=None,
                             normalize=False,
                             compressor=False,
                             comp_threshold=-18.0,
                             comp_ratio=3.0,
                             comp_attack=20.0,
                             comp_release=200.0,
                             deesser=False,
                             stereo_width=1.0,
                             pitch_semitones=0.0):
    original_sr = 44100
    semitones_extra = pitch_semitones
    total_semitones = 12 * math.log2(max(pitch_factor, 0.1)) + semitones_extra
    rate_mult = 2 ** (total_semitones / 12)
    new_sr = int(original_sr * rate_mult)

    af_parts = [f"asetrate={new_sr}", f"aresample={original_sr}"]

    if abs(rate_factor - 1.0) > 0.01:
        af_parts.append(_atempo_chain(rate_factor))

    if compressor:
        thresh_lin = 10 ** (comp_threshold / 20.0)
        af_parts.append(
            f"acompressor=threshold={thresh_lin:.5f}:ratio={comp_ratio:.1f}"
            f":attack={comp_attack:.0f}:release={comp_release:.0f}:makeup=1"
        )

    if deesser:
        af_parts.append(
            "equalizer=f=6500:width_type=o:width=1.5:g=-4,"
            "equalizer=f=8000:width_type=o:width=1.2:g=-3"
        )

    if eq_filter:
        af_parts.append(eq_filter)

    if abs(volume_db) > 0.001 or volume_db <= -59.9:
        if volume_db <= -59.9:
            af_parts.append("volume=0")
        else:
            linear_gain = 10 ** (volume_db / 20.0)
            af_parts.append(f"volume={linear_gain:.6f}")

    if reverb_filter:
        af_parts.append(reverb_filter)

    if abs(stereo_width - 1.0) > 0.05:
        af_parts.append(f"extrastereo=m={stereo_width:.2f}")

    if normalize:
        af_parts.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    af_string = ",".join(af_parts)
    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", af_string,
        "-ar", "44100", "-ac", "2",
        output_wav
    ]
    r = subprocess.run(cmd, capture_output=True, creationflags=flags)

    if r.returncode != 0:
        cmd2 = ["ffmpeg", "-y", "-i", input_path, "-ar", "44100", "-ac", "2", output_wav]
        r2 = subprocess.run(cmd2, capture_output=True, creationflags=flags)
        if r2.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou:\n{r.stderr.decode(errors='replace')}")


def _generate_tts_gtts(text, voice_key, rate_preset, **proc_kwargs):
    from gtts import gTTS
    cfg = TTS_VOICES.get(voice_key, list(TTS_VOICES.values())[0])
    lang  = cfg["lang"]; tld   = cfg["tld"]
    pitch = cfg.get("pitch", 1.0)
    rate  = cfg.get("rate", 1.0) * TTS_RATE_PRESETS.get(rate_preset, 1.0)
    if not proc_kwargs.get("eq_filter"):
        proc_kwargs["eq_filter"] = cfg.get("eq", "")
    tmp_dir  = tempfile.mkdtemp(prefix="audiofix_gtts_")
    mp3_path = os.path.join(tmp_dir, "raw.mp3")
    wav_path = os.path.join(tmp_dir, "final.wav")
    slow_mode = (rate < 0.90)
    tts = gTTS(text=text, lang=lang, tld=tld, slow=slow_mode)
    tts.save(mp3_path)
    _apply_ffmpeg_processing(mp3_path, wav_path, pitch_factor=pitch, rate_factor=rate, **proc_kwargs)
    os.unlink(mp3_path)
    return wav_path


def _generate_tts_edge(text, voice_key, rate_preset, **proc_kwargs):
    import edge_tts
    cfg      = EDGE_TTS_VOICES.get(voice_key, list(EDGE_TTS_VOICES.values())[0])
    voice_id = cfg["voice_id"]
    edge_rate = EDGE_TTS_RATE_MAP.get(rate_preset, "+0%")
    tmp_dir  = tempfile.mkdtemp(prefix="audiofix_edge_")
    mp3_path = os.path.join(tmp_dir, "raw.mp3")
    wav_path = os.path.join(tmp_dir, "final.wav")
    async def _run():
        communicate = edge_tts.Communicate(text, voice_id, rate=edge_rate)
        await communicate.save(mp3_path)
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()
    except Exception as e:
        raise RuntimeError(f"Edge TTS falhou: {e}\nVerifique sua conexão com a internet.")
    if not os.path.isfile(mp3_path) or os.path.getsize(mp3_path) < 100:
        raise RuntimeError("Edge TTS: arquivo gerado está vazio. Verifique a conexão.")
    proc_kwargs_edge = dict(proc_kwargs)
    proc_kwargs_edge["pitch_factor"] = 1.0
    proc_kwargs_edge["rate_factor"] = 1.0
    _apply_ffmpeg_processing(mp3_path, wav_path, **proc_kwargs_edge)
    os.unlink(mp3_path)
    return wav_path


def _generate_tts_elevenlabs(text, voice_key, api_key,
                              stability=0.50, similarity=0.75,
                              style=0.0, use_speaker_boost=True,
                              **proc_kwargs):
    import requests as req
    if not api_key or len(api_key.strip()) < 20:
        raise ValueError("API key do ElevenLabs inválida ou vazia.\n"
                         "Obtenha em: https://elevenlabs.io → My Account → API Key")
    cfg      = ELEVENLABS_VOICES.get(voice_key, list(ELEVENLABS_VOICES.values())[0])
    voice_id = cfg["voice_id"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"Accept": "audio/mpeg","Content-Type": "application/json","xi-api-key": api_key.strip()}
    payload = {"text": text,"model_id": "eleven_multilingual_v2",
               "voice_settings": {"stability": max(0.0, min(1.0, stability)),
                                   "similarity_boost": max(0.0, min(1.0, similarity)),
                                   "style": max(0.0, min(1.0, style)),
                                   "use_speaker_boost": use_speaker_boost}}
    try:
        response = req.post(url, json=payload, headers=headers, timeout=60)
    except Exception as e:
        raise RuntimeError(f"Falha na conexão com ElevenLabs: {e}")
    if response.status_code == 401: raise ValueError("API key inválida.")
    if response.status_code == 422: raise ValueError("Texto inválido ou voz não encontrada.")
    if response.status_code == 429: raise RuntimeError("Limite de requisições atingido.")
    if response.status_code != 200: raise RuntimeError(f"ElevenLabs API erro {response.status_code}")
    tmp_dir  = tempfile.mkdtemp(prefix="audiofix_el_")
    mp3_path = os.path.join(tmp_dir, "raw.mp3")
    wav_path = os.path.join(tmp_dir, "final.wav")
    with open(mp3_path, "wb") as f: f.write(response.content)
    if os.path.getsize(mp3_path) < 500:
        raise RuntimeError("ElevenLabs retornou arquivo vazio.")
    proc_kwargs_el = dict(proc_kwargs)
    proc_kwargs_el["pitch_factor"] = 1.0
    proc_kwargs_el["rate_factor"]  = 1.0
    _apply_ffmpeg_processing(mp3_path, wav_path, **proc_kwargs_el)
    os.unlink(mp3_path)
    return wav_path


def generate_tts_wav(engine, text, voice_key, rate_preset="Normal",
                     volume_db=0.0, eq_filter="", reverb_filter=None,
                     normalize=False, compressor=False, comp_threshold=-18.0,
                     comp_ratio=3.0, comp_attack=20.0, comp_release=200.0,
                     deesser=False, stereo_width=1.0, pitch_semitones=0.0,
                     el_api_key="", el_stability=0.50, el_similarity=0.75, el_style=0.0):
    proc_kw = dict(volume_db=volume_db, eq_filter=eq_filter, reverb_filter=reverb_filter,
                   normalize=normalize, compressor=compressor, comp_threshold=comp_threshold,
                   comp_ratio=comp_ratio, comp_attack=comp_attack, comp_release=comp_release,
                   deesser=deesser, stereo_width=stereo_width, pitch_semitones=pitch_semitones)
    if engine == "gtts":       return _generate_tts_gtts(text, voice_key, rate_preset, **proc_kw)
    elif engine == "edge":     return _generate_tts_edge(text, voice_key, rate_preset, **proc_kw)
    elif engine == "elevenlabs":
        return _generate_tts_elevenlabs(text, voice_key, el_api_key,
                                        stability=el_stability, similarity=el_similarity,
                                        style=el_style, **proc_kw)
    else: raise ValueError(f"Motor desconhecido: {engine}")


# ─── Whisper ─────────────────────────────────────────────────────────────────
WHISPER_MODELS  = ["tiny", "base", "small", "medium", "large"]
WHISPER_LANGS   = {
    "Auto-detectar": None, "Português": "pt", "Inglês": "en", "Espanhol": "es",
    "Francês": "fr", "Alemão": "de", "Italiano": "it", "Japonês": "ja",
    "Coreano": "ko", "Chinês": "zh", "Russo": "ru", "Árabe": "ar",
}

def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600); m = int((seconds % 3600) // 60)
    s = int(seconds % 60);    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def _format_timestamp_srt(seconds: float) -> str:
    h = int(seconds // 3600); m = int((seconds % 3600) // 60)
    s = int(seconds % 60);    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def transcribe_video(video_path, model_name="base", language=None, progress_cb=None, log_cb=None):
    def log(m):
        if log_cb: log_cb(m)
    log("▶ Extraindo áudio para transcrição…")
    if progress_cb: progress_cb(5)
    with tempfile.TemporaryDirectory(prefix="audiofix_whisper_") as tmp:
        wav_path = os.path.join(tmp, "audio.wav")
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn",
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, creationflags=flags)
        if progress_cb: progress_cb(20)
        log(f"▶ Carregando modelo Whisper '{model_name}'…")
        segments = []
        if _is_importable("faster_whisper"):
            from faster_whisper import WhisperModel
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            log("▶ Transcrevendo…")
            if progress_cb: progress_cb(40)
            segs, info = model.transcribe(wav_path, language=language, beam_size=5)
            for seg in segs:
                segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
                if progress_cb: progress_cb(min(90, 40 + len(segments)))
        elif _is_importable("whisper"):
            import whisper
            model = whisper.load_model(model_name)
            log("▶ Transcrevendo…")
            if progress_cb: progress_cb(40)
            kwargs = {"language": language} if language else {}
            result = model.transcribe(wav_path, **kwargs)
            for seg in result.get("segments", []):
                segments.append({"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()})
        else:
            raise RuntimeError("Whisper não instalado.")
    if progress_cb: progress_cb(100)
    log(f"✅ Transcrição concluída — {len(segments)} segmentos.")
    return segments


# ─── Geradores de ruído ───────────────────────────────────────────────────────
def generate_pink_noise(n_samples, amplitude, seed=42):
    import numpy as np
    rng = np.random.default_rng(seed); n_rows = 16; pink = np.zeros(n_samples)
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
    fft = np.fft.rfft(white); freqs_hz = np.abs(np.fft.rfftfreq(n_samples)) * 44100; eps = 1e-6
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
    "Normal":   {"label":"Normal",   "desc":"Mudanças sutis · título leve · data próxima",       "color":"#4ade80","title_len":4,"artist_len":4,"album_len":3,"comment_len":6, "date_range":30,  "track_range":(1,20), "encoder_var":False},
    "Moderada": {"label":"Moderada", "desc":"Alterações médias · campos misturados",             "color":"#fbbf24","title_len":6,"artist_len":5,"album_len":4,"comment_len":9, "date_range":365, "track_range":(1,50), "encoder_var":True},
    "Intensa":  {"label":"Intensa",  "desc":"Metadados bem distintos · datas variadas",          "color":"#f97316","title_len":8,"artist_len":7,"album_len":6,"comment_len":12,"date_range":1095,"track_range":(1,99), "encoder_var":True},
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
            repeats = int(math.ceil(n / cw_len))
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
                    try: nd, dd = stream.get("r_frame_rate","0/1").split("/"); info["fps"] = round(int(nd)/int(dd),2)
                    except: info["fps"] = 0
                elif stream.get("codec_type") == "audio":
                    info["audio_codec"] = stream.get("codec_name","?"); info["sample_rate"] = stream.get("sample_rate","?")
                    info["channels"] = stream.get("channels",0)
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

class CollapsibleSection(tk.Frame):
    _HDR_BG     = "#111116"
    _HDR_BG_HOV = "#1a1a26"
    def __init__(self, parent, title, icon="", color=MUTED,
                 default_open=True, badge_text="", **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._open = default_open; self._color = color; self._badge_text = badge_text
        self._build(title, icon)
    def _build(self, title, icon):
        self._hdr = tk.Frame(self, bg=self._HDR_BG, cursor="hand2"); self._hdr.pack(fill="x")
        self._bar = tk.Frame(self._hdr, bg=self._color, width=3); self._bar.pack(side="left", fill="y")
        self._arrow = tk.Label(self._hdr, text="▼" if self._open else "▶",
                               font=("Segoe UI", 8, "bold"), bg=self._HDR_BG, fg=self._color, padx=8, pady=6)
        self._arrow.pack(side="left")
        full_title = f"{icon}  {title}" if icon else title
        self._title_lbl = tk.Label(self._hdr, text=full_title, font=FONT_BOLD,
                                   bg=self._HDR_BG, fg=TEXT, pady=6)
        self._title_lbl.pack(side="left", fill="x", expand=True)
        if self._badge_text:
            tk.Label(self._hdr, text=self._badge_text, font=FONT_SMALL,
                     bg=self._HDR_BG, fg=self._color, padx=6).pack(side="right")
        self._hint = tk.Label(self._hdr, text="" if self._open else "clique para expandir",
                              font=FONT_SMALL, bg=self._HDR_BG, fg=MUTED, padx=8)
        self._hint.pack(side="right")
        for w in (self._hdr, self._arrow, self._title_lbl, self._hint):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
        self._content = tk.Frame(self, bg=DARK)
        if self._open: self._content.pack(fill="x", pady=(1, 3))
    def _on_enter(self, e=None):
        for w in (self._hdr, self._arrow, self._title_lbl, self._hint):
            try: w.config(bg=self._HDR_BG_HOV)
            except: pass
    def _on_leave(self, e=None):
        for w in (self._hdr, self._arrow, self._title_lbl, self._hint):
            try: w.config(bg=self._HDR_BG)
            except: pass
    def _toggle(self, e=None):
        self._open = not self._open
        if self._open:
            self._content.pack(fill="x", pady=(1, 3)); self._arrow.config(text="▼"); self._hint.config(text="")
        else:
            self._content.pack_forget(); self._arrow.config(text="▶"); self._hint.config(text="clique para expandir")
    def open(self):
        if not self._open: self._toggle()
    def close(self):
        if self._open: self._toggle()
    @property
    def content(self): return self._content


class NoiseControl(tk.Frame):
    def __init__(self, parent, name, color, default_amp=0.0, **kwargs):
        super().__init__(parent, bg=CARD, padx=8, pady=6, **kwargs)
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
        self._slider.pack(fill="x", pady=(3,0)); self._toggle()
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
        hdr = tk.Frame(self, bg=CARD); hdr.pack(fill="x", pady=(0,6))
        tk.Label(hdr, text="📊  Nível de variação dos metadados:", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(side="left")
        self._desc_lbl = tk.Label(hdr, text="", font=FONT_SMALL, bg=CARD, fg=MUTED); self._desc_lbl.pack(side="right")
        btn_row = tk.Frame(self, bg=CARD); btn_row.pack(fill="x")
        for i in range(4): btn_row.columnconfigure(i, weight=1)
        for idx, level_name in enumerate(self.LEVELS):
            cfg = VARIATION_LEVELS[level_name]; col = cfg["color"]
            btn_outer = tk.Frame(btn_row, bg=MUTED, padx=1, pady=1)
            btn_outer.grid(row=0, column=idx, sticky="ew", padx=(0,3) if idx < 3 else 0)
            btn_inner = tk.Frame(btn_outer, bg=CARD, padx=6, pady=6, cursor="hand2")
            btn_inner.pack(fill="both", expand=True)
            name_lbl = tk.Label(btn_inner, text=cfg["label"], font=FONT_BOLD, bg=CARD, fg=TEXT); name_lbl.pack(anchor="center")
            line = tk.Frame(btn_inner, bg=col, height=2); line.pack(fill="x", pady=(3,0))
            rb = tk.Radiobutton(btn_inner, variable=self._level, value=level_name, bg=CARD,
                                activebackground=CARD, selectcolor="#111116", relief="flat", bd=0,
                                cursor="hand2", command=self._refresh)
            rb.pack(anchor="e")
            for w in [btn_outer, btn_inner, name_lbl, line]: w.bind("<Button-1>", lambda e, lv=level_name: self._select(lv))
            self._btns[level_name] = (btn_outer, btn_inner, name_lbl, line, rb)
        ex_card = tk.Frame(self, bg="#111116", padx=8, pady=6); ex_card.pack(fill="x", pady=(6,0))
        self._ex_title = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=ACC2); self._ex_title.pack(anchor="w")
        self._ex_date  = tk.Label(ex_card, text="", font=FONT_MONO, bg="#111116", fg=MUTED); self._ex_date.pack(anchor="w")
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
            except: pass
        self._desc_lbl.config(text=cfg["desc"], fg=cfg["color"])
        ex_meta = generate_metadata_variants(1, selected)[0]
        self._ex_title.config(text=f"  title:  {ex_meta['title']}")
        self._ex_date.config(text=f"  date:   {ex_meta['date']}")
    @property
    def level(self): return self._level.get()


class BatchQueueItem(tk.Frame):
    STATUS_PENDING   = "pending"
    STATUS_RUNNING   = "running"
    STATUS_DONE      = "done"
    STATUS_ERROR     = "error"
    STATUS_CANCELLED = "cancelled"
    STATUS_COLORS = {STATUS_PENDING: MUTED, STATUS_RUNNING: ACCENT, STATUS_DONE: GREEN, STATUS_ERROR: RED, STATUS_CANCELLED: WARN}
    STATUS_ICONS  = {STATUS_PENDING: "⏳", STATUS_RUNNING: "⚙️", STATUS_DONE: "✅", STATUS_ERROR: "❌", STATUS_CANCELLED: "⚠️"}
    def __init__(self, parent, video_path, on_remove=None, **kwargs):
        super().__init__(parent, bg=CARD, padx=8, pady=6, **kwargs)
        self.video_path = video_path; self.on_remove = on_remove
        self._status = self.STATUS_PENDING; self._output_path = None; self._error_msg = None
        self._build()
    def _build(self):
        self.config(relief="flat", bd=0)
        top = tk.Frame(self, bg=CARD); top.pack(fill="x")
        self._icon_lbl = tk.Label(top, text="⏳", font=("Segoe UI Emoji", 10), bg=CARD, fg=MUTED, width=3)
        self._icon_lbl.pack(side="left")
        name_frame = tk.Frame(top, bg=CARD); name_frame.pack(side="left", fill="x", expand=True, padx=(4,0))
        self._name_lbl = tk.Label(name_frame, text=os.path.basename(self.video_path), font=FONT_BOLD, bg=CARD, fg=TEXT, anchor="w")
        self._name_lbl.pack(anchor="w")
        dir_text = os.path.dirname(self.video_path)
        if len(dir_text) > 60: dir_text = "…" + dir_text[-57:]
        tk.Label(name_frame, text=dir_text, font=FONT_SMALL, bg=CARD, fg=MUTED, anchor="w").pack(anchor="w")
        self._remove_btn = tk.Button(top, text="✕", font=FONT_SMALL, bg="#2a1a1a", fg=RED,
                                     relief="flat", padx=6, pady=1, cursor="hand2", command=self._do_remove)
        self._remove_btn.pack(side="right")
        self._prog = ttk.Progressbar(self, mode="determinate", maximum=100, length=200)
        self._prog.pack(fill="x", pady=(4,0))
        self._status_lbl = tk.Label(self, text="Na fila…", font=FONT_STATUS, bg=CARD, fg=MUTED, anchor="w")
        self._status_lbl.pack(anchor="w", pady=(1,0))
        tk.Frame(self, bg="#2a2a35", height=1).pack(fill="x", pady=(6,0))
    def _do_remove(self):
        if self._status == self.STATUS_RUNNING: return
        if self.on_remove: self.on_remove(self)
    def set_status(self, status, message="", progress=None):
        self._status = status
        color = self.STATUS_COLORS.get(status, MUTED); icon = self.STATUS_ICONS.get(status, "•")
        self._icon_lbl.config(text=icon, fg=color); self._status_lbl.config(text=message or status, fg=color)
        self._name_lbl.config(fg=TEXT if status != self.STATUS_CANCELLED else MUTED)
        if progress is not None:
            self._prog.config(mode="indeterminate" if progress < 0 else "determinate")
            if progress >= 0: self._prog.config(value=progress)
            else: self._prog.start(12)
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


class BatchQueuePanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._items: list[BatchQueueItem] = []; self._build()
    def _build(self):
        hdr = tk.Frame(self, bg=DARK); hdr.pack(fill="x", pady=(0,6))
        tk.Label(hdr, text="📂  Fila de Vídeos", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(side="left")
        self._count_lbl = tk.Label(hdr, text="0 vídeos", font=FONT_SMALL, bg=DARK, fg=MUTED)
        self._count_lbl.pack(side="left", padx=(8,0))
        btn_row = tk.Frame(hdr, bg=DARK); btn_row.pack(side="right")
        tk.Button(btn_row, text="➕  Adicionar vídeos", font=FONT_LABEL, bg=ACCENT, fg="white",
                  activebackground=ACC2, relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._browse_add).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="📁  Adicionar pasta", font=FONT_LABEL, bg="#2a2a35", fg=ACC2,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._browse_folder).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="🗑  Limpar fila", font=FONT_LABEL, bg="#2a1a1a", fg=RED,
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._clear_queue).pack(side="left")
        self._drop_zone = tk.Frame(self, bg="#1a1a22", relief="flat", bd=0); self._drop_zone.pack(fill="x", pady=(0,6))
        self._drop_lbl = tk.Label(self._drop_zone,
            text="🎬  Arraste vídeos aqui  ou  clique em 'Adicionar vídeos'",
            font=("Segoe UI", 9), bg="#1a1a22", fg=MUTED, pady=14)
        self._drop_lbl.pack()
        self._setup_dnd()
        outer = tk.Frame(self, bg=DARK); outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0, height=240)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self._canvas.pack(side="left", fill="both", expand=True)
        self._list_frame = tk.Frame(self._canvas, bg=DARK)
        self._win_id = self._canvas.create_window((0,0), window=self._list_frame, anchor="nw")
        self._list_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._win_id, width=e.width))
        self._canvas.bind_all("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        stats = tk.Frame(self, bg=CARD, padx=10, pady=6); stats.pack(fill="x", pady=(6,0))
        stats.columnconfigure((0,1,2,3), weight=1)
        self._stat_total   = self._stat_cell(stats, 0, "Total",      "0", TEXT)
        self._stat_pending = self._stat_cell(stats, 1, "Na fila",    "0", MUTED)
        self._stat_done    = self._stat_cell(stats, 2, "Concluídos", "0", GREEN)
        self._stat_error   = self._stat_cell(stats, 3, "Com erro",   "0", RED)
    def _stat_cell(self, parent, col, label, value, color):
        frame = tk.Frame(parent, bg=CARD); frame.grid(row=0, column=col, sticky="ew", padx=4)
        val_lbl = tk.Label(frame, text=value, font=("Segoe UI",13,"bold"), bg=CARD, fg=color); val_lbl.pack()
        tk.Label(frame, text=label, font=FONT_SMALL, bg=CARD, fg=MUTED).pack(); return val_lbl
    def _setup_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self._drop_zone.drop_target_register(DND_FILES)
            self._drop_zone.dnd_bind("<<Drop>>", self._on_drop)
            self._drop_lbl.config(text="🎬  Arraste vídeos aqui  (ou clique em 'Adicionar vídeos')", fg=CYAN)
        except: pass
    def _on_drop(self, event):
        import re
        files = re.findall(r'\{([^}]+)\}|(\S+)', event.data)
        for match in files:
            path = match[0] or match[1]
            if path and os.path.isfile(path): self.add_video(path)
    def _browse_add(self):
        paths = filedialog.askopenfilenames(title="Selecionar vídeo(s)",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("Todos","*.*")])
        for p in paths: self.add_video(p)
    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Selecionar pasta com vídeos")
        if not folder: return
        VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".webm",".flv",".ts",".m4v"}; added = 0
        for f in sorted(os.listdir(folder)):
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                self.add_video(os.path.join(folder, f)); added += 1
        if added == 0: messagebox.showinfo("Pasta vazia", "Nenhum vídeo encontrado na pasta selecionada.")
    def _clear_queue(self):
        if any(i.status == BatchQueueItem.STATUS_RUNNING for i in self._items):
            messagebox.showwarning("Processamento em andamento", "Aguarde o processamento atual terminar."); return
        for item in list(self._items): item.destroy()
        self._items.clear(); self._update_stats()
    def add_video(self, path):
        if path in [i.video_path for i in self._items]: return
        item = BatchQueueItem(self._list_frame, video_path=path, on_remove=self._remove_item)
        item.pack(fill="x", padx=4, pady=(0,3))
        self._items.append(item); self._update_stats(); self._drop_zone.pack_forget()
    def _remove_item(self, item):
        item.destroy(); self._items.remove(item); self._update_stats()
        if not self._items: self._drop_zone.pack(fill="x", pady=(0,6))
    def _update_stats(self):
        total = len(self._items); pending = sum(1 for i in self._items if i.status == BatchQueueItem.STATUS_PENDING)
        done = sum(1 for i in self._items if i.status == BatchQueueItem.STATUS_DONE)
        errors = sum(1 for i in self._items if i.status == BatchQueueItem.STATUS_ERROR)
        self._count_lbl.config(text=f"{total} vídeo{'s' if total != 1 else ''}")
        self._stat_total.config(text=str(total)); self._stat_pending.config(text=str(pending))
        self._stat_done.config(text=str(done))
        self._stat_error.config(text=str(errors), fg=RED if errors > 0 else MUTED)
    def get_pending_items(self):
        return [i for i in self._items if i.status in (BatchQueueItem.STATUS_PENDING, BatchQueueItem.STATUS_ERROR)]
    def get_all_items(self): return list(self._items)
    def has_videos(self):    return len(self._items) > 0
    def update_stats(self):  self._update_stats()


# ═══════════════════════════════════════════════════════════════════════════════
#   PAINEL TTS
# ═══════════════════════════════════════════════════════════════════════════════

class TTSPanel(tk.Frame):
    _BG     = "#0a0a14"
    _BG_HDR = "#14141f"
    _BG_HOV = "#1c1c2e"
    _BG_SEC = "#12121c"

    ENGINE_COLORS = {"gtts": MUTED, "edge": CYAN, "elevenlabs": GOLD}
    ENGINE_LABELS = {"gtts": "gTTS", "edge": "Edge TTS ✨", "elevenlabs": "ElevenLabs ⭐"}

    def __init__(self, parent, on_wav_ready=None, bg=CARD, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.on_wav_ready  = on_wav_ready
        self._bg           = bg
        self._last_wav     = None
        self._preview_proc = None
        self._engine       = tk.StringVar(value="edge")
        self._expanded     = False
        self._build()

    def _build(self):
        bg = self._bg
        hdr = tk.Frame(self, bg=bg); hdr.pack(fill="x")
        self._toggle_btn = tk.Button(
            hdr, text="🎙  ▶  Gerar voz (TTS) para Copy White",
            font=FONT_BOLD, bg=self._BG_HDR, fg=PURPLE,
            relief="flat", padx=10, pady=6, cursor="hand2",
            anchor="w", command=self._toggle)
        self._toggle_btn.pack(side="left", fill="x", expand=True)
        status_frame = tk.Frame(hdr, bg=bg); status_frame.pack(side="right", padx=6)
        self._badge_gtts = tk.Label(status_frame, font=FONT_SMALL, bg=bg,
            text="gTTS ✔" if _GTTS_OK else "gTTS ✖", fg=GREEN if _GTTS_OK else RED)
        self._badge_gtts.pack(side="left", padx=(0,4))
        self._badge_edge = tk.Label(status_frame, font=FONT_SMALL, bg=bg,
            text="Edge ✔" if _EDGE_TTS_OK else "Edge —", fg=CYAN if _EDGE_TTS_OK else MUTED)
        self._badge_edge.pack(side="left", padx=(0,4))
        self._badge_el = tk.Label(status_frame, font=FONT_SMALL, bg=bg, text="ElevenLabs —", fg=MUTED)
        self._badge_el.pack(side="left")
        self._body = tk.Frame(self, bg=self._BG, padx=12, pady=10)
        self._build_engine_selector()
        self._build_templates()
        self._build_text_area()
        self._build_voice_selector()
        self._build_speed_row()
        self._build_wav_processing()
        self._build_volume_section()
        self._build_action_buttons()
        self._build_wav_info()
        self._on_engine_change()

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(anchor="w", pady=(6,3))

    def _build_engine_selector(self):
        row = tk.Frame(self._body, bg=self._BG); row.pack(fill="x", pady=(0,10))
        row.columnconfigure(0, weight=1); row.columnconfigure(1, weight=1); row.columnconfigure(2, weight=1)
        self._engine_btns = {}
        for idx, (engine_key, label) in enumerate([
            ("gtts",       "🅶  gTTS\nGoogle · gratuito"),
            ("edge",       "🅴  Edge TTS ✨\nNeural · gratuito"),
            ("elevenlabs", "🅴  ElevenLabs ⭐\nHumano · API key"),
        ]):
            color = self.ENGINE_COLORS[engine_key]
            outer = tk.Frame(row, bg=MUTED, padx=1, pady=1)
            outer.grid(row=0, column=idx, sticky="ew", padx=(0,4) if idx < 2 else 0)
            inner = tk.Frame(outer, bg=self._BG_SEC, padx=8, pady=8, cursor="hand2")
            inner.pack(fill="both", expand=True)
            lbl = tk.Label(inner, text=label, font=("Segoe UI", 8, "bold"),
                           bg=self._BG_SEC, fg=TEXT, justify="center")
            lbl.pack(anchor="center")
            bar = tk.Frame(inner, bg=color, height=2); bar.pack(fill="x", pady=(4,0))
            for w in [outer, inner, lbl, bar]:
                w.bind("<Button-1>", lambda e, k=engine_key: self._select_engine(k))
            self._engine_btns[engine_key] = (outer, inner, lbl, bar)
        install_row = tk.Frame(self._body, bg=self._BG); install_row.pack(fill="x", pady=(0,4))
        tk.Button(install_row, text="⬇  Instalar Edge TTS", font=FONT_SMALL,
                  bg="#0d1a14", fg=CYAN, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=self._install_edge_tts).pack(side="left")
        tk.Button(install_row, text="⬇  Instalar gTTS", font=FONT_SMALL,
                  bg="#0d0d1a", fg=MUTED, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=self._install_gtts).pack(side="left", padx=(4,0))
        self._install_lbl = tk.Label(install_row, text="", font=FONT_SMALL, bg=self._BG, fg=GREEN)
        self._install_lbl.pack(side="left", padx=(8,0))

    def _build_templates(self):
        row = tk.Frame(self._body, bg=self._BG); row.pack(fill="x", pady=(0,4))
        tk.Label(row, text="📋  Template:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(side="left")
        self._tmpl_var = tk.StringVar(value=TTS_TEXT_TEMPLATES[0][0])
        tmpl_cb = ttk.Combobox(row, textvariable=self._tmpl_var,
                               values=[t[0] for t in TTS_TEXT_TEMPLATES],
                               state="readonly", width=22, font=FONT_LABEL)
        tmpl_cb.pack(side="left", padx=(6,0))
        tmpl_cb.bind("<<ComboboxSelected>>", self._apply_template)
        tk.Button(row, text="Aplicar", font=FONT_LABEL, bg=CARD2, fg=PURPLE,
                  relief="flat", padx=6, pady=1, cursor="hand2",
                  command=self._apply_template).pack(side="left", padx=(4,0))
        tk.Button(row, text="🗑 Limpar", font=FONT_LABEL, bg="#2a1a1a", fg=RED,
                  relief="flat", padx=6, pady=1, cursor="hand2",
                  command=lambda: [self._txt.delete("1.0","end"), self._update_char_count()]
                  ).pack(side="left", padx=(4,0))
        self._char_lbl = tk.Label(row, text="0 chars", font=FONT_SMALL, bg=self._BG, fg=MUTED)
        self._char_lbl.pack(side="right")

    def _build_text_area(self):
        tk.Label(self._body, text="Texto para narrar:", font=FONT_BOLD,
                 bg=self._BG, fg=MUTED).pack(anchor="w", pady=(0,3))
        self._txt = tk.Text(self._body, height=4, font=("Consolas", 9),
                            bg="#100d1e", fg=TEXT, insertbackground=PURPLE,
                            relief="flat", bd=1, wrap="word",
                            selectbackground=ACCENT, selectforeground="white")
        self._txt.pack(fill="x", pady=(0,8))
        self._txt.bind("<KeyRelease>", self._update_char_count)

    def _build_voice_selector(self):
        vf = tk.Frame(self._body, bg=self._BG); vf.pack(fill="x", pady=(0,4))
        vf.columnconfigure(0, weight=3); vf.columnconfigure(1, weight=1); vf.columnconfigure(2, weight=1)
        vc = tk.Frame(vf, bg=self._BG); vc.grid(row=0, column=0, sticky="ew", padx=(0,8))
        tk.Label(vc, text="🎤  Voz:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(anchor="w")
        self._voice_var = tk.StringVar()
        self._voice_cb = ttk.Combobox(vc, textvariable=self._voice_var,
                                      state="readonly", width=36, font=FONT_LABEL)
        self._voice_cb.pack(fill="x", pady=(2,0))
        self._voice_cb.bind("<<ComboboxSelected>>", self._on_voice_change)
        gc = tk.Frame(vf, bg=self._BG); gc.grid(row=0, column=1, sticky="ew", padx=(0,8))
        tk.Label(gc, text="⚡  Gênero:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(anchor="w")
        self._gender_filter = tk.StringVar(value="Todos")
        gf_cb = ttk.Combobox(gc, textvariable=self._gender_filter,
                              values=["Todos", "♀ Femininas", "♂ Masculinas"],
                              state="readonly", width=14, font=FONT_LABEL)
        gf_cb.pack(fill="x", pady=(2,0))
        gf_cb.bind("<<ComboboxSelected>>", self._filter_voices)
        lc = tk.Frame(vf, bg=self._BG); lc.grid(row=0, column=2, sticky="ew")
        tk.Label(lc, text="🌐  Idioma:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(anchor="w")
        self._lang_filter = tk.StringVar(value="Todos")
        self._lang_cb = ttk.Combobox(lc, textvariable=self._lang_filter,
                                     state="readonly", width=16, font=FONT_LABEL)
        self._lang_cb.pack(fill="x", pady=(2,0))
        self._lang_cb.bind("<<ComboboxSelected>>", self._filter_voices)
        self._voice_badge = tk.Label(self._body, text="", font=FONT_SMALL,
                                     bg=self._BG, fg=ACC2, anchor="w")
        self._voice_badge.pack(anchor="w", pady=(2,6))

    def _build_speed_row(self):
        row = tk.Frame(self._body, bg=self._BG); row.pack(fill="x", pady=(0,8))
        tk.Label(row, text="⏱  Velocidade:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(side="left")
        self._rate_var = tk.StringVar(value="Normal")
        rate_cb = ttk.Combobox(row, textvariable=self._rate_var,
                               values=list(TTS_RATE_PRESETS.keys()),
                               state="readonly", width=14, font=FONT_LABEL)
        rate_cb.pack(side="left", padx=(6,0))
        tk.Label(row, text="   🎵  Pitch fino:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(side="left")
        self._pitch_st_var = tk.DoubleVar(value=0.0)
        self._pitch_st_lbl = tk.Label(row, text="  0.0 st",
                                      font=("Segoe UI", 9, "bold"), bg=self._BG, fg=PURPLE, width=8)
        self._pitch_st_lbl.pack(side="left")
        pitch_slider = ttk.Scale(row, from_=-12.0, to=12.0,
                                 variable=self._pitch_st_var, orient="horizontal",
                                 command=self._on_pitch_slide, length=140)
        pitch_slider.pack(side="left", padx=(4,0))
        tk.Button(row, text="Reset", font=FONT_SMALL, bg=CARD2, fg=MUTED,
                  relief="flat", padx=4, pady=1, cursor="hand2",
                  command=lambda: [self._pitch_st_var.set(0.0),
                                   self._pitch_st_lbl.config(text="  0.0 st")]
                  ).pack(side="left", padx=(4,0))

    def _build_wav_processing(self):
        sec = tk.Frame(self._body, bg=self._BG_SEC, padx=10, pady=8)
        sec.pack(fill="x", pady=(0,8))
        tk.Label(sec, text="⚙️  Processamento WAV", font=FONT_BOLD, bg=self._BG_SEC, fg=MUTED).pack(anchor="w", pady=(0,6))
        grid = tk.Frame(sec, bg=self._BG_SEC); grid.pack(fill="x")
        grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1)
        eq_col = tk.Frame(grid, bg=self._BG_SEC); eq_col.grid(row=0, column=0, sticky="ew", padx=(0,8), pady=(0,6))
        tk.Label(eq_col, text="🎚  EQ Preset:", font=FONT_BOLD, bg=self._BG_SEC, fg=MUTED).pack(anchor="w")
        self._eq_var = tk.StringVar(value="Nenhum")
        eq_cb = ttk.Combobox(eq_col, textvariable=self._eq_var,
                              values=list(EQ_PRESETS.keys()), state="readonly", width=22, font=FONT_LABEL)
        eq_cb.pack(fill="x", pady=(2,0))
        rev_col = tk.Frame(grid, bg=self._BG_SEC); rev_col.grid(row=0, column=1, sticky="ew", pady=(0,6))
        tk.Label(rev_col, text="🏠  Ambiente/Reverb:", font=FONT_BOLD, bg=self._BG_SEC, fg=MUTED).pack(anchor="w")
        self._reverb_var = tk.StringVar(value="Sem reverb")
        rev_cb = ttk.Combobox(rev_col, textvariable=self._reverb_var,
                               values=list(REVERB_PRESETS.keys()), state="readonly", width=22, font=FONT_LABEL)
        rev_cb.pack(fill="x", pady=(2,0))
        eff_row = tk.Frame(sec, bg=self._BG_SEC); eff_row.pack(fill="x", pady=(0,6))
        self._deesser_var  = tk.BooleanVar(value=False)
        self._norm_var     = tk.BooleanVar(value=False)
        self._comp_var     = tk.BooleanVar(value=False)
        for var, label, color in [
            (self._deesser_var, "De-esser (reduz sibilância)", TEAL),
            (self._norm_var,    "Normalizar EBU R128",         GREEN),
            (self._comp_var,    "Compressor dinâmico",         ORANGE),
        ]:
            tk.Checkbutton(eff_row, variable=var, text=label, font=FONT_LABEL,
                           bg=self._BG_SEC, fg=color, selectcolor="#0a0a14",
                           activebackground=self._BG_SEC, relief="flat", cursor="hand2",
                           command=self._toggle_comp_panel).pack(side="left", padx=(0,16))
        self._comp_panel = tk.Frame(sec, bg="#0d1020", padx=10, pady=8)
        self._comp_threshold = tk.DoubleVar(value=-18.0)
        self._comp_ratio     = tk.DoubleVar(value=3.0)
        self._comp_attack    = tk.DoubleVar(value=20.0)
        self._comp_release   = tk.DoubleVar(value=200.0)
        cp = self._comp_panel
        tk.Label(cp, text="Configurações do Compressor", font=FONT_BOLD, bg="#0d1020", fg=ORANGE).pack(anchor="w", pady=(0,4))
        comp_grid = tk.Frame(cp, bg="#0d1020"); comp_grid.pack(fill="x")
        comp_grid.columnconfigure(0, weight=1); comp_grid.columnconfigure(1, weight=1)
        self._comp_sliders = []
        params = [
            ("Threshold (dB)", self._comp_threshold, -60.0, 0.0,   ORANGE, "{:.1f} dB", 0, 0),
            ("Ratio",          self._comp_ratio,      1.0,  20.0,  ORANGE, "{:.1f}:1",  0, 1),
            ("Attack (ms)",    self._comp_attack,     1.0,  200.0, WARN,   "{:.0f} ms", 1, 0),
            ("Release (ms)",   self._comp_release,    10.0, 2000.0,WARN,   "{:.0f} ms", 1, 1),
        ]
        for label, var, from_, to, color, fmt, r, c in params:
            col_frame = tk.Frame(comp_grid, bg="#0d1020", padx=(0 if c==0 else 8))
            col_frame.grid(row=r, column=c, sticky="ew", padx=(0,8) if c==0 else 0, pady=2)
            hdr_row = tk.Frame(col_frame, bg="#0d1020"); hdr_row.pack(fill="x")
            tk.Label(hdr_row, text=label, font=FONT_SMALL, bg="#0d1020", fg=MUTED).pack(side="left")
            val_lbl = tk.Label(hdr_row, text=fmt.format(var.get()), font=FONT_BOLD,
                               bg="#0d1020", fg=color, width=10)
            val_lbl.pack(side="right")
            sl = ttk.Scale(col_frame, from_=from_, to=to, variable=var, orient="horizontal",
                           command=lambda v, lbl=val_lbl, f=fmt: lbl.config(text=f.format(float(v))))
            sl.pack(fill="x"); self._comp_sliders.append(sl)
        sw_row = tk.Frame(sec, bg=self._BG_SEC); sw_row.pack(fill="x", pady=(4,0))
        tk.Label(sw_row, text="↔  Largura estéreo:", font=FONT_BOLD, bg=self._BG_SEC, fg=MUTED).pack(side="left")
        self._sw_var = tk.DoubleVar(value=1.0)
        self._sw_lbl = tk.Label(sw_row, text="Normal (1.0×)", font=("Segoe UI", 9, "bold"),
                                bg=self._BG_SEC, fg=INDIGO, width=18)
        self._sw_lbl.pack(side="left", padx=(6,0))
        for label, val in [("Mono","0.0"), ("Normal","1.0"), ("Wide","1.5"), ("Ultra","2.0")]:
            tk.Button(sw_row, text=label, font=FONT_SMALL, bg=CARD2, fg=MUTED,
                      relief="flat", padx=4, pady=1, cursor="hand2",
                      command=lambda v=val: [self._sw_var.set(float(v)), self._update_sw_label()]
                      ).pack(side="left", padx=(2,0))
        sw_slider = ttk.Scale(sw_row, from_=0.0, to=2.0, variable=self._sw_var,
                              orient="horizontal", command=lambda v: self._update_sw_label(), length=120)
        sw_slider.pack(side="left", padx=(8,0))

    def _build_volume_section(self):
        vol_frame = tk.Frame(self._body, bg=self._BG); vol_frame.pack(fill="x", pady=(0,8))
        vol_hdr = tk.Frame(vol_frame, bg=self._BG); vol_hdr.pack(fill="x")
        tk.Label(vol_hdr, text="🔊  Volume:", font=FONT_BOLD, bg=self._BG, fg=MUTED).pack(side="left")
        self._vol_lbl = tk.Label(vol_hdr, text="  0.0 dB", font=("Segoe UI", 9, "bold"),
                                 bg=self._BG, fg=PURPLE, width=12)
        self._vol_lbl.pack(side="left")
        self._mute_btn = tk.Button(vol_hdr, text="🔇 MUDO", font=("Segoe UI", 8, "bold"),
                                    bg="#1a0a0a", fg=RED, relief="flat", padx=6, pady=2,
                                    cursor="hand2", command=lambda: self._set_volume(-60.0))
        self._mute_btn.pack(side="left", padx=(8,0))
        for label, val in [("-40",-40),("-20",-20),("-10",-10),("  0",0),("+6",6),("+12",12),("+20",20),("+30",30),("+40",40)]:
            tk.Button(vol_hdr, text=label, font=FONT_SMALL, bg=CARD2, fg=MUTED, relief="flat",
                      padx=4, pady=1, cursor="hand2",
                      command=lambda v=val: self._set_volume(float(v))).pack(side="left", padx=(2,0))
        self._vol_var = tk.DoubleVar(value=0.0)
        vol_slider = ttk.Scale(vol_frame, from_=-60.0, to=40.0, variable=self._vol_var,
                               orient="horizontal", command=self._on_vol_slide)
        vol_slider.pack(fill="x", pady=(4,0))
        marks = tk.Frame(vol_frame, bg=self._BG); marks.pack(fill="x")
        for txt, side, expand in [("-60 dB\n(MUDO)","left",False),("-40 dB","left",True),
                                   ("-20 dB","left",True),("0 dB","left",True),
                                   ("+20 dB","left",True),("+40 dB\n(MAX)","right",False)]:
            tk.Label(marks, text=txt, font=FONT_SMALL, bg=self._BG, fg=MUTED, justify="center"
                     ).pack(side=side, expand=expand)

    def _build_action_buttons(self):
        bot = tk.Frame(self._body, bg=self._BG); bot.pack(fill="x", pady=(4,0))
        self._gen_btn = tk.Button(bot, text="✨  Gerar WAV", font=("Segoe UI", 9, "bold"),
                                   bg=PURPLE, fg="white", activebackground=ACC2,
                                   relief="flat", padx=14, pady=6, cursor="hand2", command=self._run_tts)
        self._gen_btn.pack(side="left")
        self._preview_btn = tk.Button(bot, text="▶  Preview", font=FONT_LABEL, bg=TEAL, fg=DARK,
                                       relief="flat", padx=10, pady=6, cursor="hand2",
                                       command=self._preview_wav, state="disabled")
        self._preview_btn.pack(side="left", padx=(6,0))
        self._stop_btn = tk.Button(bot, text="⏹", font=FONT_LABEL, bg="#2a1a1a", fg=RED,
                                    relief="flat", padx=8, pady=6, cursor="hand2",
                                    command=self._stop_preview, state="disabled")
        self._stop_btn.pack(side="left", padx=(4,0))
        self._save_btn = tk.Button(bot, text="💾  Salvar WAV", font=FONT_LABEL, bg=CARD2, fg=GREEN,
                                    relief="flat", padx=8, pady=6, cursor="hand2",
                                    command=self._save_wav, state="disabled")
        self._save_btn.pack(side="left", padx=(4,0))
        self._copy_btn = tk.Button(bot, text="📋  Copiar path", font=FONT_LABEL, bg=CARD2, fg=MUTED,
                                    relief="flat", padx=8, pady=6, cursor="hand2",
                                    command=self._copy_path, state="disabled")
        self._copy_btn.pack(side="left", padx=(4,0))
        self._status_lbl = tk.Label(bot, text="", font=FONT_STATUS, bg=self._BG, fg=MUTED)
        self._status_lbl.pack(side="left", padx=(10,0))
        self._el_frame = tk.Frame(self._body, bg=self._BG)
        el_row = tk.Frame(self._el_frame, bg=self._BG); el_row.pack(fill="x", pady=(6,0))
        tk.Label(el_row, text="🔑  ElevenLabs API Key:", font=FONT_BOLD, bg=self._BG, fg=GOLD).pack(side="left")
        self._el_key_var = tk.StringVar()
        self._el_key_entry = tk.Entry(el_row, textvariable=self._el_key_var, font=FONT_MONO,
                                      bg="#1a1408", fg=GOLD, insertbackground=GOLD, show="•",
                                      relief="flat", bd=1, width=40)
        self._el_key_entry.pack(side="left", padx=(8,0), fill="x", expand=True)
        tk.Button(el_row, text="👁", font=FONT_SMALL, bg=CARD2, fg=GOLD, relief="flat", padx=4,
                  cursor="hand2", command=self._toggle_key_vis).pack(side="left", padx=(4,0))
        tk.Label(el_row, text="  Obter em elevenlabs.io → grátis 10k chars/mês",
                 font=FONT_SMALL, bg=self._BG, fg=MUTED).pack(side="left")
        el_params = tk.Frame(self._el_frame, bg=self._BG); el_params.pack(fill="x", pady=(4,0))
        self._el_stability  = tk.DoubleVar(value=0.50)
        self._el_similarity = tk.DoubleVar(value=0.75)
        self._el_style      = tk.DoubleVar(value=0.0)
        for label, var, from_, to, color in [
            ("Stability", self._el_stability, 0.0, 1.0, GOLD),
            ("Similarity", self._el_similarity, 0.0, 1.0, WARN),
            ("Style exag.", self._el_style, 0.0, 1.0, ORANGE),
        ]:
            col = tk.Frame(el_params, bg=self._BG); col.pack(side="left", expand=True, fill="x", padx=(0,8))
            hrow = tk.Frame(col, bg=self._BG); hrow.pack(fill="x")
            tk.Label(hrow, text=label, font=FONT_SMALL, bg=self._BG, fg=MUTED).pack(side="left")
            vl = tk.Label(hrow, text=f"{var.get():.2f}", font=FONT_SMALL, bg=self._BG, fg=color, width=5)
            vl.pack(side="right")
            ttk.Scale(col, from_=from_, to=to, variable=var, orient="horizontal",
                      command=lambda v, lbl=vl: lbl.config(text=f"{float(v):.2f}")).pack(fill="x")

    def _build_wav_info(self):
        self._wav_info = tk.Label(self._body, text="", font=FONT_MONO, bg=self._BG, fg=TEAL,
                                   anchor="w", wraplength=700, justify="left")
        self._wav_info.pack(anchor="w", pady=(4,0))

    def _select_engine(self, key):
        self._engine.set(key); self._on_engine_change()

    def _on_engine_change(self, *_):
        engine = self._engine.get(); color = self.ENGINE_COLORS[engine]
        for k, (outer, inner, lbl, bar) in self._engine_btns.items():
            is_sel = (k == engine); ec = self.ENGINE_COLORS[k]
            if is_sel:
                outer.config(bg=ec); inner.config(bg=self._BG_HDR)
                lbl.config(bg=self._BG_HDR, fg=ec); bar.config(bg=ec)
            else:
                outer.config(bg=MUTED); inner.config(bg=self._BG_SEC)
                lbl.config(bg=self._BG_SEC, fg=MUTED); bar.config(bg=ec)
        self._toggle_btn.config(fg=color)
        if engine == "elevenlabs": self._el_frame.pack(fill="x", pady=(4,0))
        else: self._el_frame.pack_forget()
        self._rebuild_voice_list()

    def _rebuild_voice_list(self):
        engine = self._engine.get()
        gf = self._gender_filter.get(); lf = self._lang_filter.get()
        gender_map = {"Todos": None, "♀ Femininas": "F", "♂ Masculinas": "M"}
        target_gender = gender_map.get(gf)
        if engine == "gtts":
            groups = TTS_VOICE_GROUPS_GTTS; all_voices = TTS_VOICES
            lang_opts = ["Todos"] + list(groups.keys())
        elif engine == "edge":
            groups = EDGE_TTS_VOICE_GROUPS; all_voices = EDGE_TTS_VOICES
            lang_opts = ["Todos"] + list(groups.keys())
        else:
            groups = {"Todos": list(ELEVENLABS_VOICES.keys())}; all_voices = ELEVENLABS_VOICES
            lang_opts = ["Todos"]
        self._lang_cb.config(values=lang_opts)
        if lf not in lang_opts: self._lang_filter.set("Todos"); lf = "Todos"
        if lf == "Todos": candidates = list(all_voices.keys())
        else: candidates = groups.get(lf, list(all_voices.keys()))
        if target_gender: candidates = [k for k in candidates if all_voices[k].get("gender") == target_gender]
        if not candidates: candidates = list(all_voices.keys())
        self._voice_cb.config(values=candidates)
        if not candidates: return
        if self._voice_var.get() not in candidates: self._voice_var.set(candidates[0])
        self._on_voice_change()

    def _filter_voices(self, event=None): self._rebuild_voice_list()

    def _on_voice_change(self, event=None):
        engine = self._engine.get(); key = self._voice_var.get()
        if engine == "gtts":
            cfg = TTS_VOICES.get(key, {}); g = "♀" if cfg.get("gender") == "F" else "♂"
            self._voice_badge.config(text=f"  {g}  {cfg.get('lang','?')}-{cfg.get('tld','?')}  ·  pitch×{cfg.get('pitch',1.0):.2f}  ·  rate×{cfg.get('rate',1.0):.2f}  ·  {cfg.get('eq','sem EQ')[:30]}")
        elif engine == "edge":
            cfg = EDGE_TTS_VOICES.get(key, {}); g = "♀" if cfg.get("gender") == "F" else "♂"
            self._voice_badge.config(text=f"  {g}  Neural · {cfg.get('lang','?')}  ·  {cfg.get('desc','')}  ·  voice: {cfg.get('voice_id','?')}")
        else:
            cfg = ELEVENLABS_VOICES.get(key, {}); g = "♀" if cfg.get("gender") == "F" else "♂"
            self._voice_badge.config(text=f"  {g}  ElevenLabs  ·  {cfg.get('desc','')}  ·  id: {cfg.get('voice_id','?')}")

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._body.pack(fill="x", pady=(3,0))
            self._toggle_btn.config(text="🎙  ▼  Gerar voz (TTS) para Copy White", bg=self._BG_HOV)
        else:
            self._body.pack_forget()
            self._toggle_btn.config(text="🎙  ▶  Gerar voz (TTS) para Copy White", bg=self._BG_HDR)

    def _apply_template(self, event=None):
        name = self._tmpl_var.get()
        for tname, ttext in TTS_TEXT_TEMPLATES:
            if tname == name:
                self._txt.delete("1.0","end"); self._txt.insert("1.0", ttext)
                self._update_char_count(); break

    def _update_char_count(self, event=None):
        n = len(self._txt.get("1.0","end").strip())
        self._char_lbl.config(text=f"{n} chars", fg=GREEN if n > 0 else MUTED)

    def _toggle_comp_panel(self):
        if self._comp_var.get(): self._comp_panel.pack(fill="x", pady=(6,0))
        else: self._comp_panel.pack_forget()

    def _update_sw_label(self):
        v = self._sw_var.get()
        if v <= 0.05:   txt, color = "Mono (0.0×)", MUTED
        elif v < 0.95:  txt, color = f"Estreito ({v:.1f}×)", MUTED
        elif v < 1.15:  txt, color = f"Normal ({v:.1f}×)", INDIGO
        elif v < 1.6:   txt, color = f"Wide ({v:.1f}×)", CYAN
        else:           txt, color = f"Ultra Wide ({v:.1f}×)", PURPLE
        self._sw_lbl.config(text=txt, fg=color)

    def _set_volume(self, val):
        self._vol_var.set(val); self._on_vol_slide(val)

    def _on_vol_slide(self, val=None):
        v = self._vol_var.get()
        if v <= -59.9: self._vol_lbl.config(text="  MUDO (−∞)", fg=RED); self._mute_btn.config(bg="#3a0a0a")
        else:
            self._mute_btn.config(bg="#1a0a0a"); sign = "+" if v > 0 else ""
            if v > 20: color = ORANGE
            elif v > 0: color = WARN
            elif v > -20: color = PURPLE
            else: color = RED
            self._vol_lbl.config(text=f"  {sign}{v:.1f} dB", fg=color)

    def _on_pitch_slide(self, val=None):
        v = self._pitch_st_var.get(); sign = "+" if v > 0 else ""
        color = CYAN if v > 0 else (PINK if v < 0 else MUTED)
        self._pitch_st_lbl.config(text=f"  {sign}{v:.1f} st", fg=color)

    def _toggle_key_vis(self):
        current = self._el_key_entry.cget("show")
        self._el_key_entry.config(show="" if current == "•" else "•")

    def _install_edge_tts(self):
        self._install_lbl.config(text="Instalando edge-tts…", fg=WARN)
        def _do():
            ok = _ensure_edge_tts()
            global _EDGE_TTS_OK; _EDGE_TTS_OK = ok
            if ok:
                self.after(0, lambda: self._install_lbl.config(text="✅ edge-tts instalado!", fg=GREEN))
                self.after(0, lambda: self._badge_edge.config(text="Edge ✔", fg=CYAN))
            else:
                self.after(0, lambda: self._install_lbl.config(text="❌ Falhou. Tente: pip install edge-tts", fg=RED))
            self.after(3000, lambda: self._install_lbl.config(text=""))
        threading.Thread(target=_do, daemon=True).start()

    def _install_gtts(self):
        self._install_lbl.config(text="Instalando gTTS…", fg=WARN)
        def _do():
            ok, _ = _pip_install("gtts"); importlib.invalidate_caches()
            global _GTTS_OK; _GTTS_OK = _is_importable("gtts")
            if _GTTS_OK:
                self.after(0, lambda: self._install_lbl.config(text="✅ gTTS instalado!", fg=GREEN))
                self.after(0, lambda: self._badge_gtts.config(text="gTTS ✔", fg=GREEN))
            else:
                self.after(0, lambda: self._install_lbl.config(text="❌ Falhou. Tente: pip install gtts", fg=RED))
            self.after(3000, lambda: self._install_lbl.config(text=""))
        threading.Thread(target=_do, daemon=True).start()

    def _preview_wav(self):
        if not self._last_wav or not os.path.isfile(self._last_wav): return
        self._stop_preview()
        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        try:
            self._preview_proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", self._last_wav],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            self._stop_btn.config(state="normal")
            self._status_lbl.config(text="▶ Reproduzindo…", fg=TEAL)
            def _watch():
                if self._preview_proc: self._preview_proc.wait()
                self.after(0, lambda: self._stop_btn.config(state="disabled"))
                self.after(0, lambda: self._status_lbl.config(text="", fg=MUTED))
            threading.Thread(target=_watch, daemon=True).start()
        except FileNotFoundError:
            messagebox.showwarning("ffplay", "ffplay não encontrado.\nInstale ffmpeg completo para usar o preview.")

    def _stop_preview(self):
        if self._preview_proc:
            try: self._preview_proc.terminate()
            except: pass
            self._preview_proc = None
        self._stop_btn.config(state="disabled"); self._status_lbl.config(text="", fg=MUTED)

    def _save_wav(self):
        if not self._last_wav or not os.path.isfile(self._last_wav): return
        dest = filedialog.asksaveasfilename(title="Salvar WAV gerado", defaultextension=".wav",
                                            filetypes=[("WAV", "*.wav"), ("Todos", "*.*")])
        if not dest: return
        import shutil
        try:
            shutil.copy2(self._last_wav, dest)
            self._status_lbl.config(text=f"✅ Salvo: {os.path.basename(dest)}", fg=GREEN)
            self.after(3000, lambda: self._status_lbl.config(text="", fg=MUTED))
        except Exception as e: messagebox.showerror("Erro ao salvar", str(e))

    def _copy_path(self):
        if self._last_wav:
            self.clipboard_clear(); self.clipboard_append(self._last_wav)
            self._status_lbl.config(text="✅ Path copiado!", fg=GREEN)
            self.after(2000, lambda: self._status_lbl.config(text="", fg=MUTED))

    def _run_tts(self):
        engine = self._engine.get()
        if engine == "gtts" and not _GTTS_OK:
            messagebox.showerror("gTTS não instalado", "Clique em '⬇ Instalar gTTS' ou execute:\n  pip install gtts"); return
        if engine == "edge" and not _EDGE_TTS_OK:
            messagebox.showerror("Edge TTS não instalado", "Clique em '⬇ Instalar Edge TTS' ou execute:\n  pip install edge-tts"); return
        if engine == "elevenlabs" and not _is_importable("requests"):
            messagebox.showerror("requests não instalado", "Execute:\n  pip install requests"); return
        text = self._txt.get("1.0","end").strip()
        if not text: messagebox.showwarning("Texto vazio", "Digite o texto que deseja narrar."); return
        voice = self._voice_var.get(); rate_pre = self._rate_var.get()
        vol_db = self._vol_var.get(); eq_filter = EQ_PRESETS.get(self._eq_var.get(), "")
        reverb_f = REVERB_PRESETS.get(self._reverb_var.get()); normalize = self._norm_var.get()
        compressor = self._comp_var.get(); comp_thr = self._comp_threshold.get()
        comp_ratio = self._comp_ratio.get(); comp_att = self._comp_attack.get()
        comp_rel = self._comp_release.get(); deesser = self._deesser_var.get()
        sw = self._sw_var.get(); pitch_st = self._pitch_st_var.get()
        el_key = self._el_key_var.get(); el_stab = self._el_stability.get()
        el_sim = self._el_similarity.get(); el_style = self._el_style.get()
        self._gen_btn.config(state="disabled", text="⏳  Gerando…", bg=MUTED)
        self._status_lbl.config(text="Processando TTS…", fg=WARN)
        self._wav_info.config(text="")
        self._preview_btn.config(state="disabled"); self._save_btn.config(state="disabled")
        self._copy_btn.config(state="disabled")
        def worker():
            try:
                wav = generate_tts_wav(engine=engine, text=text, voice_key=voice,
                    rate_preset=rate_pre, volume_db=vol_db, eq_filter=eq_filter,
                    reverb_filter=reverb_f, normalize=normalize, compressor=compressor,
                    comp_threshold=comp_thr, comp_ratio=comp_ratio, comp_attack=comp_att,
                    comp_release=comp_rel, deesser=deesser, stereo_width=sw,
                    pitch_semitones=pitch_st, el_api_key=el_key, el_stability=el_stab,
                    el_similarity=el_sim, el_style=el_style)
                self._last_wav = wav
                dur_str = ""
                try: info = get_video_info(wav); dur_str = f"  ·  {info.get('duration', 0):.1f}s"
                except: pass
                engine_lbl = self.ENGINE_LABELS.get(engine, engine)
                vol_info = "MUDO" if vol_db <= -59.9 else f"{'+' if vol_db>0 else ''}{vol_db:.1f} dB"
                self.after(0, lambda: self._wav_info.config(
                    text=(f"[{engine_lbl}]  {os.path.basename(wav)}{dur_str}  ·  vol: {vol_info}"
                          f"  ·  EQ: {self._eq_var.get()}  ·  Reverb: {self._reverb_var.get()}\n"
                          f"  🗂  {wav}"), fg=TEAL))
                self.after(0, lambda: self._status_lbl.config(text="✅ WAV pronto!", fg=GREEN))
                self.after(0, lambda: self._preview_btn.config(state="normal"))
                self.after(0, lambda: self._save_btn.config(state="normal"))
                self.after(0, lambda: self._copy_btn.config(state="normal"))
                if self.on_wav_ready: self.after(0, lambda: self.on_wav_ready(wav))
            except Exception as e:
                self.after(0, lambda: self._status_lbl.config(text=f"❌ {e}", fg=RED))
                self.after(0, lambda: messagebox.showerror("Erro no TTS", str(e)))
            finally:
                engine_color = self.ENGINE_COLORS.get(engine, PURPLE)
                self.after(0, lambda: self._gen_btn.config(state="normal", text="✨  Gerar WAV", bg=engine_color))
        threading.Thread(target=worker, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#   ABA TRANSCRIÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

class TranscribeTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._segments = []; self._video_path = tk.StringVar()
        self._model_var = tk.StringVar(value="base"); self._lang_var = tk.StringVar(value="Auto-detectar")
        self._running = False; self._build()

    def _build(self):
        body = tk.Frame(self, bg=DARK, padx=20, pady=16); body.pack(fill="both", expand=True)
        top_card = tk.Frame(body, bg=CARD, padx=14, pady=12); top_card.pack(fill="x", pady=(0,10))
        tk.Label(top_card, text="🎬  Vídeo para transcrever", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,5))
        vid_row = tk.Frame(top_card, bg=CARD); vid_row.pack(fill="x")
        self._vid_entry = tk.Entry(vid_row, textvariable=self._video_path, font=FONT_MONO,
                                   bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1)
        self._vid_entry.pack(side="left", fill="x", expand=True)
        tk.Button(vid_row, text="Escolher vídeo", font=FONT_LABEL, bg=ACCENT, fg="white",
                  relief="flat", padx=10, pady=2, cursor="hand2", command=self._browse_video).pack(side="right", padx=(8,0))
        opts_card = tk.Frame(body, bg=CARD, padx=14, pady=12); opts_card.pack(fill="x", pady=(0,10))
        opts_card.columnconfigure(0, weight=1); opts_card.columnconfigure(1, weight=1); opts_card.columnconfigure(2, weight=1)
        mod_frame = tk.Frame(opts_card, bg=CARD); mod_frame.grid(row=0, column=0, sticky="ew", padx=(0,12))
        tk.Label(mod_frame, text="🧠  Modelo Whisper", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,3))
        model_cb = ttk.Combobox(mod_frame, textvariable=self._model_var,
                                values=WHISPER_MODELS, state="readonly", width=12, font=FONT_LABEL)
        model_cb.pack(anchor="w")
        hints = {"tiny":"~40MB · rápido","base":"~150MB · bom","small":"~500MB","medium":"~1.5GB · ótimo","large":"~3GB · máximo"}
        self._model_hint = tk.Label(mod_frame, text=hints["base"], font=FONT_SMALL, bg=CARD, fg=MUTED); self._model_hint.pack(anchor="w", pady=(2,0))
        model_cb.bind("<<ComboboxSelected>>", lambda e: self._model_hint.config(text=hints.get(self._model_var.get(),"")))
        lang_frame = tk.Frame(opts_card, bg=CARD); lang_frame.grid(row=0, column=1, sticky="ew", padx=(0,12))
        tk.Label(lang_frame, text="🌐  Idioma", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,3))
        lang_cb = ttk.Combobox(lang_frame, textvariable=self._lang_var,
                               values=list(WHISPER_LANGS.keys()), state="readonly", width=16, font=FONT_LABEL)
        lang_cb.pack(anchor="w")
        tk.Label(lang_frame, text="Auto-detectar é recomendado", font=FONT_SMALL, bg=CARD, fg=MUTED).pack(anchor="w", pady=(2,0))
        stat_frame = tk.Frame(opts_card, bg=CARD); stat_frame.grid(row=0, column=2, sticky="ew")
        tk.Label(stat_frame, text="📦  Status", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,3))
        wok = _WHISPER_OK
        tk.Label(stat_frame, text="faster-whisper ✔" if wok else "⚠ pip install faster-whisper",
                 font=FONT_SMALL, bg=CARD, fg=GREEN if wok else RED).pack(anchor="w")
        prog_card = tk.Frame(body, bg=CARD, padx=14, pady=8); prog_card.pack(fill="x", pady=(0,10))
        prog_row = tk.Frame(prog_card, bg=CARD); prog_row.pack(fill="x")
        self._trans_btn = tk.Button(prog_row, text="▶  Transcrever",
                                    font=("Segoe UI", 9, "bold"), bg=ACCENT, fg="white",
                                    relief="flat", padx=16, pady=6, cursor="hand2",
                                    command=self._start_transcription)
        self._trans_btn.pack(side="left")
        self._exp_txt_btn = tk.Button(prog_row, text="📄  Exportar .TXT", font=FONT_LABEL, bg=CARD2, fg=CYAN,
                                      relief="flat", padx=10, pady=6, cursor="hand2",
                                      command=lambda: self._export("txt"), state="disabled")
        self._exp_txt_btn.pack(side="left", padx=(6,0))
        self._exp_srt_btn = tk.Button(prog_row, text="🎞  Exportar .SRT", font=FONT_LABEL, bg=CARD2, fg=TEAL,
                                      relief="flat", padx=10, pady=6, cursor="hand2",
                                      command=lambda: self._export("srt"), state="disabled")
        self._exp_srt_btn.pack(side="left", padx=(6,0))
        self._prog_bar = ttk.Progressbar(prog_card, mode="determinate", maximum=100)
        self._prog_bar.pack(fill="x", pady=(6,0))
        self._prog_lbl = tk.Label(prog_card, text="Aguardando…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self._prog_lbl.pack(anchor="w", pady=(3,0))
        result_outer = tk.Frame(body, bg=DARK); result_outer.pack(fill="both", expand=True)
        self._res_canvas = tk.Canvas(result_outer, bg=DARK, highlightthickness=0)
        res_sb = ttk.Scrollbar(result_outer, orient="vertical", command=self._res_canvas.yview)
        self._res_canvas.configure(yscrollcommand=res_sb.set)
        res_sb.pack(side="right", fill="y"); self._res_canvas.pack(side="left", fill="both", expand=True)
        self._res_frame = tk.Frame(self._res_canvas, bg=DARK)
        self._res_win = self._res_canvas.create_window((0,0), window=self._res_frame, anchor="nw")
        self._res_frame.bind("<Configure>", lambda e: self._res_canvas.configure(scrollregion=self._res_canvas.bbox("all")))
        self._res_canvas.bind("<Configure>", lambda e: self._res_canvas.itemconfig(self._res_win, width=e.width))
        tk.Label(self._res_frame, text="A transcrição aparecerá aqui…",
                 font=("Segoe UI",10), bg=DARK, fg=MUTED, pady=30).pack()

    def _browse_video(self):
        path = filedialog.askopenfilename(title="Selecionar vídeo",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("Todos","*.*")])
        if path: self._video_path.set(path)

    def set_video(self, path): self._video_path.set(path)

    def _start_transcription(self):
        if self._running: return
        path = self._video_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Erro", "Selecione um vídeo válido."); return
        if not _WHISPER_OK:
            messagebox.showerror("Whisper não instalado", "Execute:\n  pip install faster-whisper"); return
        model = self._model_var.get(); lang = WHISPER_LANGS.get(self._lang_var.get())
        self._running = True
        self._trans_btn.config(state="disabled", text="⏳  Transcrevendo…", bg=MUTED)
        self._prog_bar.config(value=0)
        def prog_cb(pct): self.after(0, lambda: self._prog_bar.config(value=pct))
        def log_cb(msg):  self.after(0, lambda: self._prog_lbl.config(text=msg, fg=TEXT))
        def worker():
            try:
                segs = transcribe_video(path, model_name=model, language=lang,
                                        progress_cb=prog_cb, log_cb=log_cb)
                self._segments = segs
                self.after(0, lambda: self._render_result(segs))
            except Exception as e:
                self.after(0, lambda: self._prog_lbl.config(text=f"❌ {e}", fg=RED))
                self.after(0, lambda: messagebox.showerror("Erro na transcrição", str(e)))
            finally:
                self._running = False
                self.after(0, lambda: self._trans_btn.config(state="normal", text="▶  Transcrever", bg=ACCENT))
        threading.Thread(target=worker, daemon=True).start()

    def _render_result(self, segments):
        for w in self._res_frame.winfo_children(): w.destroy()
        if not segments:
            tk.Label(self._res_frame, text="Nenhum segmento encontrado.",
                     font=FONT_STATUS, bg=DARK, fg=MUTED, pady=20).pack(); return
        self._prog_lbl.config(text=f"✅ {len(segments)} segmentos transcritos.", fg=GREEN)
        self._exp_txt_btn.config(state="normal"); self._exp_srt_btn.config(state="normal")
        for i, seg in enumerate(segments):
            row_bg = CARD if i % 2 == 0 else "#1a1a22"
            row = tk.Frame(self._res_frame, bg=row_bg, padx=12, pady=5); row.pack(fill="x", pady=(0,1))
            tk.Label(row, text=_format_timestamp(seg["start"]),
                     font=("Consolas",8,"bold"), bg=row_bg, fg=CYAN, width=10, anchor="w").pack(side="left")
            tk.Label(row, text=_format_timestamp(seg["end"]),
                     font=("Consolas",8), bg=row_bg, fg=MUTED, width=10, anchor="w").pack(side="left")
            tk.Label(row, text=seg["text"], font=("Segoe UI",9), bg=row_bg, fg=TEXT,
                     anchor="w", wraplength=600, justify="left").pack(side="left", fill="x", expand=True)

    def _export(self, fmt):
        if not self._segments:
            messagebox.showwarning("Sem transcrição", "Faça a transcrição primeiro."); return
        ext = f".{fmt}"
        path = filedialog.asksaveasfilename(title=f"Exportar {fmt.upper()}",
            defaultextension=ext, filetypes=[(fmt.upper(), f"*{ext}"),("Todos","*.*")])
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                if fmt == "txt":
                    for seg in self._segments:
                        f.write(f"[{_format_timestamp(seg['start'])}]  {seg['text']}\n")
                elif fmt == "srt":
                    for i, seg in enumerate(self._segments, 1):
                        f.write(f"{i}\n{_format_timestamp_srt(seg['start'])} --> {_format_timestamp_srt(seg['end'])}\n{seg['text']}\n\n")
            messagebox.showinfo("Exportado!", f"Salvo em:\n{path}")
        except Exception as e: messagebox.showerror("Erro ao exportar", str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#   ABA PREVIEW
# ═══════════════════════════════════════════════════════════════════════════════

class PreviewTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DARK, **kwargs)
        self._orig_path = tk.StringVar(); self._proc_path = tk.StringVar()
        self._orig_proc = [None, None]; self._build()

    def _build(self):
        body = tk.Frame(self, bg=DARK, padx=20, pady=16); body.pack(fill="both", expand=True)
        tk.Label(body, text="🎬  Preview — Original vs Processado",
                 font=("Segoe UI",12,"bold"), bg=DARK, fg=TEXT).pack(anchor="w", pady=(0,12))
        sel_frame = tk.Frame(body, bg=CARD, padx=14, pady=12); sel_frame.pack(fill="x", pady=(0,12))
        sel_frame.columnconfigure(0, weight=1); sel_frame.columnconfigure(1, weight=1)
        orig_f = tk.Frame(sel_frame, bg=CARD); orig_f.grid(row=0, column=0, sticky="ew", padx=(0,8))
        tk.Label(orig_f, text="📼  Vídeo Original", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,3))
        orig_row = tk.Frame(orig_f, bg=CARD); orig_row.pack(fill="x")
        tk.Entry(orig_row, textvariable=self._orig_path, font=FONT_MONO,
                 bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True)
        tk.Button(orig_row, text="Escolher", font=FONT_LABEL, bg="#2a2a35", fg=ACC2,
                  relief="flat", padx=6, pady=2, cursor="hand2",
                  command=lambda: self._browse("orig")).pack(side="right", padx=(4,0))
        proc_f = tk.Frame(sel_frame, bg=CARD); proc_f.grid(row=0, column=1, sticky="ew", padx=(8,0))
        tk.Label(proc_f, text="✨  Vídeo Processado", font=FONT_BOLD, bg=CARD, fg=MUTED).pack(anchor="w", pady=(0,3))
        proc_row = tk.Frame(proc_f, bg=CARD); proc_row.pack(fill="x")
        tk.Entry(proc_row, textvariable=self._proc_path, font=FONT_MONO,
                 bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True)
        tk.Button(proc_row, text="Escolher", font=FONT_LABEL, bg="#2a2a35", fg=TEAL,
                  relief="flat", padx=6, pady=2, cursor="hand2",
                  command=lambda: self._browse("proc")).pack(side="right", padx=(4,0))
        ctrl = tk.Frame(body, bg=CARD, padx=14, pady=10); ctrl.pack(fill="x")
        tk.Button(ctrl, text="▶  Reproduzir Original", font=FONT_BOLD, bg=ACCENT, fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=lambda: self._play("orig")).pack(side="left", padx=(0,6))
        tk.Button(ctrl, text="▶  Reproduzir Processado", font=FONT_BOLD, bg=TEAL, fg=DARK,
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=lambda: self._play("proc")).pack(side="left", padx=(0,6))
        tk.Button(ctrl, text="▶▶  Reproduzir Ambos", font=FONT_BOLD, bg=PURPLE, fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._play_both).pack(side="left")

    def _browse(self, key):
        path = filedialog.askopenfilename(title="Selecionar vídeo",
            filetypes=[("Vídeos","*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts *.m4v"),("Todos","*.*")])
        if not path: return
        if key == "orig": self._orig_path.set(path)
        else:             self._proc_path.set(path)

    def set_paths(self, orig=None, proc=None):
        if orig and os.path.isfile(orig): self._orig_path.set(orig)
        if proc and os.path.isfile(proc): self._proc_path.set(proc)

    def _play(self, key):
        path = (self._orig_path if key == "orig" else self._proc_path).get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Não encontrado", "Selecione o vídeo primeiro."); return
        open_video_player(path)

    def _play_both(self):
        orig = self._orig_path.get().strip(); proc = self._proc_path.get().strip()
        if not orig or not os.path.isfile(orig):
            messagebox.showwarning("Original não encontrado", "Selecione o vídeo original."); return
        if not proc or not os.path.isfile(proc):
            messagebox.showwarning("Processado não encontrado", "Selecione o vídeo processado."); return
        open_video_player(orig); self.after(500, lambda: open_video_player(proc))

    def _stop_all(self):
        for p in self._orig_proc:
            if p:
                try: p.terminate()
                except: pass
        self._orig_proc = [None, None]


# ═══════════════════════════════════════════════════════════════════════════════
#   APP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class AudioFixApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"AudioFix Pro — v{VERSAO_ATUAL}")
        self.geometry("960x1020"); self.minsize(820, 820)
        self.configure(bg=DARK); self.resizable(True, True)
        self.running = False; self._batch_cancel = False
        self._noise_controls: dict = {}; self._dcb_widgets = []; self._audio_mode_widgets = []
        self.output_dir    = tk.StringVar(); self.n_variants    = tk.IntVar(value=0)
        self.cw_path       = tk.StringVar(); self.cw_enabled    = tk.BooleanVar(value=False)
        self.cw_gain       = tk.DoubleVar(value=0.40); self.dcb_enabled   = tk.BooleanVar(value=False)
        self.dcb_threshold = tk.DoubleVar(value=0.50); self.dcb_ratio     = tk.DoubleVar(value=4.0)
        self.dcb_makeup    = tk.DoubleVar(value=1.80); self._mode         = tk.StringVar(value="audio")
        self._build_ui()
        if not _FFMPEG_OK:
            self.after(600, lambda: messagebox.showwarning("ffmpeg não encontrado", _ffmpeg_install_hint()))
        # ── Verifica atualização 3 segundos após abrir (silencioso se atualizado) ──
        self.after(3000, lambda: verificar_atualizacao(self, silencioso=True))

    def _build_ui(self):
        hdr = tk.Frame(self, bg=PANEL, pady=10); hdr.pack(fill="x")
        title_row = tk.Frame(hdr, bg=PANEL); title_row.pack()
        tk.Label(title_row, text="AudioFix Pro", font=FONT_TITLE, bg=PANEL, fg=TEXT).pack(side="left")
        tk.Label(title_row, text=f"  v{VERSAO_ATUAL}", font=("Segoe UI",9), bg=PANEL, fg=ACCENT).pack(side="left", pady=(6,0))

        # ── Botão de verificar atualização manual ──────────────────────────
        tk.Button(title_row, text="🔄  Verificar atualização",
                  font=FONT_SMALL, bg="#1a1a2e", fg=ACC2,
                  relief="flat", padx=8, pady=3, cursor="hand2",
                  command=lambda: verificar_atualizacao(self, silencioso=False)
                  ).pack(side="left", padx=(16, 0), pady=(6, 0))

        tk.Label(hdr, text="Processamento em lote · Inversão de fase · Ruídos · Copy White · TTS Neural · Transcrição · Preview",
                 font=FONT_STATUS, bg=PANEL, fg=MUTED).pack(pady=(1,0))
        dep_frame = tk.Frame(hdr, bg=PANEL); dep_frame.pack(pady=(4,0))
        for text, color in [
            ("ffmpeg ✔" if _FFMPEG_OK else "ffmpeg ✖",    GREEN if _FFMPEG_OK else RED),
            ("  |  ", MUTED),
            ("Edge TTS ✔" if _EDGE_TTS_OK else "Edge TTS —", CYAN if _EDGE_TTS_OK else MUTED),
            ("  |  ", MUTED),
            ("gTTS ✔" if _GTTS_OK else "gTTS —",           GREEN if _GTTS_OK else MUTED),
            ("  |  ", MUTED),
            ("whisper ✔" if _WHISPER_OK else "whisper —",   GREEN if _WHISPER_OK else MUTED),
            ("  |  ", MUTED),
            (f"v{VERSAO_ATUAL}", MUTED),
        ]:
            tk.Label(dep_frame, text=text, font=FONT_SMALL, bg=PANEL, fg=color).pack(side="left")
        self._build_notebook()

    def _build_notebook(self):
        nb_outer = tk.Frame(self, bg=DARK); nb_outer.pack(fill="both", expand=True)
        tab_bar = tk.Frame(nb_outer, bg="#111116", pady=0); tab_bar.pack(fill="x")
        page_container = tk.Frame(nb_outer, bg=DARK); page_container.pack(fill="both", expand=True)
        pages = {}; tab_btns = {}

        def switch_tab(name):
            for n, p in pages.items(): p.pack_forget()
            pages[name].pack(fill="both", expand=True)
            for n, b in tab_btns.items():
                b.config(bg=ACCENT if n == name else "#111116",
                         fg="white" if n == name else MUTED)

        def make_tab(name, label, icon):
            btn = tk.Button(tab_bar, text=f"{icon}  {label}", font=FONT_TAB,
                            bg="#111116", fg=MUTED, relief="flat",
                            padx=14, pady=8, cursor="hand2",
                            command=lambda n=name: switch_tab(n))
            btn.pack(side="left"); tab_btns[name] = btn
            frame = tk.Frame(page_container, bg=DARK); pages[name] = frame; return frame

        proc_page    = make_tab("processar",   "Processar",   "⚙️")
        trans_page   = make_tab("transcrever", "Transcrever", "📝")
        preview_page = make_tab("preview",     "Preview",     "🎬")

        self._build_process_page(proc_page)
        self.transcribe_tab = TranscribeTab(trans_page); self.transcribe_tab.pack(fill="both", expand=True)
        self.preview_tab    = PreviewTab(preview_page);  self.preview_tab.pack(fill="both", expand=True)
        switch_tab("processar"); self._switch_tab = switch_tab

    def _build_process_page(self, parent):
        outer = tk.Frame(parent, bg=DARK); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=DARK, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        body_frame = tk.Frame(canvas, bg=DARK)
        body_win = canvas.create_window((0,0), window=body_frame, anchor="nw")
        body_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        body = tk.Frame(body_frame, bg=DARK, padx=20, pady=14); body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1); row_idx = 0

        mode_outer = tk.Frame(body, bg=DARK, pady=3)
        mode_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,4)); row_idx += 1
        tk.Label(mode_outer, text="⚙️  Modo de entrada", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        mc = tk.Frame(mode_outer, bg=DARK); mc.pack(fill="x")
        mc.columnconfigure(0, weight=1); mc.columnconfigure(1, weight=1)
        self._btn_single_outer = tk.Frame(mc, bg=ACCENT, padx=2, pady=2)
        self._btn_single_outer.grid(row=0, column=0, sticky="nsew", padx=(0,4))
        self._btn_single_inner = tk.Frame(self._btn_single_outer, bg="#1a1830", padx=12, pady=10, cursor="hand2")
        self._btn_single_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_single_inner, text="🎬  Um vídeo", font=("Segoe UI",10,"bold"), bg="#1a1830", fg=ACC2).pack(anchor="w")
        tk.Label(self._btn_single_inner, text="Selecione um arquivo\ne defina a saída manualmente",
                 font=FONT_SMALL, bg="#1a1830", fg=MUTED, justify="left").pack(anchor="w", pady=(3,0))
        self._btn_batch_outer = tk.Frame(mc, bg=MUTED, padx=2, pady=2)
        self._btn_batch_outer.grid(row=0, column=1, sticky="nsew", padx=(4,0))
        self._btn_batch_inner = tk.Frame(self._btn_batch_outer, bg=CARD, padx=12, pady=10, cursor="hand2")
        self._btn_batch_inner.pack(fill="both", expand=True)
        tk.Label(self._btn_batch_inner, text="📦  Vários vídeos (lote)", font=("Segoe UI",10,"bold"), bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self._btn_batch_inner, text="Adicione múltiplos arquivos\ne processe todos em sequência",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, justify="left").pack(anchor="w", pady=(3,0))
        for w in [self._btn_single_outer, self._btn_single_inner] + list(self._btn_single_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_input_mode("single"))
        for w in [self._btn_batch_outer, self._btn_batch_inner] + list(self._btn_batch_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_input_mode("batch"))

        self._single_outer = tk.Frame(body, bg=DARK, pady=3)
        self._single_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        self._single_video  = tk.StringVar(); self._single_output = tk.StringVar()
        self._file_row_widget(self._single_outer, 0, "🎬  Vídeo de entrada", self._single_video, self._browse_single_input, "")
        self._file_row_widget(self._single_outer, 1, "💾  Arquivo de saída", self._single_output, self._browse_single_output, "")
        self._single_outer.columnconfigure(0, weight=1)

        self._tts_single_outer = tk.Frame(body, bg=DARK, pady=1)
        self._tts_single_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        self._tts_single = TTSPanel(self._tts_single_outer, on_wav_ready=self._on_tts_wav_ready, bg=DARK)
        self._tts_single.pack(fill="x")

        self._batch_outer = tk.Frame(body, bg=DARK, pady=3)
        self._batch_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        self.batch_queue = BatchQueuePanel(self._batch_outer); self.batch_queue.pack(fill="both", expand=True)
        out_dir_card = tk.Frame(self._batch_outer, bg=CARD, padx=12, pady=8); out_dir_card.pack(fill="x", pady=(6,0))
        out_dir_row = tk.Frame(out_dir_card, bg=CARD); out_dir_row.pack(fill="x")
        tk.Label(out_dir_row, text="📁  Pasta de saída (lote):", font=FONT_BOLD, bg=CARD, fg=MUTED, width=22, anchor="w").pack(side="left")
        tk.Entry(out_dir_row, textvariable=self.output_dir, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG,
                 insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(out_dir_row, text="Escolher pasta", font=FONT_LABEL, bg=ACCENT, fg="white",
                  relief="flat", padx=8, pady=2, cursor="hand2",
                  command=self._browse_output_dir).pack(side="right")

        self._tts_batch_outer = tk.Frame(body, bg=DARK, pady=1)
        self._tts_batch_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        self._tts_batch = TTSPanel(self._tts_batch_outer, on_wav_ready=self._on_tts_wav_ready, bg=DARK)
        self._tts_batch.pack(fill="x")

        proc_outer = tk.Frame(body, bg=DARK, pady=3)
        proc_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        tk.Label(proc_outer, text="⚙️  Modo de processamento", font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,4))
        pc = tk.Frame(proc_outer, bg=DARK); pc.pack(fill="x")
        pc.columnconfigure(0, weight=1); pc.columnconfigure(1, weight=1)
        self._proc_audio_outer = tk.Frame(pc, bg=ACCENT, padx=2, pady=2)
        self._proc_audio_outer.grid(row=0, column=0, sticky="nsew", padx=(0,4))
        self._proc_audio_inner = tk.Frame(self._proc_audio_outer, bg="#1a1830", padx=12, pady=10, cursor="hand2")
        self._proc_audio_inner.pack(fill="both", expand=True)
        tk.Label(self._proc_audio_inner, text="🎛️  Manipular Áudio", font=("Segoe UI",10,"bold"), bg="#1a1830", fg=ACC2).pack(anchor="w")
        tk.Label(self._proc_audio_inner, text="Inversão de fase · Ruídos · Copy White · DCB",
                 font=FONT_SMALL, bg="#1a1830", fg=MUTED).pack(anchor="w", pady=(3,0))
        self._proc_orig_outer = tk.Frame(pc, bg=MUTED, padx=2, pady=2)
        self._proc_orig_outer.grid(row=0, column=1, sticky="nsew", padx=(4,0))
        self._proc_orig_inner = tk.Frame(self._proc_orig_outer, bg=CARD, padx=12, pady=10, cursor="hand2")
        self._proc_orig_inner.pack(fill="both", expand=True)
        tk.Label(self._proc_orig_inner, text="🎬  Áudio Original", font=("Segoe UI",10,"bold"), bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self._proc_orig_inner, text="Sem processamento · só variações de metadados",
                 font=FONT_SMALL, bg=CARD, fg=MUTED).pack(anchor="w", pady=(3,0))
        for w in [self._proc_audio_outer, self._proc_audio_inner] + list(self._proc_audio_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_proc_mode("audio"))
        for w in [self._proc_orig_outer, self._proc_orig_inner] + list(self._proc_orig_inner.winfo_children()):
            w.bind("<Button-1>", lambda e: self._set_proc_mode("original"))

        noise_section = CollapsibleSection(body, title="Mistura de ruídos coloridos", icon="🎨",
                                           color=PINK, default_open=True)
        noise_section.grid(row=row_idx, column=0, sticky="ew", pady=(0,1)); row_idx += 1
        noise_grid = tk.Frame(noise_section.content, bg=DARK); noise_grid.pack(fill="x")
        noise_grid.columnconfigure(0, weight=1); noise_grid.columnconfigure(1, weight=1)
        defaults = {"Rosa":0.003,"Branco":0.0,"Marrom":0.0,"Azul":0.0,"Violeta":0.0,"Cinza":0.0}
        for idx2, name in enumerate(NOISE_GENERATORS.keys()):
            ctrl = NoiseControl(noise_grid, name=name, color=NOISE_COLORS[name], default_amp=defaults.get(name,0.0))
            ctrl.grid(row=idx2//2, column=idx2%2, sticky="ew", padx=(0,4) if idx2%2==0 else (4,0), pady=1)
            self._noise_controls[name] = ctrl
        self._audio_mode_widgets.append(noise_section)

        cw_section = CollapsibleSection(body, title="Copy White — sobreposição de áudio externo", icon="📻",
                                        color=CYAN, default_open=True)
        cw_section.grid(row=row_idx, column=0, sticky="ew", pady=(0,1)); row_idx += 1
        cw_inner = tk.Frame(cw_section.content, bg=DARK, pady=3); cw_inner.pack(fill="x")
        cw_hdr = tk.Frame(cw_inner, bg=DARK); cw_hdr.pack(fill="x", pady=(0,3))
        tk.Checkbutton(cw_hdr, variable=self.cw_enabled, bg=DARK, activebackground=DARK, fg=CYAN,
                       selectcolor="#111116", relief="flat", bd=0, cursor="hand2",
                       command=self._toggle_cw).pack(side="left")
        tk.Label(cw_hdr, text="Ativar Copy White", font=FONT_BOLD, bg=DARK, fg=CYAN).pack(side="left")
        self.cw_card = tk.Frame(cw_inner, bg=CARD, padx=12, pady=10); self.cw_card.pack(fill="x")
        file_row_cw = tk.Frame(self.cw_card, bg=CARD); file_row_cw.pack(fill="x", pady=(0,6))
        tk.Label(file_row_cw, text="Áudio WAV:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_entry = tk.Entry(file_row_cw, textvariable=self.cw_path, font=FONT_MONO,
                                 bg=INPUT_BG, fg=INPUT_FG, insertbackground="black", relief="flat", bd=1)
        self.cw_entry.pack(side="left", fill="x", expand=True, padx=(0,6))
        tk.Button(file_row_cw, text="Escolher WAV", font=FONT_LABEL, bg=CYAN, fg=DARK,
                  relief="flat", padx=8, pady=2, cursor="hand2", command=self._browse_cw).pack(side="right")
        gain_row = tk.Frame(self.cw_card, bg=CARD); gain_row.pack(fill="x")
        tk.Label(gain_row, text="Ganho mix:", font=FONT_BOLD, bg=CARD, fg=MUTED, width=12, anchor="w").pack(side="left")
        self.cw_gain_lbl = tk.Label(gain_row, text=f"{self.cw_gain.get():.2f}", font=FONT_BOLD, bg=CARD, fg=CYAN, width=5)
        self.cw_gain_lbl.pack(side="right")
        self.cw_slider = ttk.Scale(gain_row, from_=0.05, to=1.0, variable=self.cw_gain, orient="horizontal",
                                   command=lambda v: self.cw_gain_lbl.config(text=f"{float(v):.2f}"))
        self.cw_slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._toggle_cw()
        self._audio_mode_widgets.append(cw_section)

        dcb_section = CollapsibleSection(body, title="DCB — Dynamic Compression Boost", icon="🎚",
                                         color=GOLD, default_open=False)
        dcb_section.grid(row=row_idx, column=0, sticky="ew", pady=(0,1)); row_idx += 1
        dcb_inner = tk.Frame(dcb_section.content, bg=DARK, pady=3); dcb_inner.pack(fill="x")
        dcb_hdr = tk.Frame(dcb_inner, bg=DARK); dcb_hdr.pack(fill="x", pady=(0,3))
        tk.Checkbutton(dcb_hdr, variable=self.dcb_enabled, bg=DARK, activebackground=DARK, fg=GOLD,
                       selectcolor="#111116", relief="flat", bd=0, cursor="hand2",
                       command=self._toggle_dcb).pack(side="left")
        tk.Label(dcb_hdr, text="Ativar DCB", font=FONT_BOLD, bg=DARK, fg=GOLD).pack(side="left")
        self.dcb_card = tk.Frame(dcb_inner, bg=CARD, padx=12, pady=10); self.dcb_card.pack(fill="x")
        dcb_ctrl = tk.Frame(self.dcb_card, bg=CARD); dcb_ctrl.pack(fill="x")
        self._dcb_slider_row(dcb_ctrl, "Threshold",   self.dcb_threshold, 0.10, 0.90, "{:.2f}",   GOLD)
        self._dcb_slider_row(dcb_ctrl, "Ratio",       self.dcb_ratio,     1.0,  10.0, "{:.1f}:1", GOLD)
        self._dcb_slider_row(dcb_ctrl, "Makeup Gain", self.dcb_makeup,    0.5,  3.0,  "{:.2f}×",  WARN)
        self._toggle_dcb()
        self._audio_mode_widgets.append(dcb_section)

        var_section = CollapsibleSection(body, title="Variações de metadados", icon="🎲",
                                         color=WARN, default_open=False)
        var_section.grid(row=row_idx, column=0, sticky="ew", pady=(0,1)); row_idx += 1
        var_inner = tk.Frame(var_section.content, bg=DARK, pady=3); var_inner.pack(fill="x")
        var_card = tk.Frame(var_inner, bg=CARD, padx=12, pady=10); var_card.pack(fill="x")
        spin_frame = tk.Frame(var_card, bg=CARD); spin_frame.pack(fill="x")
        self.var_minus_btn = tk.Button(spin_frame, text="  −  ", font=("Segoe UI",11,"bold"),
                                       bg="#2a1a1a", fg=RED, relief="flat", cursor="hand2",
                                       padx=5, pady=3, command=self._decrement_variants)
        self.var_minus_btn.pack(side="left")
        self.var_display = tk.Label(spin_frame, text="0", font=("Segoe UI",12,"bold"),
                                    bg=CARD, fg=TEXT, width=4, anchor="center")
        self.var_display.pack(side="left", padx=4)
        self.var_plus_btn = tk.Button(spin_frame, text="  +  ", font=("Segoe UI",11,"bold"),
                                      bg="#1a2a1a", fg=GREEN, relief="flat", cursor="hand2",
                                      padx=5, pady=3, command=self._increment_variants)
        self.var_plus_btn.pack(side="left")
        self.var_hint = tk.Label(spin_frame, text="sem variações", font=FONT_SMALL, bg=CARD, fg=MUTED)
        self.var_hint.pack(side="left", padx=(8,0))
        self.n_variants.trace_add("write", lambda *_: self._sync_var_display())
        tk.Frame(var_card, bg=MUTED, height=1).pack(fill="x", pady=(8,6))
        self.variation_level_selector = VariationLevelSelector(var_card)
        self.variation_level_selector.pack(fill="x")

        prog_outer = tk.Frame(body, bg=DARK, pady=3)
        prog_outer.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        prog_card = tk.Frame(prog_outer, bg=CARD, padx=12, pady=8); prog_card.pack(fill="x")
        self.global_progress = ttk.Progressbar(prog_card, mode="determinate", maximum=100, length=400)
        self.global_progress.pack(fill="x")
        self.global_status = tk.Label(prog_card, text="Aguardando…", font=FONT_STATUS, bg=CARD, fg=MUTED)
        self.global_status.pack(anchor="w", pady=(3,0))

        log_section = CollapsibleSection(body, title="Log de processamento", icon="📋",
                                         color=INDIGO, default_open=False)
        log_section.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        log_inner = tk.Frame(log_section.content, bg=DARK, pady=3); log_inner.pack(fill="x")
        log_card = tk.Frame(log_inner, bg=CARD, padx=12, pady=8); log_card.pack(fill="both", expand=True)
        log_grid = tk.Frame(log_card, bg=CARD); log_grid.pack(fill="both", expand=True)
        log_grid.rowconfigure(0, weight=1); log_grid.columnconfigure(0, weight=1)
        self.log_box = tk.Text(log_grid, height=7, font=FONT_MONO, bg="#111116", fg="#a0a0b8",
                               insertbackground=TEXT, relief="flat", state="disabled", wrap="word")
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(log_grid, command=self.log_box.yview); sb2.grid(row=0, column=1, sticky="ns")
        self.log_box.config(yscrollcommand=sb2.set)
        self._log_section = log_section

        btn_frame = tk.Frame(body, bg=DARK, pady=10)
        btn_frame.grid(row=row_idx, column=0, sticky="ew", pady=(0,3)); row_idx += 1
        self.run_btn = tk.Button(btn_frame, text="▶  PROCESSAR", font=("Segoe UI",10,"bold"),
                                 bg=ACCENT, fg="white", activebackground=ACC2,
                                 relief="flat", padx=24, pady=8, cursor="hand2",
                                 command=self._start_processing)
        self.run_btn.pack(side="right")
        self.cancel_btn = tk.Button(btn_frame, text="⏹  Cancelar lote", font=("Segoe UI",10,"bold"),
                                    bg="#2a1a1a", fg=RED, relief="flat", padx=16, pady=8,
                                    cursor="hand2", state="disabled", command=self._cancel_batch)
        self.cancel_btn.pack(side="right", padx=(0,6))
        tk.Button(btn_frame, text="🗑  Limpar log", font=FONT_LABEL, bg=CARD, fg=MUTED,
                  relief="flat", padx=12, pady=8, cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=(0,6))

        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT,
                        thickness=8, bordercolor=DARK, lightcolor=ACCENT)
        style.configure("Vertical.TScrollbar", troughcolor="#111116", background=MUTED,
                        arrowcolor=MUTED, bordercolor=DARK)
        style.configure("TScale", background=CARD, troughcolor=PANEL, sliderthickness=14)
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=INPUT_BG,
                        foreground=INPUT_FG, selectbackground=ACCENT)
        self._input_mode = "single"; self._proc_mode = "audio"
        self._set_input_mode("single"); self._set_proc_mode("audio")

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_tts_wav_ready(self, wav_path):
        self.cw_path.set(wav_path); self.cw_enabled.set(True)
        self._toggle_cw(); self._log(f"🎙 TTS → Copy White: {wav_path}")

    def _file_row_widget(self, parent, grid_row, label, var, cmd, placeholder):
        outer = tk.Frame(parent, bg=DARK, pady=2); outer.grid(row=grid_row, column=0, sticky="ew", pady=(0,3))
        tk.Label(outer, text=label, font=FONT_BOLD, bg=DARK, fg=MUTED).pack(anchor="w", pady=(0,3))
        card = tk.Frame(outer, bg=CARD, padx=12, pady=8); card.pack(fill="x")
        tk.Entry(card, textvariable=var, font=FONT_MONO, bg=INPUT_BG, fg=INPUT_FG,
                 insertbackground="black", relief="flat", bd=1).pack(side="left", fill="x", expand=True)
        tk.Button(card, text="Escolher", font=FONT_LABEL, bg=ACCENT, fg="white",
                  relief="flat", padx=8, pady=2, cursor="hand2", command=cmd).pack(side="right", padx=(8,0))

    def _dcb_slider_row(self, parent, label, var, from_, to, fmt, color):
        row = tk.Frame(parent, bg=CARD, pady=2); row.pack(fill="x")
        tk.Label(row, text=label, font=FONT_BOLD, bg=CARD, fg=MUTED, width=14, anchor="w").pack(side="left")
        val_lbl = tk.Label(row, text=fmt.format(var.get()), font=FONT_BOLD, bg=CARD, fg=color, width=8)
        val_lbl.pack(side="right")
        slider = ttk.Scale(row, from_=from_, to=to, variable=var, orient="horizontal",
                           command=lambda v, lbl=val_lbl, f=fmt: lbl.config(text=f.format(float(v))))
        slider.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._dcb_widgets.append(slider)

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
            self._single_outer.grid(); self._tts_single_outer.grid()
            self._batch_outer.grid_remove(); self._tts_batch_outer.grid_remove()
        else:
            self._btn_batch_outer.config(bg=ACCENT); self._btn_batch_inner.config(bg="#1a1830")
            for w in self._btn_batch_inner.winfo_children():
                try: w.config(bg="#1a1830")
                except: pass
            self._btn_single_outer.config(bg=MUTED); self._btn_single_inner.config(bg=CARD)
            for w in self._btn_single_inner.winfo_children():
                try: w.config(bg=CARD)
                except: pass
            self._single_outer.grid_remove(); self._tts_single_outer.grid_remove()
            self._batch_outer.grid(); self._tts_batch_outer.grid()

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
        path = filedialog.askopenfilename(title="Selecionar WAV",
            filetypes=[("WAV","*.wav"),("Todos","*.*")])
        if path: self.cw_path.set(path); self._log(f"📻 Copy White: {path}")

    def _toggle_cw(self):
        state = "normal" if self.cw_enabled.get() else "disabled"
        self.cw_entry.config(state=state); self.cw_slider.config(state=state)

    def _toggle_dcb(self):
        state = "normal" if self.dcb_enabled.get() else "disabled"
        for w in self._dcb_widgets: w.config(state=state)

    def _increment_variants(self):
        if self.n_variants.get() < 50: self.n_variants.set(self.n_variants.get() + 1)

    def _decrement_variants(self):
        if self.n_variants.get() > 0: self.n_variants.set(self.n_variants.get() - 1)

    def _sync_var_display(self):
        n = self.n_variants.get(); self.var_display.config(text=str(n))
        self.var_hint.config(text="sem variações" if n == 0 else f"+ {n} variação(ões)",
                             fg=MUTED if n == 0 else WARN)
        self.var_minus_btn.config(state="normal" if n > 0 else "disabled",
                                  fg=RED if n > 0 else MUTED)

    def _log(self, msg):
        def _do():
            if hasattr(self, '_log_section') and not self._log_section._open:
                self._log_section.open()
            self.log_box.config(state="normal"); self.log_box.insert("end", msg+"\n")
            self.log_box.see("end"); self.log_box.config(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self.log_box.config(state="normal"); self.log_box.delete("1.0","end")
        self.log_box.config(state="disabled")

    def _set_global_status(self, msg, color=None, pct=None):
        def _do():
            self.global_status.config(text=msg, fg=color or TEXT)
            if pct is not None: self.global_progress.config(value=pct)
        self.after(0, _do)

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
        if self._input_mode == "single": self._process_single()
        else: self._process_batch()

    def _process_single(self):
        vin = self._single_video.get().strip(); vout = self._single_output.get().strip()
        if not vin or not os.path.isfile(vin):
            messagebox.showerror("Erro", "Selecione um vídeo de entrada válido."); return
        if not vout: messagebox.showerror("Erro", "Defina o arquivo de saída."); return
        n = self.n_variants.get(); level = self.variation_level_selector.level
        noise = self._get_noise_amplitudes(); cw_path_val = None; cw_gain = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path_val = self.cw_path.get().strip()
            if not cw_path_val or not os.path.isfile(cw_path_val):
                messagebox.showerror("Erro","Copy White ativo mas sem WAV válido."); return
        self.running = True; self._batch_cancel = False
        self.run_btn.config(state="disabled", text="⏳  Processando…", bg=MUTED)
        self.cancel_btn.config(state="normal"); self.global_progress.config(value=0)
        self._set_global_status("Iniciando processamento…", TEXT, 0); self._clear_log()
        def worker():
            try:
                if self._proc_mode == "audio":
                    full_pipeline_audio(vin, vout, noise_amplitudes=noise,
                                        copy_white_path=cw_path_val, copy_white_gain=cw_gain,
                                        dcb_enabled=self.dcb_enabled.get(),
                                        dcb_threshold=self.dcb_threshold.get(),
                                        dcb_ratio=self.dcb_ratio.get(),
                                        dcb_makeup=self.dcb_makeup.get(),
                                        n_variants=n, variation_level=level,
                                        progress_cb=lambda p: self._set_global_status(f"Processando… {p}%", TEXT, p),
                                        log_cb=self._log)
                else:
                    full_pipeline_original(vin, vout, n_variants=n, variation_level=level,
                                           progress_cb=lambda p: self._set_global_status(f"Processando… {p}%", TEXT, p),
                                           log_cb=self._log)
                self._set_global_status(f"✅ Concluído! → {os.path.basename(vout)}", GREEN, 100)
                self.after(0, lambda: self.preview_tab.set_paths(orig=vin, proc=vout))
                self.after(0, lambda: messagebox.showinfo("Concluído!",
                    f"{1+n} arquivo(s).\n→ {vout}\n\nVeja o Preview na aba '🎬 Preview'"))
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
        n = self.n_variants.get(); level = self.variation_level_selector.level
        noise = self._get_noise_amplitudes(); cw_path_val = None; cw_gain = self.cw_gain.get()
        if self.cw_enabled.get():
            cw_path_val = self.cw_path.get().strip()
            if not cw_path_val or not os.path.isfile(cw_path_val):
                messagebox.showerror("Erro","Copy White ativo mas sem WAV válido."); return
        self.running = True; self._batch_cancel = False
        self.run_btn.config(state="disabled", text="⏳  Processando lote…", bg=MUTED)
        self.cancel_btn.config(state="normal"); self.global_progress.config(value=0)
        self._clear_log(); total = len(items)
        self._set_global_status(f"Lote iniciado: {total} vídeo(s)…", TEXT, 0)
        def worker():
            done = 0; errors = 0; last_ok_in = None; last_ok_out = None
            for idx, item in enumerate(items):
                if self._batch_cancel:
                    for rem in items[idx:]:
                        if rem.status == BatchQueueItem.STATUS_PENDING:
                            rem.set_status(BatchQueueItem.STATUS_CANCELLED, "Cancelado")
                    break
                vout = self._build_output_path(item.video_path); item.set_output(vout)
                def item_progress(pct, _item=item, _idx=idx, _total=total):
                    _item.set_status(BatchQueueItem.STATUS_RUNNING, f"Processando… {pct}%", pct)
                    self._set_global_status(f"[{_idx+1}/{_total}] {os.path.basename(_item.video_path)}  {pct}%",
                                            TEXT, int((_idx/_total)*100 + (pct/_total)))
                item.set_status(BatchQueueItem.STATUS_RUNNING, "Iniciando…", -1)
                try:
                    if self._proc_mode == "audio":
                        full_pipeline_audio(item.video_path, vout, noise_amplitudes=noise,
                                            copy_white_path=cw_path_val, copy_white_gain=cw_gain,
                                            dcb_enabled=self.dcb_enabled.get(),
                                            dcb_threshold=self.dcb_threshold.get(),
                                            dcb_ratio=self.dcb_ratio.get(),
                                            dcb_makeup=self.dcb_makeup.get(),
                                            n_variants=n, variation_level=level,
                                            progress_cb=item_progress,
                                            log_cb=lambda m, _i=item: self._log(f"[{os.path.basename(_i.video_path)}] {m}"))
                    else:
                        full_pipeline_original(item.video_path, vout, n_variants=n,
                                               variation_level=level, progress_cb=item_progress,
                                               log_cb=lambda m, _i=item: self._log(f"[{os.path.basename(_i.video_path)}] {m}"))
                    item.set_status(BatchQueueItem.STATUS_DONE, f"✅ Pronto → {os.path.basename(vout)}", 100)
                    done += 1; last_ok_in = item.video_path; last_ok_out = vout
                except Exception as e:
                    item.set_error(str(e))
                    item.set_status(BatchQueueItem.STATUS_ERROR, f"❌ {str(e)[:80]}", 0)
                    errors += 1; self._log(f"❌ ERRO [{os.path.basename(item.video_path)}]: {e}")
                self.after(0, self.batch_queue.update_stats)
            self.running = False
            summary = f"✅ Lote concluído: {done}/{total} OK" + (f"  ·  {errors} erro(s)" if errors else "")
            self._set_global_status(summary, GREEN if errors == 0 else WARN, 100)
            if last_ok_in and last_ok_out:
                self.after(0, lambda: self.preview_tab.set_paths(orig=last_ok_in, proc=last_ok_out))
            self.after(0, lambda: self.run_btn.config(state="normal", text="▶  PROCESSAR", bg=ACCENT))
            self.after(0, lambda: self.cancel_btn.config(state="disabled"))
            if not self._batch_cancel:
                self.after(0, lambda: messagebox.showinfo("Lote concluído",
                    f"{done} de {total} vídeos processados." +
                    (f"\n\n{errors} erro(s)." if errors else "") +
                    "\n\nVeja o Preview na aba '🎬 Preview'"))
        threading.Thread(target=worker, daemon=True).start()

    def _cancel_batch(self):
        if not self.running: return
        if messagebox.askyesno("Cancelar lote?",
                "Deseja cancelar?\nO vídeo atual será finalizado antes de parar."):
            self._batch_cancel = True
            self._set_global_status("⚠️  Cancelamento solicitado…", WARN)
            self.cancel_btn.config(state="disabled", text="Cancelando…")


# ═══════════════════════════════════════════════════════════════════════════════
#   SPLASH SCREEN
# ═══════════════════════════════════════════════════════════════════════════════

class SplashScreen(tk.Tk):
    WIDTH = 520; HEIGHT = 320
    def __init__(self):
        super().__init__()
        self.overrideredirect(True); self.configure(bg="#0d0d0f")
        self.attributes("-topmost", True); self.resizable(False, False)
        try: self.attributes("-alpha", 0.0)
        except: pass
        self._center(); self._done = False; self._angle = 0.0
        self._build(); self._fade_in()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2; y = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _build(self):
        self.canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT,
                                bg="#0d0d0f", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        cx, cy = self.WIDTH//2, 100; r = 44
        self._ring1 = self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=300,
                                             outline="#7c6af7", width=4, style="arc")
        self._ring2 = self.canvas.create_arc(cx-r+5, cy-r+5, cx+r-5, cy+r-5, start=60, extent=200,
                                             outline="#22d3ee", width=2, style="arc")
        self.canvas.create_text(cx, cy, text="🎛️", font=("Segoe UI Emoji", 22), fill="#e8e8f0")
        self.canvas.create_text(self.WIDTH//2, 158, text="AudioFix Pro",
                                font=("Segoe UI", 17, "bold"), fill="#e8e8f0")
        self.canvas.create_text(self.WIDTH//2, 178,
                                text=f"v{VERSAO_ATUAL}  ·  Edge TTS Neural · ElevenLabs · gTTS · Lote",
                                font=("Segoe UI", 8), fill="#6b6b80")
        bx1, by1, bx2, by2 = 55, 205, self.WIDTH-55, 217
        self.canvas.create_rectangle(bx1, by1, bx2, by2, fill="#16161a", outline="#1e1e24", width=1)
        self._bx1=bx1; self._by1=by1; self._bx2=bx2; self._by2=by2; self._bw=bx2-bx1
        self._bar_fill = self.canvas.create_rectangle(bx1, by1, bx1, by2, fill="#7c6af7", outline="")
        self._pct_txt  = self.canvas.create_text(self.WIDTH//2, 230, text="0%",
                                                  font=("Segoe UI",8,"bold"), fill="#7c6af7")
        self._step_txt = self.canvas.create_text(self.WIDTH//2, 246, text="Iniciando…",
                                                  font=("Segoe UI",8), fill="#6b6b80")
        self.canvas.create_rectangle(0, 0, self.WIDTH, 3, fill="#7c6af7", outline="")
        self.canvas.create_rectangle(0, self.HEIGHT-3, self.WIDTH, self.HEIGHT, fill="#14b8a6", outline="")

    def _fade_in(self, alpha=0.0):
        try: self.attributes("-alpha", alpha)
        except: pass
        if alpha < 1.0: self.after(16, lambda: self._fade_in(min(alpha+0.07, 1.0)))
        else: self._animate_ring()

    def _animate_ring(self):
        if self._done: return
        self._angle = (self._angle + 4) % 360
        try:
            self.canvas.itemconfig(self._ring1, start=self._angle)
            self.canvas.itemconfig(self._ring2, start=(self._angle+60)%360)
        except: pass
        self.after(18, self._animate_ring)

    def update_progress(self, pct, label=""):
        fw = int(self._bw * pct / 100)
        try:
            self.canvas.coords(self._bar_fill, self._bx1, self._by1, self._bx1+fw, self._by2)
            self.canvas.itemconfig(self._pct_txt, text=f"{int(pct)}%")
            if label: self.canvas.itemconfig(self._step_txt, text=label)
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

    step(0,  "Iniciando AudioFix Pro…",          0.15)
    step(10, "Verificando Python 3.8+…",         0.10)
    if sys.version_info < (3, 8): sys.exit(1)
    step(20, "Carregando numpy / scipy…",        0.10)
    _ensure_packages()
    step(38, "Verificando ffmpeg…",              0.15)
    global _FFMPEG_OK, _GTTS_OK, _EDGE_TTS_OK, _WHISPER_OK, _REQUESTS_OK
    _FFMPEG_OK   = _check_ffmpeg()
    step(50, "Verificando gTTS…",               0.10)
    _GTTS_OK     = _check_gtts_silent()
    step(60, "Verificando Edge TTS…",            0.10)
    _EDGE_TTS_OK = _check_edge_tts_silent()
    step(70, "Verificando Whisper…",             0.10)
    _WHISPER_OK  = _check_whisper_silent()
    step(80, "Verificando requests…",            0.05)
    _REQUESTS_OK = _check_requests_silent()
    step(88, "Carregando módulos de áudio…",     0.10)
    try:
        import numpy; from scipy.io import wavfile  # noqa
    except: pass
    step(95, "Construindo interface…",           0.20)
    step(100, "Pronto!",                         0.30)
    splash.after(0, lambda: splash.finish(_launch_main))


def _launch_main():
    app = AudioFixApp()
    app.mainloop()


if __name__ == "__main__":
    splash = SplashScreen()
    threading.Thread(target=_run_loading, args=(splash,), daemon=True).start()
    splash.mainloop()