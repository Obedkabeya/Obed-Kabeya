#!/usr/bin/env python3
"""
KBO Corporate Finance — serveur minimal (bibliothèque standard uniquement).

Sert le site statique du dossier ./public et expose une petite API JSON :

  GET    /api/articles              -> liste des articles (récents d'abord)
  GET    /api/articles/<id>         -> un article
  POST   /api/articles              -> créer un article        (auth admin)
  DELETE /api/articles/<id>         -> supprimer un article     (auth admin)
  GET    /api/admin/verify          -> vérifie le mot de passe  (auth admin)
  GET    /api/settings              -> réglages publics du site
  POST   /api/settings              -> enregistre les réglages   (auth admin)
  POST   /api/upload                -> upload d'image (base64)    (auth admin)
  POST   /api/apply/<slug>          -> enregistre une candidature (formation…)
  POST   /api/contact/<slug>        -> enregistre une demande de contact

Les données sont stockées dans ./data/*.json — aucune dépendance externe.

Lancement :
    python3 server.py            # http://localhost:8000
    PORT=9000 python3 server.py
    ADMIN_PASSWORD=secret python3 server.py

Envoi d'e-mail (optionnel, pour recevoir les messages du formulaire) :
    SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
    SMTP_USER=vous@gmail.com SMTP_PASS="mot-de-passe-application" \
    python3 server.py
"""

import base64
import hashlib
import json
import os
import re
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(ROOT, "public")
DATA_DIR = os.path.join(ROOT, "data")
UPLOAD_DIR = os.path.join(PUBLIC_DIR, "images", "uploads")   # base64 photo uploads (compat)
MEDIA_DIR = os.path.join(PUBLIC_DIR, "uploads")              # media library (images + vidéos)
ARTICLES_FILE = os.path.join(DATA_DIR, "articles.json")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
MEDIA_FILE = os.path.join(DATA_DIR, "media.json")
GALLERY_FILE = os.path.join(DATA_DIR, "gallery.json")
CONTENT_FILE = os.path.join(DATA_DIR, "content.json")      # remplacements de texte (édition en ligne)
IMGCONTENT_FILE = os.path.join(DATA_DIR, "imgcontent.json")  # remplacements d'images (édition en ligne)
SLIDES_FILE = os.path.join(DATA_DIR, "slides.json")          # carrousels d'images par emplacement
AUTH_FILE = os.path.join(DATA_DIR, "auth.json")            # mot de passe admin (haché)
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")   # sessions d'authentification (rôle admin)

SESSION_COOKIE = "kbo_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 jours

# ============================================================
#  Stockage : PostgreSQL (Railway) si DATABASE_URL est présent,
#  sinon fichiers JSON locaux (développement sur votre Mac).
#  La bascule est automatique — aucune configuration nécessaire.
# ============================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
try:
    if DATABASE_URL:
        import psycopg2
        from psycopg2.extras import Json as _PgJson
        DB_ENABLED = True
    else:
        DB_ENABLED = False
except Exception:            # psycopg2 absent → on reste sur les fichiers locaux
    DB_ENABLED = False


def _kv_key(path):
    """Clé de stockage = nom du fichier de données sans extension (ex. 'settings')."""
    return os.path.splitext(os.path.basename(path))[0]


import threading
_DB_LOCK = threading.Lock()
_DB_CONN = None


def _db_conn():
    """Connexion PostgreSQL réutilisée (rapide), rouverte si nécessaire."""
    global _DB_CONN
    if _DB_CONN is None or getattr(_DB_CONN, "closed", 1):
        _DB_CONN = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        _DB_CONN.autocommit = True
    return _DB_CONN


def _db_exec(run):
    """Exécute run(cursor) de façon thread-safe, avec une reconnexion si besoin."""
    global _DB_CONN
    with _DB_LOCK:
        for attempt in range(2):
            try:
                with _db_conn().cursor() as cur:
                    return run(cur)
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                try:
                    if _DB_CONN:
                        _DB_CONN.close()
                except Exception:
                    pass
                _DB_CONN = None
                if attempt == 1:
                    raise


def _db():
    """Contexte simple pour l'initialisation (avec ... as conn)."""
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = True
    return conn


def _kv_get(key, default):
    def run(cur):
        cur.execute("SELECT value FROM kv_store WHERE key=%s", (key,))
        row = cur.fetchone()
        return row[0] if row else default
    return _db_exec(run)


def _kv_set(key, value):
    def run(cur):
        cur.execute(
            "INSERT INTO kv_store(key, value, updated) VALUES (%s, %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated = now()",
            (key, _PgJson(value)))
    _db_exec(run)


def _file_put(rel_path, data, mime):
    def run(cur):
        cur.execute(
            "INSERT INTO files(path, mime, data, added) VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (path) DO UPDATE SET data = EXCLUDED.data, mime = EXCLUDED.mime",
            (rel_path, mime, psycopg2.Binary(data)))
    _db_exec(run)


def _file_get(rel_path):
    def run(cur):
        cur.execute("SELECT data, mime FROM files WHERE path=%s", (rel_path,))
        row = cur.fetchone()
        if not row:
            return None
        return bytes(row[0]), (row[1] or "application/octet-stream")
    return _db_exec(run)


def _file_delete(rel_path):
    def run(cur):
        cur.execute("DELETE FROM files WHERE path=%s", (rel_path,))
    _db_exec(run)

PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "kbo-admin")

# SMTP — configuré UNIQUEMENT par variables d'environnement (jamais dans un fichier,
# pour ne jamais exposer le mot de passe sur GitHub). Minimum requis : SMTP_USER + SMTP_PASS.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
try:
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
except ValueError:
    SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "")            # mot de passe d'application Gmail
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER

