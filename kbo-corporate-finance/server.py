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

PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "kbo-admin")

# SMTP (facultatif) — si configuré, les messages du formulaire sont envoyés par e-mail.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

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
def _ensure_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
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
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, data):
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


def _drain(rfile, length):
    """Discard `length` bytes from the request body (keeps the socket clean)."""
    remaining = length
    while remaining > 0:
        chunk = rfile.read(min(65536, remaining))
        if not chunk:
            break
        remaining -= len(chunk)


def _send_email(to_addr, subject, body, reply_to=None):
    """Send an e-mail via SMTP if configured. Returns (sent: bool, detail: str)."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return False, "SMTP non configuré"
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM or SMTP_USER
        msg["To"] = to_addr
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=context)
            s.login(SMTP_USER, SMTP_PASS)
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
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(raw)
    return "images/uploads/%s" % name, None


# ----------------------------- request handler -----------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "KBO/1.0"

    # ---- utilities ----
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def _is_admin(self):
        return self.headers.get("X-Admin-Password", "") == ADMIN_PASSWORD

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

        if path == "/api/submissions":  # admin-only inbox
            if not self._is_admin():
                return self._send_json({"error": "Non autorisé"}, 401)
            subs = _read_json(SUBMISSIONS_FILE, [])
            return self._send_json(sorted(subs, key=lambda s: s.get("received", ""), reverse=True))

        return self._send_json({"error": "Not found"}, 404)

    # ---- API: POST ----
    def _api_post(self, path):
        if path == "/api/articles":
            return self._create_article()

        if path == "/api/settings":
            return self._save_settings()

        if path == "/api/settings/image":
            return self._save_one_image()

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
        if key not in DEFAULT_SETTINGS["images"] or not path:
            return self._send_json({"error": "Requête invalide"}, 400)
        settings = _get_settings()
        settings["images"][key] = path
        settings.pop("_emailConfigured", None)
        _write_json(SETTINGS_FILE, settings)
        return self._send_json({"ok": True, "images": settings["images"]})

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
        dest = os.path.join(MEDIA_DIR, name)
        written = 0
        try:
            with open(dest, "wb") as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
        except OSError:
            return self._send_json({"error": "Écriture impossible."}, 500)

        rel = "uploads/%s" % name
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
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            # SPA-ish fallback: serve 404 page if present, else plain 404
            self.send_error(404, "Fichier introuvable")
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
        if os.path.basename(full) == "article.html":
            body = self._inject_article_og(body)

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ico"):
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            # HTML / JS / CSS / SVG must always revalidate so edits appear at once.
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

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
    print("  Site       : http://localhost:%d" % PORT)
    print("  Admin      : http://localhost:%d/admin.html  (tableau de bord complet)" % PORT)
    print("  Mot de passe admin : %s" % ("(défini via ADMIN_PASSWORD)" if os.environ.get("ADMIN_PASSWORD") else "kbo-admin"))
    print("  E-mail (formulaire): %s" % ("configuré → %s" % SMTP_HOST if (SMTP_HOST and SMTP_USER and SMTP_PASS) else "non configuré (messages enregistrés + affichés ici)"))
    print("  Ctrl+C pour arrêter")
    print("―" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arrêt du serveur.")
        server.shutdown()


if __name__ == "__main__":
    main()
