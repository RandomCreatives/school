# Deployment guide

Target: one small VPS (1 vCPU / 1 GB RAM is plenty for a school), Ubuntu 24.04,
Postgres, gunicorn behind nginx, nightly backups. No Docker required.

## 1. Server setup

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql nginx

sudo -u postgres psql <<'SQL'
CREATE USER school WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE school OWNER school;
SQL

sudo mkdir -p /srv/school && sudo chown "$USER" /srv/school
cd /srv/school
git clone <repo-url> .
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Environment (/srv/school/.env)

| Variable | Example | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | long random string | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `0` | never `1` in production |
| `DJANGO_ALLOWED_HOSTS` | `school.example.com` | comma-separated |
| `DATABASE_URL` | `postgres://school:pw@127.0.0.1:5432/school` | switch off SQLite |

```bash
set -a; . /srv/school/.env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic   # set STATIC_ROOT first if serving via nginx
.venv/bin/python manage.py createsuperuser  # the office admin account
```

`STATIC_ROOT = BASE_DIR / "staticfiles"` must be set via settings for
collectstatic — add it in `config/settings.py` when deploying (kept out of
dev defaults).

## 3. gunicorn (systemd, /etc/systemd/system/school.service)

```ini
[Unit]
Description=School management system
After=network.target

[Service]
User=www-data
WorkingDirectory=/srv/school
EnvironmentFile=/srv/school/.env
ExecStart=/srv/school/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now school
```

## 4. nginx (/etc/nginx/sites-available/school, symlinked to sites-enabled)

```nginx
server {
    listen 80;
    server_name school.example.com;

    location /static/ { alias /srv/school/staticfiles/; }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then enable HTTPS with certbot (`sudo apt install certbot python3-certbot-nginx &&
sudo certbot --nginx`) — a school holds minors' data; plain HTTP is not acceptable.

## 5. Nightly backups

`scripts/backup.sh` dumps Postgres, gzips, and keeps 30 days. Wire it into cron:

```cron
0 2 * * * BACKUP_DIR=/srv/school/backups DATABASE_URL=postgres://school:pw@127.0.0.1:5432/school /srv/school/scripts/backup.sh
```

Copy backups off the server weekly (any object storage / second machine) — a
backup on the same disk is not a backup. Test restore once before trusting it:

```bash
gunzip -c backups/school-<date>.sql.gz | psql postgres://school:pw@127.0.0.1:5432/school
```

## 6. First-run checklist (office)

1. Log into `/admin/` with the superuser.
2. Create the **academic year** (it auto-creates its 3 terms), fill in term
   dates, mark it *current*.
3. Add **subjects**; create **teacher** user accounts and link Teacher profiles.
4. Create **classes**, set homeroom teachers, run *Generate sections*.
5. `python manage.py import_students students.csv --dry-run`, then for real.
6. Enroll students in their classes (class page → enrollment inline).
7. Assign section teachers; hand teachers their logins.