# Textes éditables du site (clés utilisées côté page via data-text="clé").
DEFAULT_TEXTS = {
    "brandMark": "KBO",
    "brandSub": "corporate finance",
    "heroEyebrow": "KBO Corporate Finance",
    "name": "Obed Kabeya",
    "role": "banquier de marché & trader",
    "presentation": (
        "Depuis dix ans, j'interviens sur différents marchés. Je partage ma passion "
        "pour la finance des marchés, l'écriture et la réflexion stratégique — avec la "
        "conviction qu'une décision lucide naît d'une pensée claire."
    ),
    "homePathsTitle": "Par où souhaitez-vous commencer ?",
    "homePathsIntro": (
        "Un versant personnel, fait de récits et de réflexions. Un versant professionnel, "
        "structuré autour de trois services exigeants."
    ),
    "homePhilosophyTitle": "Une finance lucide, exigeante et transmissible.",
    "homePhilosophyText": (
        "Les marchés récompensent la discipline, pas l'improvisation. J'aborde chaque "
        "position, chaque conseil et chaque formation avec la même rigueur : comprendre "
        "avant d'agir, structurer avant de risquer, transmettre ce qui a fait ses preuves."
    ),
    "footerAbout": (
        "Obed Kabeya — banquier de marché & trader. Formation, structuration comptable et "
        "conseil en investissement, au service d'une finance lucide et exigeante."
    ),
    "contactTitle": "Entrons en relation.",
    "contactIntro": (
        "Une question, un projet, une envie de collaborer ? Écrivez-moi directement — "
        "je réponds personnellement à chaque message."
    ),
}

# Réglages par défaut du site (modifiables via le tableau de bord /admin.html).
DEFAULT_SETTINGS = {
    "email": "Obedkabeya1996@gmail.com",
    "presentation": DEFAULT_TEXTS["presentation"],
    "photo": "images/portrait.svg",
    "social": {
        "linkedin": "https://www.linkedin.com",
        "x": "https://x.com",
        "youtube": "https://youtube.com",
        "facebook": "",
        "instagram": "",
    },
    "texts": dict(DEFAULT_TEXTS),
    "images": {
        "bio1": "images/journey.svg",
        "bio2": "images/markets.svg",
        "bio3": "images/writing.svg",
    },
}

# Emplacements d'images éditables sur la page Biographie.
BIO_IMAGE_KEYS = ["bio1", "bio2", "bio3"]

ALLOWED_IMAGE_MIME = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/webp": ".webp", "image/gif": ".gif",
}
# Extensions autorisées pour la bibliothèque de médias (images + vidéos).
ALLOWED_MEDIA_EXT = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
    ".mp4": "video", ".webm": "video", ".mov": "video", ".m4v": "video",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024          # base64 photo
MAX_MEDIA_BYTES = 200 * 1024 * 1024         # upload brut (vidéos verticales incluses)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
}


# ----------------------------- storage helpers -----------------------------
# NB : mail.json n'est plus utilisé (SMTP vient des variables d'environnement).
_DATA_FILES = [ARTICLES_FILE, SUBMISSIONS_FILE, SETTINGS_FILE, MEDIA_FILE, GALLERY_FILE,
               CONTENT_FILE, IMGCONTENT_FILE, SLIDES_FILE, AUTH_FILE, SESSIONS_FILE]
_LIST_KEYS = {"articles", "submissions", "media", "gallery"}


def _default_for(key):
    if key == "settings":
        return DEFAULT_SETTINGS
    return [] if key in _LIST_KEYS else {}


