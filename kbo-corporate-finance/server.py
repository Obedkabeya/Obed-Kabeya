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
import socket
import ssl
import uuid
import urllib.request
import urllib.error
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
COMMENTS_FILE = os.path.join(DATA_DIR, "comments.json")      # commentaires des articles
NEWSLETTER_FILE = os.path.join(DATA_DIR, "newsletter.json")  # adresses e-mail (offres/actualités)
STATS_FILE = os.path.join(DATA_DIR, "stats.json")            # fréquentation (anonyme, sans cookie)
# Réglages e-mail saisis depuis le tableau de bord (adresse + mot de passe
# d'application). Ce fichier est dans .gitignore et n'est JAMAIS livré dans le
# zip : le mot de passe ne peut donc pas se retrouver sur GitHub.
MAIL_FILE = os.path.join(DATA_DIR, "mail.json")
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

# NOTE : la configuration e-mail (BREVO_API_KEY, SENDGRID_API_KEY, MAIL_FROM,
# SMTP_*) est lue directement dans l'environnement À CHAQUE ENVOI, via _mail_env()
# (voir plus bas). Rien n'est figé au démarrage, rien n'est stocké dans un fichier.
# Priorité : Brevo (API HTTP) → SendGrid (API HTTP) → SMTP (secours).

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
    # Accueil (nouvelle structure — cabinet KBO)
    "homeHeroLead": (
        "Former aux marchés, aider les entreprises à devenir bancables, conseiller les "
        "investisseurs. Trois métiers, une même exigence : comprendre avant d'agir, "
        "structurer avant de risquer."
    ),
    "homePillarsTitle": "Ce que fait le cabinet",
    "homeProcessTitle": "Une même exigence, à chaque étape",
    "homeProcessLead": (
        "Comprendre avant d'agir, structurer avant de risquer, transmettre ce qui a "
        "fait ses preuves. Trois principes qui guident chaque formation, chaque dossier "
        "et chaque conseil."
    ),
    "homeShowcaseTitle": "La finance, expliquée simplement",
    "homeShowcaseText": (
        "Des marchés régionaux à la bancarisation d'une petite entreprise, nous rendons "
        "des sujets réputés complexes clairs et actionnables. Placez ici votre vidéo de "
        "présentation ou une image forte."
    ),
    "homeCtaTitle": "Par où souhaitez-vous commencer ?",
    "homeCtaText": (
        "Une formation, un diagnostic de bancabilité, un conseil en investissement — "
        "dites-nous où vous en êtes, on avance ensemble."
    ),
    "homeFounderTitle": "Un praticien, pas un vendeur",
    "homeFounderText": (
        "Obed Kabeya a fondé KBO Corporate Finance après une formation en banque et "
        "finance d'entreprise et une certification en finance des marchés. La conviction "
        "qui l'anime : la finance n'est pas réservée à une élite — elle se transmet, "
        "s'explique et se met au service de ceux qui construisent."
    ),
    # Anciennes clés d'accueil — conservées pour compatibilité (n'apparaissent plus).
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
    "whatsapp": "",   # numéro international sans « + » (ex. 22990112233) — widget WhatsApp
    "theme": {},      # surcharges de couleurs (design) : primaire, accent, texte, fond, fonce
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
               CONTENT_FILE, IMGCONTENT_FILE, SLIDES_FILE, AUTH_FILE, SESSIONS_FILE,
               COMMENTS_FILE, NEWSLETTER_FILE, STATS_FILE, MAIL_FILE]
_LIST_KEYS = {"articles", "submissions", "media", "gallery", "newsletter"}


