# KBO Corporate Finance — Site d'Obed Kabeya

Site personnel et professionnel d'**Obed Kabeya**, banquier de marché et trader.
Design minimaliste et élégant (bleu foncé · noir · blanc), entièrement responsive
(téléphone · tablette · ordinateur).

## Démarrer

Aucune installation, aucune dépendance. Il suffit de **Python 3** (déjà présent sur macOS) :

```bash
cd kbo-corporate-finance
python3 server.py
```

Puis ouvrez **http://localhost:8000**

Options :

```bash
PORT=9000 python3 server.py            # changer le port
ADMIN_PASSWORD=monsecret python3 server.py   # changer le mot de passe admin
```

> Le site fonctionne aussi en ouvrant `public/index.html` directement, mais le
> blog et les formulaires nécessitent le serveur (ils dialoguent avec l'API).

## Structure

```
kbo-corporate-finance/
├── server.py            # serveur + API (bibliothèque standard Python)
├── data/
│   ├── articles.json    # articles / histoires / vidéos du blog
│   ├── settings.json    # réglages + textes éditables + images (bio) du site
│   ├── media.json       # index de la bibliothèque de médias
│   ├── gallery.json     # album photos / vidéos (galerie)
│   └── submissions.json # candidatures & messages de contact reçus
└── public/
    ├── index.html            # Accueil — hero + 2 chemins
    ├── personnel.html        # Biographie + Blog + aperçu galerie
    ├── galerie.html          # Galerie publique (lightbox)
    ├── article.html          # Lecture d'un article / d'une vidéo
    ├── admin.html            # Tableau de bord d'administration (onglets)
    ├── parametres.html       # → redirige vers admin.html
    ├── professionnel.html    # Vue d'ensemble des 3 services
    ├── formation.html        # Service 1 — formation (candidature exigeante)
    ├── comptabilite.html     # Service 2 — comptabilité (contact)
    ├── conseil.html          # Service 3 — conseil (contact)
    ├── contact.html          # Contact général
    ├── css/                  # style.css (design) + admin.css (tableau de bord)
    ├── js/                   # composants, blog, article, admin, formulaires
    ├── uploads/              # médias téléversés (images + vidéos)
    └── images/               # illustrations SVG + images/uploads (compat)
```

## Pages & fonctionnalités

- **Accueil** — hero avec photo + présentation, deux accès (Personnel / Professionnel).
- **Personnel** — biographie développée illustrée + blog dynamique.
- **Blog** — articles en liste (titre, date, extrait, image). Les vidéos YouTube/Vimeo
  sont intégrées automatiquement dans la page de l'article.
- **Espace admin** (`/admin.html`) — un **tableau de bord unique** protégé par mot de
  passe (`kbo-admin` par défaut), organisé en onglets :
  - **Identité & Accueil** : photo de profil (upload), logo (sigle + sous-titre),
    **le nom affiché dans le titre d'accueil**, le rôle/accroche et la présentation.
  - **Textes des pages** : titres et paragraphes de l'Accueil, du pied de page et
    de la page Contact — tout le texte visible est modifiable.
  - **Réseaux & Contact** : adresse e-mail de réception et liens LinkedIn / X /
    YouTube / Facebook / Instagram.
  - **Blog & Histoires** : créer/supprimer articles, histoires et vidéos, avec upload
    d'image d'aperçu et **vidéos verticales (mobile) téléversées** — plus besoin de YouTube.
  - **Galerie** : album photos & vidéos (verticales incluses) — téléverser, légender,
    publier/masquer. Les éléments publiés alimentent la **page Galerie publique**
    (`galerie.html`, avec agrandissement au clic / lightbox) et un aperçu sur Personnel.
  - Un bouton **« Voir en tant que visiteur »** ouvre le site tel que le voient vos
    visiteurs (aucun bouton d'édition), avec une barre pour revenir à l'admin.
  - **Médias** : bibliothèque pour téléverser et gérer images et vidéos, réutilisables
    partout (copier le lien, supprimer).
  - **Photos de la biographie** : gérées **uniquement** dans l'onglet Identité
    (3 emplacements). La page Personnel n'affiche aucun bouton d'édition.

  **Vue admin vs visiteur** : les visiteurs ne voient aucun bouton d'édition ni lien de
  réglages. L'icône ⚙ Paramètres et les boutons « Changer la photo » n'apparaissent
  qu'après connexion (le navigateur mémorise la session). Pour ouvrir l'admin, allez sur
  `/admin.html` (à mettre en favori).

  **Articles partageables** : chaque article a des boutons de partage (WhatsApp, X,
  Facebook, LinkedIn, e-mail, copier le lien) et le serveur ajoute des balises Open
  Graph, si bien qu'un lien partagé affiche un aperçu (titre, extrait, image).

  Un clic sur « Enregistrer » et les changements se propagent **automatiquement** sur
  toutes les pages (Accueil, Personnel, Professionnel, Contact), avec confirmation.
  Le lien vers l'admin est accessible partout via une **icône ⚙ discrète en pied de
  page** (et « ⚙ Espace admin » en bas du menu mobile). `/parametres.html` redirige
  vers ce tableau de bord.
- **Professionnel** — 3 services :
  1. **Formation en finance des marchés** — page détaillée, carrousel de modules,
     **dossier de candidature exigeant** (parcours, motivations, objectifs…).
  2. **Comptabilité des entreprises naissantes** — page + formulaire de contact.
  3. **Conseil en investissement** — page + formulaire de contact.
- **Contact** — coordonnées + formulaire général.

## Où arrivent les demandes ?

Toutes les candidatures et messages sont enregistrés dans `data/submissions.json`
et affichés en direct dans le terminal du serveur. Un administrateur connecté peut
aussi les consulter via `GET /api/submissions` (en-tête `X-Admin-Password`).

## Recevoir les messages par e-mail (envoi réel)

Par défaut, les messages sont enregistrés et affichés dans le terminal. Pour qu'ils
soient **envoyés automatiquement** à l'adresse configurée dans Paramètres, démarrez le
serveur avec vos identifiants SMTP. Exemple avec Gmail (créez un
« mot de passe d'application » dans votre compte Google) :

```bash
SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
SMTP_USER="Obedkabeya1996@gmail.com" \
SMTP_PASS="votre-mot-de-passe-application" \
python3 server.py
```

Une fois le SMTP configuré, chaque « Envoyer le message » depuis la page Contact (et
chaque candidature) part vers l'adresse définie dans **Paramètres → Adresse e-mail de
réception**. La page Paramètres indique si l'envoi d'e-mail est actif.

## Personnaliser

La plupart des réglages courants se font **sans toucher au code**, via
**Paramètres** (`/parametres.html`) : photo de profil, présentation de l'accueil,
adresse e-mail et réseaux sociaux. Pour le reste :

- **Couleurs / typographie** : variables CSS en haut de `public/css/style.css`.
- **Mot de passe admin** : variable d'environnement `ADMIN_PASSWORD`
  (protège l'espace publication **et** les Paramètres).
- **Textes des pages** (biographie, services) : directement dans les fichiers HTML.