def _db_init():
    """Crée les tables et importe (une seule fois) les données et images
    livrées avec le site vers PostgreSQL. Ainsi rien n'est perdu à la mise
    en ligne, et tout devient permanent."""
    with _db() as conn, conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS kv_store ("
                    "key TEXT PRIMARY KEY, value JSONB NOT NULL, updated TIMESTAMPTZ DEFAULT now())")
        cur.execute("CREATE TABLE IF NOT EXISTS files ("
                    "path TEXT PRIMARY KEY, mime TEXT, data BYTEA, added TIMESTAMPTZ DEFAULT now())")
        for path in _DATA_FILES:
            key = _kv_key(path)
            cur.execute("SELECT 1 FROM kv_store WHERE key=%s", (key,))
            if cur.fetchone():
                continue
            val = None
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        val = json.load(f)
                except Exception:
                    val = None
            if val is None:
                val = _default_for(key)
            cur.execute("INSERT INTO kv_store(key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (key, _PgJson(val)))
        for folder, prefix in ((MEDIA_DIR, "uploads"), (UPLOAD_DIR, "images/uploads")):
            if not os.path.isdir(folder):
                continue
            for name in os.listdir(folder):
                if name.startswith("."):
                    continue
                rel = prefix + "/" + name
                cur.execute("SELECT 1 FROM files WHERE path=%s", (rel,))
                if cur.fetchone():
                    continue
                try:
                    with open(os.path.join(folder, name), "rb") as f:
                        data = f.read()
                except Exception:
                    continue
                mime = CONTENT_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
                cur.execute("INSERT INTO files(path, mime, data) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (rel, mime, psycopg2.Binary(data)))
    print("  [DB] PostgreSQL initialisé — données permanentes.", flush=True)


def _ensure_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    if DB_ENABLED:
        _db_init()
        return
    if not os.path.exists(ARTICLES_FILE):
        _write_json(ARTICLES_FILE, [])
    if not os.path.exists(SUBMISSIONS_FILE):
        _write_json(SUBMISSIONS_FILE, [])
    if not os.path.exists(SETTINGS_FILE):
        _write_json(SETTINGS_FILE, DEFAULT_SETTINGS)
    if not os.path.exists(MEDIA_FILE):
        _write_json(MEDIA_FILE, [])
    if not os.path.exists(GALLERY_FILE):
        _write_json(GALLERY_FILE, [])
    if not os.path.exists(CONTENT_FILE):
        _write_json(CONTENT_FILE, {})
    if not os.path.exists(IMGCONTENT_FILE):
        _write_json(IMGCONTENT_FILE, {})
    if not os.path.exists(SLIDES_FILE):
        _write_json(SLIDES_FILE, {})


def _get_settings():
    """Read settings, back-filling any missing keys from the defaults."""
    data = _read_json(SETTINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    texts_in = data.get("texts") if isinstance(data.get("texts"), dict) else {}
    texts = {}
    for key, default in DEFAULT_TEXTS.items():
        texts[key] = texts_in.get(key, default)
    # Compat : ancien champ presentation à la racine → texts.presentation
    if data.get("presentation") and not texts_in.get("presentation"):
        texts["presentation"] = data["presentation"]

    images_in = data.get("images") if isinstance(data.get("images"), dict) else {}
    images = {}
    for key, default in DEFAULT_SETTINGS["images"].items():
        images[key] = images_in.get(key) or default

    merged = {
        "email": data.get("email") or DEFAULT_SETTINGS["email"],
        "presentation": texts["presentation"],
        "photo": data.get("photo") or DEFAULT_SETTINGS["photo"],
        "social": {},
        "texts": texts,
        "images": images,
    }
    social = data.get("social") if isinstance(data.get("social"), dict) else {}
    for key in DEFAULT_SETTINGS["social"]:
        merged["social"][key] = social.get(key, DEFAULT_SETTINGS["social"][key]) or ""
    return merged


def _read_json(path, default):
    if DB_ENABLED:
        try:
            return _kv_get(_kv_key(path), default)
        except Exception as e:
            print("  [DB] lecture échouée (%s) → repli fichier : %s" % (_kv_key(path), e), flush=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    if DB_ENABLED:
        try:
            _kv_set(_kv_key(path), data)
            return
        except Exception as e:
            print("  [DB] écriture échouée (%s) → repli fichier : %s" % (_kv_key(path), e), flush=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _clean(value, limit=5000):
    """Trim + length-limit user text. Rendering is escaped client-side, so we
    store raw text here (escaping in both places would double-encode)."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").strip()
    # Drop control chars except newline/tab.
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


_ALLOWED_TAGS = {"strong", "b", "em", "i", "u", "br", "span", "a"}


def _sanitize_html(value, limit=20000):
    """Keep only a small allowlist of inline tags; drop scripts, styles and
    event handlers. Content is authored by the authenticated admin only."""
    if value is None:
        return ""
    text = str(value)[:limit]
    # Remove whole script/style blocks.
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", text)
    # Strip on*="" event handlers and javascript: URLs.
    text = re.sub(r'(?i)\son\w+\s*=\s*"[^"]*"', "", text)
    text = re.sub(r"(?i)\son\w+\s*=\s*'[^']*'", "", text)
    text = re.sub(r"(?i)javascript:", "", text)

    def _keep(m):
        raw = m.group(0)
        tag = (m.group(1) or "").lower()
        if tag not in _ALLOWED_TAGS:
            return ""  # remove disallowed tag, keep inner text
        if tag == "a":
            href = re.search(r'href\s*=\s*"([^"]*)"', raw, re.I)
            url = href.group(1) if href else "#"
            if raw.lstrip().startswith("</"):
                return "</a>"
            return '<a href="%s" target="_blank" rel="noopener">' % url.replace('"', "%22")
        if raw.lstrip().startswith("</"):
            return "</%s>" % tag
        if tag == "br":
            return "<br>"
        return "<%s>" % tag

    text = re.sub(r"</?\s*([a-zA-Z0-9]+)[^>]*>", _keep, text)
    return text.strip()


def _drain(rfile, length):
    """Discard `length` bytes from the request body (keeps the socket clean)."""
    remaining = length
    while remaining > 0:
        chunk = rfile.read(min(65536, remaining))
        if not chunk:
            break
        remaining -= len(chunk)


# ----------------------------- auth (mot de passe) -----------------------------
def _hash_pw(pw, salt):
    return hashlib.sha256((salt + ":" + pw).encode("utf-8")).hexdigest()


def _check_password(pw):
    """True if pw matches the stored admin password (or the default when none set)."""
    if not pw:
        return False
    auth = _read_json(AUTH_FILE, None)
    if isinstance(auth, dict) and auth.get("hash") and auth.get("salt"):
        return _hash_pw(pw, auth["salt"]) == auth["hash"]
    return pw == ADMIN_PASSWORD  # aucun mot de passe personnalisé → valeur par défaut/env


def _set_password(pw):
    salt = uuid.uuid4().hex
    _write_json(AUTH_FILE, {"salt": salt, "hash": _hash_pw(pw, salt)})


# ----------------------------- sessions (rôles) -----------------------------
def _load_sessions():
    s = _read_json(SESSIONS_FILE, {})
    return s if isinstance(s, dict) else {}


def _new_session(role="admin"):
    sessions = _load_sessions()
    # purge des sessions expirées
    now = datetime.utcnow().timestamp()
    sessions = {t: v for t, v in sessions.items()
                if now - float(v.get("ts", 0)) < SESSION_MAX_AGE}
    token = uuid.uuid4().hex + uuid.uuid4().hex
    sessions[token] = {"role": role, "ts": now}
    _write_json(SESSIONS_FILE, sessions)
    return token


def _session_role(token):
    if not token:
        return None
    v = _load_sessions().get(token)
    if not v:
        return None
    if datetime.utcnow().timestamp() - float(v.get("ts", 0)) >= SESSION_MAX_AGE:
        return None
    return v.get("role")


def _destroy_session(token):
    if not token:
        return
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _write_json(SESSIONS_FILE, sessions)


# ----------------------------- e-mail (SMTP) -----------------------------
def _get_mail():
    """Configuration SMTP lue UNIQUEMENT dans les variables d'environnement.
    Aucun secret n'est stocké dans un fichier (donc rien à fuiter sur GitHub)."""
    return {
        "host": SMTP_HOST or "smtp.gmail.com",
        "port": SMTP_PORT or 587,
        "user": SMTP_USER,
        "pass": SMTP_PASS,
        "from": SMTP_FROM or SMTP_USER,
    }


def _send_email(to_addr, subject, body, reply_to=None):
    """Send an e-mail via SMTP if configured. Returns (sent: bool, detail: str)."""
    cfg = _get_mail()
    if not (cfg["host"] and cfg["user"] and cfg["pass"]):
        return False, "SMTP non configuré"
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from"] or cfg["user"]
        msg["To"] = to_addr
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls(context=context)
            s.login(cfg["user"], cfg["pass"])
            s.send_message(msg)
        return True, "envoyé"
    except Exception as exc:  # noqa: BLE001 - report but never crash the request
        return False, "erreur SMTP: %s" % exc


def _save_upload(data_url):
    """Decode a base64 data URL image and store it under public/images/uploads.
    Returns (rel_path, error)."""
    m = re.match(r"^data:([\w/+.\-]+);base64,(.+)$", data_url or "", re.DOTALL)
    if not m:
        return None, "Format d'image invalide."
    mime = m.group(1).lower()
    if mime not in ALLOWED_IMAGE_MIME:
        return None, "Type d'image non supporté (PNG, JPG, WEBP ou GIF)."
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        return None, "Image illisible."
    if len(raw) > MAX_UPLOAD_BYTES:
        return None, "Image trop lourde (max 5 Mo)."
    ext = ALLOWED_IMAGE_MIME[mime]
    name = "photo-%s%s" % (uuid.uuid4().hex[:10], ext)
    rel = "images/uploads/%s" % name
    _store_upload(rel, raw, CONTENT_TYPES.get(ext, "image/jpeg"), os.path.join(UPLOAD_DIR, name))
    return rel, None


def _store_upload(rel_path, data, mime, disk_path):
    """Enregistre un fichier téléversé : base PostgreSQL si active, sinon disque."""
    if DB_ENABLED:
        _file_put(rel_path, data, mime)
    else:
        with open(disk_path, "wb") as f:
            f.write(data)


# ----------------------------- request handler -----------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "KBO/1.0"

    # ---- utilities ----
    def _send_json(self, obj, status=200, cookies=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for c in (cookies or []):
            self.send_header("Set-Cookie", c)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > 12_000_000:  # allows a ~5 Mo base64 image upload
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _get_cookie(self, name):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == name:
                    return v
        return None

    def _role(self):
        """Rôle de la requête : 'admin' si session valide (ou en-tête mot de passe
        pour les outils/API), sinon 'visitor'."""
        role = _session_role(self._get_cookie(SESSION_COOKIE))
        if role == "admin":
            return "admin"
        if _check_password(self.headers.get("X-Admin-Password", "")):
            return "admin"
        return "visitor"

    def _is_admin(self):
        return self._role() == "admin"

    def _set_cookie(self, name, value, max_age):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s" % (name, value, max_age, secure)

    def log_message(self, fmt, *args):
        print("  %s - %s" % (self.address_string(), fmt % args))

    # ---- routing ----
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api_get(path)
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api_post(path)
        self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/articles/([^/]+)$", path)
        if m:
            return self._delete_article(m.group(1))
        m = re.match(r"^/api/media/([^/]+)$", path)
        if m:
            return self._delete_media(m.group(1))
        m = re.match(r"^/api/gallery/([^/]+)$", path)
        if m:
            return self._delete_gallery(m.group(1))
        self._send_json({"error": "Not found"}, 404)

    # ---- API: GET ----
    def _api_get(self, path):
        if path == "/api/me":
            return self._send_json({"role": self._role()})

        if path == "/api/articles":
            articles = _read_json(ARTICLES_FILE, [])
            articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)
            return self._send_json(articles)

        m = re.match(r"^/api/articles/([^/]+)$", path)
        if m:
            aid = m.group(1)
            for a in _read_json(ARTICLES_FILE, []):
                if a.get("id") == aid:
                    return self._send_json(a)
            return self._send_json({"error": "Article introuvable"}, 404)

        if path == "/api/admin/verify":
            if self._is_admin():
                return self._send_json({"ok": True})
            return self._send_json({"error": "Non autorisé"}, 401)

        if path == "/api/settings":
            settings = _get_settings()
            settings["_emailConfigured"] = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)
            return self._send_json(settings)

        if path == "/api/media":
            return self._list_media()

        if path == "/api/gallery":
            return self._list_gallery()

        if path == "/api/content":
            return self._send_json(_read_json(CONTENT_FILE, {}))

        if path == "/api/imgcontent":
            return self._send_json(_read_json(IMGCONTENT_FILE, {}))

        if path == "/api/slides":
            return self._send_json(_read_json(SLIDES_FILE, {}))

        if path == "/api/mailconfig":  # admin only, never exposes the password
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            cfg = _get_mail()
            return self._send_json({"host": cfg["host"], "port": cfg["port"], "user": cfg["user"],
                                    "from": cfg["from"], "hasPass": bool(cfg["pass"]),
                                    "active": bool(cfg["host"] and cfg["user"] and cfg["pass"])})

        if path == "/api/submissions":  # admin-only inbox
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            subs = _read_json(SUBMISSIONS_FILE, [])
            return self._send_json(sorted(subs, key=lambda s: s.get("received", ""), reverse=True))

        return self._send_json({"error": "Not found"}, 404)

    # ---- API: POST ----
    def _api_post(self, path):
        if path == "/api/login":
            return self._login()

        if path == "/api/logout":
            return self._logout()

        if path == "/api/articles":
            return self._create_article()

        if path == "/api/settings":
            return self._save_settings()

        if path == "/api/settings/image":
            return self._save_one_image()

        if path == "/api/settings/text":
            return self._save_one_text()

        if path == "/api/content":
            return self._save_content()

        if path == "/api/imgcontent":
            return self._save_imgcontent()

        if path == "/api/slides":
            return self._save_slides()

        if path == "/api/admin/password":
            return self._change_password()

        if path == "/api/mailtest":
            return self._send_test_email()

        if path == "/api/upload":
            return self._upload_image()

        if path == "/api/upload-raw":
            return self._upload_raw()

        if path == "/api/gallery":
            return self._create_gallery()

        m = re.match(r"^/api/gallery/([^/]+)$", path)
        if m:
            return self._update_gallery(m.group(1))

        m = re.match(r"^/api/(apply|contact)/([a-z0-9\-]+)$", path)
        if m:
            return self._save_submission(category=m.group(1), slug=m.group(2))

        self._send_json({"error": "Not found"}, 404)

    def _save_settings(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        if not isinstance(data, dict):
            return self._send_json({"error": "Requête invalide"}, 400)

        current = _get_settings()
        email = _clean(data.get("email"), 200) or current["email"]
        if not EMAIL_RE.match(email):
            return self._send_json({"error": "Adresse e-mail invalide."}, 400)

        social_in = data.get("social") if isinstance(data.get("social"), dict) else {}
        social = {}
        for key in DEFAULT_SETTINGS["social"]:
            val = _clean(social_in.get(key), 300)
            if val and not re.match(r"^https?://", val, re.I):
                val = "https://" + val
            social[key] = val

        texts_in = data.get("texts") if isinstance(data.get("texts"), dict) else {}
        texts = {}
        for key in DEFAULT_TEXTS:
            val = _clean(texts_in.get(key), 2000)
            texts[key] = val if val else current["texts"].get(key, DEFAULT_TEXTS[key])

        images_in = data.get("images") if isinstance(data.get("images"), dict) else {}
        images = {}
        for key in DEFAULT_SETTINGS["images"]:
            images[key] = _clean(images_in.get(key), 400) or current["images"].get(key, DEFAULT_SETTINGS["images"][key])

        settings = {
            "email": email,
            "presentation": texts["presentation"],
            "photo": _clean(data.get("photo"), 400) or current["photo"],
            "social": social,
            "texts": texts,
            "images": images,
        }
        _write_json(SETTINGS_FILE, settings)
        settings["_emailConfigured"] = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)
        return self._send_json({"ok": True, "settings": settings})

    def _save_one_image(self):
        """Met à jour une seule image du site (édition en ligne depuis la biographie)."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        key = _clean(data.get("key"), 40)
        path = _clean(data.get("path"), 400)
        valid = key in DEFAULT_SETTINGS["images"] or key == "photo"
        if not valid or not path:
            return self._send_json({"error": "Requête invalide"}, 400)
        settings = _get_settings()
        if key == "photo":
            settings["photo"] = path       # photo de profil (accueil)
        else:
            settings["images"][key] = path
        settings.pop("_emailConfigured", None)
        _write_json(SETTINGS_FILE, settings)
        return self._send_json({"ok": True, "images": settings["images"]})

    def _save_one_text(self):
        """Met à jour un des textes « réglages » (nom, rôle, logo, présentation…)
        depuis l'édition en ligne. La clé doit exister dans DEFAULT_TEXTS."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        key = _clean(data.get("key"), 60)
        if key not in DEFAULT_TEXTS:
            return self._send_json({"error": "Clé inconnue"}, 400)
        value = _sanitize_html(data.get("value"), 4000)
        settings = _get_settings()
        settings["texts"][key] = value
        if key == "presentation":
            settings["presentation"] = value
        settings.pop("_emailConfigured", None)
        _write_json(SETTINGS_FILE, settings)
        return self._send_json({"ok": True})

    def _save_content(self):
        """Enregistre le remplacement d'un texte libre du site (biographie,
        pages services…), identifié par sa clé d'emplacement."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        key = _clean(data.get("key"), 300)
        if not key:
            return self._send_json({"error": "Clé manquante"}, 400)
        content = _read_json(CONTENT_FILE, {})
        if not isinstance(content, dict):
            content = {}
        value = _sanitize_html(data.get("value"), 20000)
        if value == "":
            content.pop(key, None)          # texte vidé → on revient au défaut
        else:
            content[key] = value
        _write_json(CONTENT_FILE, content)
        return self._send_json({"ok": True})

    def _save_imgcontent(self):
        """Remplace une image du site (par emplacement) par une image téléversée."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        key = _clean(data.get("key"), 300)
        path = _clean(data.get("path"), 500)
        if not key:
            return self._send_json({"error": "Clé manquante"}, 400)
        imgs = _read_json(IMGCONTENT_FILE, {})
        if not isinstance(imgs, dict):
            imgs = {}
        if not path:
            imgs.pop(key, None)             # revient à l'image d'origine
        else:
            imgs[key] = path
        _write_json(IMGCONTENT_FILE, imgs)
        return self._send_json({"ok": True})

    def _save_slides(self):
        """Enregistre le carrousel d'images d'un emplacement (liste ordonnée)."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        key = _clean(data.get("key"), 300)
        if not key:
            return self._send_json({"error": "Clé manquante"}, 400)
        paths = data.get("paths")
        clean = []
        if isinstance(paths, list):
            for p in paths[:30]:
                cp = _clean(p, 500)
                if cp:
                    clean.append(cp)
        slides = _read_json(SLIDES_FILE, {})
        if not isinstance(slides, dict):
            slides = {}
        if clean:
            slides[key] = clean
        else:
            slides.pop(key, None)           # vide → revient à l'image par défaut
        _write_json(SLIDES_FILE, slides)
        return self._send_json({"ok": True, "paths": clean})

    def _login(self):
        """Authentifie le propriétaire et ouvre une session (cookie HttpOnly)."""
        data = self._read_body()
        if not _check_password(str(data.get("password") or "")):
            return self._send_json({"error": "Mot de passe incorrect."}, 401)
        token = _new_session("admin")
        cookie = self._set_cookie(SESSION_COOKIE, token, SESSION_MAX_AGE)
        return self._send_json({"ok": True, "role": "admin"}, cookies=[cookie])

    def _logout(self):
        _destroy_session(self._get_cookie(SESSION_COOKIE))
        cleared = self._set_cookie(SESSION_COOKIE, "", 0)
        return self._send_json({"ok": True}, cookies=[cleared])

    def _change_password(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        new = str(data.get("new") or "").strip()
        if len(new) < 4:
            return self._send_json({"error": "Le nouveau mot de passe doit faire au moins 4 caractères."}, 400)
        _set_password(new)
        return self._send_json({"ok": True})

    def _send_test_email(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        recipient = _get_settings()["email"]
        sent, detail = _send_email(recipient, "Test — KBO Corporate Finance",
                                   "Ceci est un e-mail de test envoyé depuis votre tableau de bord.\n"
                                   "Si vous le recevez, la configuration e-mail fonctionne. ✓")
        if sent:
            return self._send_json({"ok": True, "to": recipient})
        return self._send_json({"ok": False, "error": detail}, 400)

    def _upload_image(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        rel, err = _save_upload(data.get("dataUrl"))
        if err:
            return self._send_json({"error": err}, 400)
        return self._send_json({"ok": True, "path": rel}, 201)

    def _upload_raw(self):
        """Streamed binary upload for the media library (images + vidéos verticales).
        Body = octets du fichier ; en-têtes X-Filename + Content-Type."""
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0:
            return self._send_json({"error": "Fichier vide."}, 400)
        if length > MAX_MEDIA_BYTES:
            return self._send_json({"error": "Fichier trop lourd (max 200 Mo)."}, 413)

        orig = self.headers.get("X-Filename", "fichier")
        ext = os.path.splitext(orig)[1].lower()
        if ext not in ALLOWED_MEDIA_EXT:
            # rattrapage via le type MIME
            ctype = (self.headers.get("Content-Type", "") or "").split(";")[0].lower()
            guess = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
                     "image/gif": ".gif", "video/mp4": ".mp4", "video/webm": ".webm",
                     "video/quicktime": ".mov"}.get(ctype)
            ext = guess or ""
        if ext not in ALLOWED_MEDIA_EXT:
            # vider le corps pour garder la connexion propre
            _drain(self.rfile, length)
            return self._send_json({"error": "Type de fichier non supporté (images ou vidéos)."}, 400)

        kind = ALLOWED_MEDIA_EXT[ext]
        name = "%s-%s%s" % (kind, uuid.uuid4().hex[:10], ext)
        rel = "uploads/%s" % name
        mime = CONTENT_TYPES.get(ext, "application/octet-stream")
        # Lire le corps en mémoire (permet le stockage base de données)
        buf = bytearray()
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            buf.extend(chunk)
            remaining -= len(chunk)
        written = len(buf)
        try:
            _store_upload(rel, bytes(buf), mime, os.path.join(MEDIA_DIR, name))
        except Exception as exc:
            return self._send_json({"error": "Écriture impossible : %s" % exc}, 500)
        entry = {
            "name": name,
            "path": rel,
            "kind": kind,
            "size": written,
            "title": _clean(orig, 160),
            "added": datetime.utcnow().isoformat() + "Z",
        }
        media = _read_json(MEDIA_FILE, [])
        media.append(entry)
        _write_json(MEDIA_FILE, media)
        return self._send_json({"ok": True, "path": rel, "kind": kind, "name": name}, 201)

    def _list_media(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        media = _read_json(MEDIA_FILE, [])
        return self._send_json(sorted(media, key=lambda m: m.get("added", ""), reverse=True))

    def _delete_media(self, name):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        if "/" in name or "\\" in name or ".." in name:
            return self._send_json({"error": "Nom invalide"}, 400)
        media = _read_json(MEDIA_FILE, [])
        remaining = [m for m in media if m.get("name") != name]
        if DB_ENABLED:
            try:
                _file_delete("uploads/" + name)
            except Exception:
                pass
        else:
            try:
                fp = os.path.join(MEDIA_DIR, name)
                if os.path.isfile(fp):
                    os.remove(fp)
            except OSError:
                pass
        _write_json(MEDIA_FILE, remaining)
        return self._send_json({"ok": True})

    # ---- galerie / album (photos + vidéos verticales) ----
    def _list_gallery(self):
        items = _read_json(GALLERY_FILE, [])
        query = urlparse(self.path).query
        want_all = "all=1" in query and self._is_admin()
        if not want_all:
            items = [g for g in items if g.get("published", True)]
        return self._send_json(sorted(items, key=lambda g: g.get("added", ""), reverse=True))

    def _create_gallery(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        path = _clean(data.get("path"), 500)
        if not path:
            return self._send_json({"error": "Aucun média fourni."}, 400)
        kind = "video" if data.get("kind") == "video" else "image"
        item = {
            "id": uuid.uuid4().hex[:12],
            "path": path,
            "kind": kind,
            "orientation": "vertical" if data.get("orientation") == "vertical" else "landscape",
            "caption": _clean(data.get("caption"), 200),
            "published": data.get("published", True) is not False,
            "added": datetime.utcnow().isoformat() + "Z",
        }
        items = _read_json(GALLERY_FILE, [])
        items.append(item)
        _write_json(GALLERY_FILE, items)
        return self._send_json({"ok": True, "item": item}, 201)

    def _update_gallery(self, gid):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        items = _read_json(GALLERY_FILE, [])
        found = None
        for g in items:
            if g.get("id") == gid:
                found = g
                if "published" in data:
                    g["published"] = bool(data.get("published"))
                if "caption" in data:
                    g["caption"] = _clean(data.get("caption"), 200)
                break
        if not found:
            return self._send_json({"error": "Introuvable"}, 404)
        _write_json(GALLERY_FILE, items)
        return self._send_json({"ok": True, "item": found})

    def _delete_gallery(self, gid):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        items = _read_json(GALLERY_FILE, [])
        remaining = [g for g in items if g.get("id") != gid]
        if len(remaining) == len(items):
            return self._send_json({"error": "Introuvable"}, 404)
        _write_json(GALLERY_FILE, remaining)
        return self._send_json({"ok": True})

    def _create_article(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        title = _clean(data.get("title"), 200)
        excerpt = _clean(data.get("excerpt"), 400)
        if not title or not excerpt:
            return self._send_json({"error": "Le titre et l'extrait sont obligatoires."}, 400)

        the_date = _clean(data.get("date"), 20) or date.today().isoformat()
        kind = data.get("type")
        atype = kind if kind in ("video", "story") else "article"
        orientation = "vertical" if data.get("orientation") == "vertical" else "landscape"
        article = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "type": atype,                                  # article | story | video
            "tag": _clean(data.get("tag"), 40),
            "date": the_date,
            "image": _clean(data.get("image"), 500),
            "video": _clean(data.get("video"), 500),        # lien YouTube/Vimeo (optionnel)
            "videoFile": _clean(data.get("videoFile"), 500),  # vidéo téléversée (mp4/webm/mov)
            "orientation": orientation,                     # vertical (mobile) | landscape
            "excerpt": excerpt,
            "body": _clean(data.get("body"), 20000),
            "created": datetime.utcnow().isoformat() + "Z",
        }
        articles = _read_json(ARTICLES_FILE, [])
        articles.append(article)
        _write_json(ARTICLES_FILE, articles)
        return self._send_json(article, 201)

    def _delete_article(self, aid):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        articles = _read_json(ARTICLES_FILE, [])
        remaining = [a for a in articles if a.get("id") != aid]
        if len(remaining) == len(articles):
            return self._send_json({"error": "Article introuvable"}, 404)
        _write_json(ARTICLES_FILE, remaining)
        return self._send_json({"ok": True})

    def _save_submission(self, category, slug):
        data = self._read_body()
        if not isinstance(data, dict) or not data:
            return self._send_json({"error": "Requête invalide"}, 400)

        fields = {}
        for k, v in data.items():
            if k.startswith("_"):
                continue
            fields[_clean(k, 60)] = _clean(v, 5000)

        if not fields.get("email"):
            return self._send_json({"error": "Une adresse e-mail est requise."}, 400)

        entry = {
            "id": uuid.uuid4().hex[:12],
            "category": category,      # apply | contact
            "service": slug,           # formation | comptabilite | conseil | general
            "kind": _clean(data.get("_kind"), 80),
            "fields": fields,
            "received": datetime.utcnow().isoformat() + "Z",
        }
        subs = _read_json(SUBMISSIONS_FILE, [])
        subs.append(entry)
        _write_json(SUBMISSIONS_FILE, subs)

        # Deliver to the address configured in Paramètres.
        recipient = _get_settings()["email"]
        subject = "%s — %s" % (entry["kind"] or "Nouveau message", fields.get("nom", "sans nom"))
        lines = ["Nouveau message reçu depuis le site KBO Corporate Finance.", ""]
        lines.append("Catégorie : %s / %s" % (category, slug))
        for k, v in fields.items():
            lines.append("%s : %s" % (k, v))
        lines += ["", "Reçu le %s" % entry["received"]]
        sent, detail = _send_email(recipient, subject, "\n".join(lines),
                                   reply_to=fields.get("email"))
        entry["emailed"] = sent

        # Mirror to the server log so Obed sees it live.
        print("\n  ✉  Nouvelle soumission [%s/%s] de %s <%s> — e-mail: %s"
              % (category, slug, fields.get("nom", "?"), fields.get("email", "?"),
                 "envoyé à %s" % recipient if sent else detail), flush=True)
        return self._send_json({"ok": True, "id": entry["id"]}, 201)

    # ---- static files ----
    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        # Extensionless -> .html (e.g. /contact -> contact.html)
        rel = path.lstrip("/")
        candidate = os.path.join(PUBLIC_DIR, rel)
        if not os.path.splitext(candidate)[1] and not os.path.isdir(candidate):
            if os.path.exists(candidate + ".html"):
                rel += ".html"
                candidate += ".html"

        full = os.path.normpath(os.path.join(PUBLIC_DIR, rel))
        # Prevent path traversal outside PUBLIC_DIR
        if not full.startswith(PUBLIC_DIR):
            self.send_error(403, "Forbidden")
            return

        # Fichiers téléversés : servis depuis PostgreSQL en production
        # (le disque de Railway est éphémère).
        if DB_ENABLED and (rel.startswith("uploads/") or rel.startswith("images/uploads/")):
            try:
                hit = _file_get(rel)
            except Exception:
                hit = None
            if hit is not None:
                data, mime = hit
                if os.path.splitext(rel)[1].lower() in (".mp4", ".webm", ".mov", ".m4v"):
                    return self._serve_bytes_ranged(data, mime)
                return self._send_bytes(data, mime, cache=True)

        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            # SPA-ish fallback: serve 404 page if present, else plain 404
            self.send_error(404, "Fichier introuvable")
            return

        base = os.path.basename(full)
        is_admin = self._is_admin()

        # Le code d'édition n'est JAMAIS livré aux visiteurs (protection serveur).
        if base == "editor.js" and not is_admin:
            self.send_error(403, "Réservé à l'administrateur")
            return

        ext = os.path.splitext(full)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")

        # Videos: honour HTTP Range so <video> can stream and seek.
        if ext in (".mp4", ".webm", ".mov", ".m4v"):
            return self._serve_ranged(full, ctype)

        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404, "Fichier introuvable")
            return

        # Rich link previews: inject Open Graph tags when an article is shared.
        if base == "article.html":
            body = self._inject_article_og(body)

        # Injection du rôle + de l'éditeur, uniquement pour l'administrateur connecté.
        if ext == ".html":
            body = self._inject_role(body, is_admin, base)

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if ext == ".html":
            # Le HTML dépend du rôle (admin/visiteur) : ne jamais mettre en cache.
            self.send_header("Cache-Control", "no-store")
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ico"):
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            # JS / CSS / SVG : revalidation à chaque fois.
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _inject_role(self, body, is_admin, base):
        """Tell the page its role, and load the editor ONLY for a logged-in admin.
        Visitors never receive any admin/editor code."""
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body
        # Le drapeau de rôle doit être défini AVANT l'exécution des scripts du body
        # (components.js le lit) → on l'injecte dans le <head>.
        flag = "<script>window.__KBO_ADMIN__=%s;</script>" % ("true" if is_admin else "false")
        text = text.replace("</head>", flag + "</head>", 1)
        # L'éditeur en ligne (pages publiques, admin connecté) se charge en fin de body.
        if is_admin and base != "admin.html":
            text = text.replace("</body>", '<script src="js/editor.js"></script></body>', 1)
        return text.encode("utf-8")

    def _inject_article_og(self, body):
        """Insert Open Graph / Twitter meta for the requested article so shared
        links show a title, description and image on social networks."""
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        aid = (qs.get("id") or [""])[0]
        if not aid:
            return body
        article = None
        for a in _read_json(ARTICLES_FILE, []):
            if a.get("id") == aid:
                article = a
                break
        if not article:
            return body

        host = self.headers.get("Host", "localhost:%d" % PORT)
        scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        base = "%s://%s/" % (scheme, host)
        url = base + "article.html?id=" + aid
        img = article.get("image") or "images/post-default.svg"
        img_abs = img if img.startswith("http") else base + img.lstrip("/")
        settings = _get_settings()
        author = settings["texts"].get("name", "")

        def esc(s):
            return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace('"', "&quot;"))

        title = "%s — %s" % (esc(article.get("title", "")), esc(settings["texts"].get("brandMark", "KBO")))
        desc = esc(article.get("excerpt", ""))
        tags = (
            '<meta property="og:type" content="article">\n'
            '<meta property="og:title" content="%s">\n'
            '<meta property="og:description" content="%s">\n'
            '<meta property="og:image" content="%s">\n'
            '<meta property="og:url" content="%s">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            '<meta name="twitter:title" content="%s">\n'
            '<meta name="twitter:description" content="%s">\n'
            '<meta name="twitter:image" content="%s">\n'
            '<meta name="author" content="%s">\n'
        ) % (esc(article.get("title", "")), desc, img_abs, esc(url),
             esc(article.get("title", "")), desc, img_abs, author)

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body
        # Replace the placeholder <title> and add meta just before </head>.
        text = re.sub(r"<title>.*?</title>", "<title>%s</title>" % title, text, count=1, flags=re.DOTALL)
        text = text.replace("</head>", tags + "</head>", 1)
        return text.encode("utf-8")

    def _send_bytes(self, data, ctype, cache=False):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_bytes_ranged(self, data, ctype):
        """Sert des octets en mémoire (vidéo depuis la base) avec support Range."""
        size = len(data)
        rng = self.headers.get("Range", "")
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        partial = False
        if m and (m.group(1) or m.group(2)):
            partial = True
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            if m.group(1) == "":
                start = max(0, size - int(m.group(2)))
                end = size - 1
            start = min(start, size - 1)
            end = min(end, size - 1)
        chunk = data[start:end + 1]
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(chunk)))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        try:
            self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_ranged(self, full, ctype):
        try:
            size = os.path.getsize(full)
        except OSError:
            self.send_error(404, "Fichier introuvable")
            return
        rng = self.headers.get("Range", "")
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        partial = False
        if m and (m.group(1) or m.group(2)):
            partial = True
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            if m.group(1) == "":  # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
                end = size - 1
            start = min(start, size - 1)
            end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        try:
            with open(full, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionResetError):
            pass


def main():
    try:
        import sys
        sys.stdout.reconfigure(line_buffering=True)  # live logs even when piped
    except Exception:
        pass
    _ensure_data()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("―" * 60)
    print("  KBO Corporate Finance")
    print("  Stockage   : %s" % ("PostgreSQL (permanent)" if DB_ENABLED
          else "fichiers JSON locaux (dossier data/)"))
    print("  Site       : http://localhost:%d" % PORT)
    print("  Admin      : http://localhost:%d/admin.html  (tableau de bord complet)" % PORT)
    _pw_custom = os.path.exists(AUTH_FILE)
    print("  Mot de passe admin : %s" % ("(personnalisé dans le tableau de bord)" if _pw_custom
          else (os.environ.get("ADMIN_PASSWORD") or "kbo-admin")))
    _mail = _get_mail()
    print("  E-mail (formulaire): %s" % ("configuré → %s" % _mail["host"] if (_mail["host"] and _mail["user"] and _mail["pass"])
          else "non configuré (à régler dans le tableau de bord → Notifications e-mail)"))
    print("  Ctrl+C pour arrêter")
    print("―" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arrêt du serveur.")
        server.shutdown()


if __name__ == "__main__":
    main()