def _record_view(rel_path, referer=""):
    """Compte une visite de page — de façon ANONYME : aucune adresse IP, aucun
    cookie, aucune donnée personnelle. On ne garde qu'un total par jour et par
    page (et d'où vient le visiteur), ce qui suffit à piloter le site."""
    try:
        stats = _read_json(STATS_FILE, {})
        if not isinstance(stats, dict):
            stats = {}
        day = datetime.utcnow().strftime("%Y-%m-%d")
        days = stats.setdefault("days", {})
        entry = days.setdefault(day, {"views": 0, "pages": {}, "sources": {}})
        entry["views"] = entry.get("views", 0) + 1
        entry.setdefault("pages", {})
        entry["pages"][rel_path] = entry["pages"].get(rel_path, 0) + 1
        # Provenance : on ne retient que le nom de domaine (ex. google.com)
        src = "direct"
        if referer:
            try:
                host = urlparse(referer).netloc.lower()
                if host and host not in ("", "localhost") and not host.startswith("127."):
                    src = host
            except Exception:
                src = "direct"
        entry.setdefault("sources", {})
        entry["sources"][src] = entry["sources"].get(src, 0) + 1
        stats["total"] = stats.get("total", 0) + 1
        # On ne conserve que les 90 derniers jours
        if len(days) > 90:
            for old in sorted(days.keys())[:-90]:
                days.pop(old, None)
        _write_json(STATS_FILE, stats)
    except Exception:
        pass    # la fréquentation ne doit jamais casser l'affichage du site


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

    theme = data.get("theme") if isinstance(data.get("theme"), dict) else {}
    merged = {
        "email": data.get("email") or DEFAULT_SETTINGS["email"],
        "whatsapp": (data.get("whatsapp") or DEFAULT_SETTINGS.get("whatsapp", "")),
        "theme": theme,
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


# ============================================================
#  E-MAIL — priorité aux API HTTP (port 443, jamais bloqué par Railway) :
#  1) Brevo   2) SendGrid   3) SMTP (secours, surtout en local)
# ============================================================
def _mail_env():
    """Lit les variables d'e-mail depuis l'environnement À CHAQUE APPEL
    (et pas seulement au démarrage) — indispensable pour Railway."""
    # Ce que l'administrateur a saisi dans le tableau de bord est PRIORITAIRE
    # sur les variables d'environnement : c'est son choix explicite.
    cfg = _read_json(MAIL_FILE, {})
    if not isinstance(cfg, dict):
        cfg = {}

    def pick(cfg_key, env_key, default=""):
        v = str(cfg.get(cfg_key, "") or "").strip()
        return v or os.environ.get(env_key, default).strip()

    try:
        smtp_port = int(str(cfg.get("port") or os.environ.get("SMTP_PORT", "465")))
    except ValueError:
        smtp_port = 465
    smtp_user = pick("user", "SMTP_USER")
    smtp_pass = str(cfg.get("pass", "") or "") or os.environ.get("SMTP_PASS", "")
    return {
        "brevo": os.environ.get("BREVO_API_KEY", "").strip(),
        "sendgrid": os.environ.get("SENDGRID_API_KEY", "").strip(),
        "smtp_host": pick("host", "SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com",
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_pass": smtp_pass,
        "from": (str(cfg.get("from", "") or "").strip()
                 or os.environ.get("MAIL_FROM", "").strip()
                 or os.environ.get("SMTP_FROM", "").strip()
                 or smtp_user),
        "from_name": (str(cfg.get("from_name", "") or "").strip()
                      or os.environ.get("MAIL_FROM_NAME", "").strip()
                      or "KBO Corporate Finance"),
    }


def _get_mail():
    """État de l'e-mail (fournisseur + expéditeur). Ne renvoie AUCUN secret."""
    e = _mail_env()
    if e["brevo"]:
        provider = "brevo"
    elif e["sendgrid"]:
        provider = "sendgrid"
    elif e["smtp_host"] and e["smtp_user"] and e["smtp_pass"]:
        provider = "smtp"
    else:
        provider = None
    return {
        "provider": provider,
        "active": provider is not None,
        "from": e["from"],
        "host": e["smtp_host"],
        "port": e["smtp_port"],
        "user": e["smtp_user"],
        "pass": e["smtp_pass"],
        # Diagnostic (booléens uniquement, aucun secret) : quelles variables sont vues ?
        "detected": {
            "BREVO_API_KEY": bool(e["brevo"]),
            "SENDGRID_API_KEY": bool(e["sendgrid"]),
            "MAIL_FROM": bool(e["from"]),
            "SMTP_USER": bool(e["smtp_user"]),
            "SMTP_PASS": bool(e["smtp_pass"]),
        },
    }


def _http_post_json(url, headers, payload, timeout=25):
    """POST JSON via urllib (HTTPS/443). Renvoie (ok: bool, détail: str)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
        return (200 <= code < 300), "HTTP %d" % code
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        return False, "HTTP %d : %s" % (e.code, detail)
    except Exception as exc:  # noqa: BLE001
        return False, "%s" % exc


def _send_via_brevo(api_key, from_email, from_name, to_addr, subject, body, reply_to=None):
    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_addr}],
        "subject": subject,
        "textContent": body,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    ok, detail = _http_post_json("https://api.brevo.com/v3/smtp/email",
                                 {"api-key": api_key, "accept": "application/json"}, payload)
    return ok, ("envoyé (Brevo)" if ok else "erreur Brevo : " + detail)


def _send_via_sendgrid(api_key, from_email, from_name, to_addr, subject, body, reply_to=None):
    payload = {
        "personalizations": [{"to": [{"email": to_addr}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    ok, detail = _http_post_json("https://api.sendgrid.com/v3/mail/send",
                                 {"Authorization": "Bearer " + api_key}, payload)
    return ok, ("envoyé (SendGrid)" if ok else "erreur SendGrid : " + detail)


def _resolve_ipv4(host):
    """Adresse IPv4 du serveur (ou None). Force l'IPv4 pour le SMTP de secours."""
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return None


class _SMTP_SSL_IPv4(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        ip = _resolve_ipv4(host) or host
        raw = socket.create_connection((ip, port), timeout, getattr(self, "source_address", None))
        return self.context.wrap_socket(raw, server_hostname=self._host)


class _SMTP_IPv4(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        ip = _resolve_ipv4(host) or host
        return socket.create_connection((ip, port), timeout, getattr(self, "source_address", None))


def _send_via_smtp(e, from_email, to_addr, subject, body, reply_to=None):
    host = e["smtp_host"] or "smtp.gmail.com"
    try:
        port = int(e["smtp_port"] or 465)
    except (TypeError, ValueError):
        port = 465
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_email or e["smtp_user"]
        msg["To"] = to_addr
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        context = ssl.create_default_context()
        if port == 465:
            server = _SMTP_SSL_IPv4(host=host, port=port, context=context, timeout=30)
        else:
            server = _SMTP_IPv4(host=host, port=port, timeout=30)
            server.ehlo(); server.starttls(context=context); server.ehlo()
        try:
            server.login(e["smtp_user"], e["smtp_pass"])
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return True, "envoyé (SMTP port %d)" % port
    except Exception as exc:  # noqa: BLE001
        return False, "erreur SMTP (port %d) : %s" % (port, exc)


def _send_email(to_addr, subject, body, reply_to=None):
    """Envoie un e-mail. Renvoie (envoyé: bool, détail: str).
    Priorité : votre boîte e-mail directe (SMTP, ex. Gmail) → Brevo → SendGrid.
    Le choix explicite de l'administrateur passe donc AVANT tout le reste.
    Quoi qu'il arrive, le message est déjà enregistré dans le tableau de bord."""
    e = _mail_env()
    from_email = e["from"] or _get_settings().get("email", "")
    from_name = e["from_name"]
    if e["smtp_host"] and e["smtp_user"] and e["smtp_pass"]:
        ok, detail = _send_via_smtp(e, from_email, to_addr, subject, body, reply_to)
        if ok:
            return True, detail
        # Si la boîte directe échoue (hébergeur qui bloque le SMTP), on tente
        # un service de secours éventuellement configuré, plutôt que d'échouer.
        if e["brevo"]:
            return _send_via_brevo(e["brevo"], from_email, from_name, to_addr, subject, body, reply_to)
        if e["sendgrid"]:
            return _send_via_sendgrid(e["sendgrid"], from_email, from_name, to_addr, subject, body, reply_to)
        return False, detail
    if e["brevo"]:
        return _send_via_brevo(e["brevo"], from_email, from_name, to_addr, subject, body, reply_to)
    if e["sendgrid"]:
        return _send_via_sendgrid(e["sendgrid"], from_email, from_name, to_addr, subject, body, reply_to)
    return False, ("Aucune adresse e-mail configurée. Renseignez votre adresse et "
                   "votre mot de passe d'application dans « Compte & e-mail ».")


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
            settings["_emailConfigured"] = _get_mail()["active"]
            # Permanence du stockage : sans base de données, tout ce que
            # l'administrateur modifie sera perdu au prochain déploiement.
            settings["_storagePermanent"] = bool(DB_ENABLED)
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

        if path == "/api/mailconfig":  # admin only, never exposes any secret
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            cfg = _get_mail()
            # On renvoie l'adresse et le serveur (utiles à l'affichage) mais
            # JAMAIS le mot de passe : seulement l'information « il est défini ».
            return self._send_json({"provider": cfg["provider"], "active": cfg["active"],
                                    "from": cfg["from"], "detected": cfg["detected"],
                                    "smtpUser": cfg["user"], "smtpHost": cfg["host"],
                                    "smtpPort": cfg["port"], "hasPassword": bool(cfg["pass"])})

        if path == "/api/submissions":  # admin-only inbox
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            subs = _read_json(SUBMISSIONS_FILE, [])
            return self._send_json(sorted(subs, key=lambda s: s.get("received", ""), reverse=True))

        # Commentaires d'un article (publics, en lecture)
        m = re.match(r"^/api/comments/([A-Za-z0-9_\-]+)$", path)
        if m:
            allc = _read_json(COMMENTS_FILE, {})
            items = allc.get(m.group(1), []) if isinstance(allc, dict) else []
            return self._send_json(sorted(items, key=lambda c: c.get("date", "")))

        if path == "/api/newsletter":   # admin-only : liste des inscrits
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            subs = _read_json(NEWSLETTER_FILE, [])
            return self._send_json(sorted(subs, key=lambda s: s.get("date", ""), reverse=True))

        if path == "/api/stats":        # admin-only : fréquentation du site
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            stats = _read_json(STATS_FILE, {})
            days = stats.get("days", {}) if isinstance(stats, dict) else {}
            last = sorted(days.keys())[-30:]
            pages, sources, per_day = {}, {}, []
            for d in last:
                e = days.get(d, {})
                per_day.append({"date": d, "views": e.get("views", 0)})
                for k, v in (e.get("pages") or {}).items():
                    pages[k] = pages.get(k, 0) + v
                for k, v in (e.get("sources") or {}).items():
                    sources[k] = sources.get(k, 0) + v
            top = lambda d: sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:10]
            return self._send_json({
                "total": stats.get("total", 0) if isinstance(stats, dict) else 0,
                "days": per_day,
                "last30": sum(x["views"] for x in per_day),
                "topPages": [{"page": k, "views": v} for k, v in top(pages)],
                "topSources": [{"source": k, "views": v} for k, v in top(sources)],
            })

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

        if path == "/api/mailconfig":
            return self._save_mail_config()

        if path == "/api/newsletter":
            return self._newsletter_signup()

        if path == "/api/comments-delete":       # admin uniquement
            return self._delete_comment()

        m = re.match(r"^/api/comments/([A-Za-z0-9_\-]+)$", path)
        if m:
            return self._add_comment(m.group(1))

        m = re.match(r"^/api/(apply|contact)/([a-z0-9\-]+)$", path)
        if m:
            return self._save_submission(category=m.group(1), slug=m.group(2))

        self._send_json({"error": "Not found"}, 404)

    # ---- Réglages e-mail (adresse + mot de passe d'application) ----
    def _save_mail_config(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        if not isinstance(data, dict):
            return self._send_json({"error": "Requête invalide"}, 400)

        current = _read_json(MAIL_FILE, {})
        if not isinstance(current, dict):
            current = {}

        if data.get("clear"):                       # bouton « Déconnecter »
            _write_json(MAIL_FILE, {})
            return self._send_json({"ok": True, "cleared": True})

        user = _clean(data.get("user"), 200)
        if user and not EMAIL_RE.match(user):
            return self._send_json({"error": "Adresse e-mail invalide."}, 400)
        # Le mot de passe d'application Gmail fait 16 lettres, souvent collé
        # avec des espaces : on les retire pour éviter une erreur d'authentification.
        pwd = re.sub(r"\s+", "", str(data.get("pass") or ""))
        try:
            port = int(str(data.get("port") or 465))
        except ValueError:
            port = 465
        if port not in (25, 465, 587, 2525):
            port = 465

        cfg = {
            "host": _clean(data.get("host"), 120) or "smtp.gmail.com",
            "port": port,
            "user": user or current.get("user", ""),
            # Champ laissé vide = on conserve le mot de passe déjà enregistré.
            "pass": pwd or current.get("pass", ""),
            "from": _clean(data.get("from"), 200) or user or current.get("from", ""),
            "from_name": _clean(data.get("from_name"), 120) or current.get("from_name", ""),
        }
        _write_json(MAIL_FILE, cfg)
        return self._send_json({"ok": True, "hasPassword": bool(cfg["pass"])})

    # ---- Commentaires d'articles ----
    def _add_comment(self, article_id):
        data = self._read_body()
        if not isinstance(data, dict):
            return self._send_json({"error": "Requête invalide"}, 400)
        # Le nom est FACULTATIF : on respecte l'anonymat de ceux qui le souhaitent.
        nom = _clean(data.get("nom"), 80) or "Anonyme"
        message = _clean(data.get("message"), 2000)
        if not message:
            return self._send_json({"error": "Votre commentaire est vide."}, 400)
        if len(message) < 2:
            return self._send_json({"error": "Message trop court."}, 400)
        # On ne garde que du texte : aucun HTML n'est stocké ni réaffiché.
        entry = {
            "id": uuid.uuid4().hex[:10],
            "nom": nom,
            "message": message,
            "date": datetime.utcnow().isoformat() + "Z",
        }
        allc = _read_json(COMMENTS_FILE, {})
        if not isinstance(allc, dict):
            allc = {}
        items = allc.get(article_id) or []
        if len(items) >= 500:
            return self._send_json({"error": "Trop de commentaires sur cet article."}, 429)
        items.append(entry)
        allc[article_id] = items
        _write_json(COMMENTS_FILE, allc)
        print("\n  💬 Nouveau commentaire sur « %s » de %s" % (article_id, nom), flush=True)
        return self._send_json({"ok": True, "comment": entry}, 201)

    def _delete_comment(self):
        if not self._is_admin():
            return self._send_json({"error": "Non autorisé"}, 401)
        data = self._read_body()
        article_id = _clean((data or {}).get("article"), 80)
        cid = _clean((data or {}).get("id"), 40)
        allc = _read_json(COMMENTS_FILE, {})
        if not isinstance(allc, dict) or article_id not in allc:
            return self._send_json({"error": "Introuvable"}, 404)
        allc[article_id] = [c for c in allc[article_id] if c.get("id") != cid]
        _write_json(COMMENTS_FILE, allc)
        return self._send_json({"ok": True})

    # ---- Newsletter (adresses e-mail pour les offres/actualités) ----
    def _newsletter_signup(self):
        data = self._read_body()
        email = _clean((data or {}).get("email"), 200)
        if not email or not EMAIL_RE.match(email):
            return self._send_json({"error": "Adresse e-mail invalide."}, 400)
        subs = _read_json(NEWSLETTER_FILE, [])
        if not isinstance(subs, list):
            subs = []
        if any((s.get("email") or "").lower() == email.lower() for s in subs):
            return self._send_json({"ok": True, "already": True})   # déjà inscrit : on ne dit rien de plus
        subs.append({"email": email, "date": datetime.utcnow().isoformat() + "Z"})
        _write_json(NEWSLETTER_FILE, subs)
        print("\n  ✉  Nouvelle inscription newsletter : %s" % email, flush=True)
        return self._send_json({"ok": True}, 201)

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

        wa = re.sub(r"[^\d]", "", (data.get("whatsapp") or current.get("whatsapp") or ""))[:20]
        # Thème (design) : on ne garde que des couleurs hexadécimales valides.
        theme_in = data.get("theme") if isinstance(data.get("theme"), dict) else current.get("theme", {})
        theme = {}
        for k in ("primaire", "accent", "texte", "fond", "fonce"):
            v = str((theme_in or {}).get(k, "")).strip()
            if re.match(r"^#[0-9a-fA-F]{6}$", v):
                theme[k] = v.lower()
        settings = {
            "email": email,
            "whatsapp": wa,
            "theme": theme,
            "presentation": texts["presentation"],
            "photo": _clean(data.get("photo"), 400) or current["photo"],
            "social": social,
            "texts": texts,
            "images": images,
        }
        _write_json(SETTINGS_FILE, settings)
        settings["_emailConfigured"] = _get_mail()["active"]
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

        status = 200
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            # Page 404 personnalisée si présente, sinon 404 brut.
            nf = os.path.join(PUBLIC_DIR, "404.html")
            if os.path.isfile(nf):
                full = nf
                status = 404
            else:
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

        # Rich link previews: inject Open Graph tags when an article is shared,
        # sinon des balises OG par défaut dérivées du <title> et de la description.
        if base == "article.html":
            body = self._inject_article_og(body)
        elif ext == ".html":
            body = self._inject_default_og(body)

        # Injection du rôle + de l'éditeur, uniquement pour l'administrateur connecté.
        if ext == ".html":
            body = self._inject_role(body, is_admin, base)
            # Fréquentation : on ne compte que les visiteurs (pas vos propres
            # visites en tant qu'administrateur), et jamais les pages privées.
            if status == 200 and not is_admin and base not in ("admin.html", "parametres.html"):
                _record_view("/" + rel, self.headers.get("Referer", "") or "")

        self.send_response(status)
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

    def _inject_default_og(self, body):
        """Balises Open Graph / Twitter par défaut, dérivées du <title> et de la
        meta description de la page (pour un partage propre sur les réseaux)."""
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body
        if "og:title" in text:
            return body
        def grab(pat):
            m = re.search(pat, text, re.I | re.S)
            return m.group(1).strip() if m else ""
        title = grab(r"<title>(.*?)</title>")
        if not title:
            return body
        desc = grab(r'<meta\s+name="description"\s+content="(.*?)"')
        def esc(s):
            return (s.replace("&", "&amp;").replace('"', "&quot;")
                     .replace("<", "&lt;").replace(">", "&gt;"))
        tags = (
            '<meta property="og:type" content="website">'
            '<meta property="og:site_name" content="KBO Corporate Finance">'
            '<meta property="og:title" content="%s">'
            '<meta property="og:description" content="%s">'
            '<meta name="twitter:card" content="summary">'
            '<meta name="twitter:title" content="%s">'
            '<meta name="twitter:description" content="%s">'
        ) % (esc(title), esc(desc), esc(title), esc(desc))
        text = text.replace("</head>", tags + "</head>", 1)
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
    print("  E-mail (formulaire): %s" % ("actif via %s" % _mail["provider"] if _mail["active"]
          else "non configuré (ajoutez BREVO_API_KEY, ou SENDGRID_API_KEY, ou les variables SMTP)"))
    print("  Ctrl+C pour arrêter")
    print("―" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arrêt du serveur.")
        server.shutdown()


if __name__ == "__main__":
    main()
