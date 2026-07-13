# ops-event-tools

Convention operations tools — currently the AV dashboard (live TV-guide schedule,
full schedule, rooms/equipment/checklists, staff shifts, links) rebuilt as a
multi-event Django app. Successor to `av-dashboard` (Flask).

## Stack

Django 5.2 LTS + HTMX + Bootstrap 5 (CDN, no build step). SQLite by default,
Postgres via env vars. Google Sheets sync per event via a service account.

## Features

- **Multi-event**: every convention is an `Event` with fully separated rooms,
  equipment, schedule, staff shifts, checklists, links, and layout images.
  Google Sheets connection is optional per event — sheet-less events are
  managed directly in the Django admin.
- **RBAC**: four roles as Django groups — Viewer (live/schedule/rooms/links),
  Staff (+ staff shifts, checklist check-off), Manager (+ manage area, admin
  data entry), Admin (+ users, event create/delete). Login required site-wide;
  the login form's "keep me signed in" checkbox gives a 90-day kiosk session
  for TV displays.
- **Proper datetimes**: sheet date/time strings are parsed once at sync into
  timezone-aware datetimes (per-event timezone). Midnight-crossing panels
  (11:45 PM – 12:45 AM) are handled at parse time.

## Install / upgrade (server)

One script handles system packages (poppler-utils), the venv, migrations,
static files, and the systemd units — idempotent, so it's also the upgrade path:

```bash
git clone https://github.com/jackson1719/ops-event-tools.git /opt/ops-event-tools
cd /opt/ops-event-tools
./deploy/install.sh
```

Then, on a fresh install:

1. Edit `.env` — set `ALLOWED_HOSTS` (a random `SECRET_KEY` was generated for you).
2. Drop the Google service-account key at `credentials.json` (or set
   `GOOGLE_CREDENTIALS_FILE` in `.env`). Only needed for sheet-connected events.
3. `./venv/bin/python manage.py createsuperuser`
4. Create an Event in `/admin/` (optionally with a spreadsheet ID), assign users
   to the Viewer/Staff/Manager/Admin groups, then:

```bash
./venv/bin/python manage.py sync_events <slug>     # or --all
```

## Development setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env                 # set DEBUG=true for the dev server
./venv/bin/python manage.py migrate
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py runserver
```

## Expected spreadsheet tabs / columns

| Tab (default name) | Columns |
|---|---|
| Rooms | building, floor, room_name, room_number |
| Equipment | building, room_name, room_number, vendor, type, qty, equipment |
| Events | date, start_time, end_time, building, room_name, room_number, av, name, desc |
| Staff Shifts | staff, date, start_time, end_time, notes |
| Room Checklist (optional) | building, room_name, room_number, item, checked, checked_by, checked_at |

Dates accept `4/3/2026` or `2026-04-03`; times accept `9:00 AM` or `14:00`.
Rows that fail to parse are skipped and reported on the event's Manage page.

## Services

Installed by `deploy/install.sh`:

- `ops-event-tools.service` — gunicorn on port 3001 (whitenoise serves static)
- `ops-sync.timer` / `ops-sync.service` — runs `manage.py sync_events --all`
  every 10 minutes (also clears expired sessions)

Useful commands:

```bash
sudo systemctl status ops-event-tools      # service health
sudo journalctl -u ops-event-tools -f      # follow app logs
sudo journalctl -u ops-sync -n 50          # recent sync runs
sudo systemctl restart ops-event-tools     # after a code update
```

Postgres later: `pip install psycopg`, set `DB_ENGINE=postgresql` +
`DB_NAME/DB_HOST/DB_USER/DB_PASSWORD` in `.env`, run `migrate`.

## Migrating data from the legacy av-dashboard

```bash
./venv/bin/python manage.py sync_events <slug>                    # data comes from the same sheet
./venv/bin/python manage.py import_room_images <slug> /opt/av-dashboard/static/uploads/room_images
./venv/bin/python manage.py import_links <slug> /opt/av-dashboard/data/links.json
```

## Tests

```bash
./venv/bin/python manage.py test
```

## Security notes / accepted trade-offs

These are deliberate design choices, not oversights:

- **Roles are global, not per-event.** A Manager manages *every* event in the
  install; an Admin administers all events and users. Correct for a single-org
  tool. Child objects are still event-scoped, so there's no cross-event data
  bleed — but role grants are install-wide. Revisit if this ever becomes
  multi-tenant.
- **`SECURE_COOKIES` defaults off** so plain-HTTP LAN testing works. **Set it
  `true` in `.env` for any HTTPS deployment** (Cloudflare tunnel or direct
  8443) or session cookies ship without the Secure flag. The app refuses to
  boot with the insecure default `SECRET_KEY` when `DEBUG` is off.
- **Account enumeration is enabled** (friendly "unknown email" errors) — an
  internal-tool trade-off. The custom login is non-enumerating and now
  rate-limited (10 failures / 15 min per IP+username, keyed on
  `CF-Connecting-IP`).
- **Google email-auth auto-connects** a matching account: whoever controls the
  Google mailbox for a user's email can sign in as them. Only set a user's
  email to an address they control, especially for Manager/Admin.
- **The iCal feed authenticates by a URL token** (calendar apps can't do
  session login); the token appears in access logs. It's high-entropy but
  long-lived — treat a personal calendar URL as a shared secret.
- **Secrets live in the SQLite DB** (SMTP/Google/Cloudflare) by design. The DB
  file is `chmod 600` and the systemd units set `UMask=0077`; back up the
  `backups/` folder somewhere off-box since it contains those secrets.
- **Content-Security-Policy is enforced** via `ContentSecurityPolicyMiddleware`:
  a per-request nonce with `script-src 'strict-dynamic'` and no
  `'unsafe-inline'` for scripts, so an injected `<script>` or `on*=` handler
  won't run even if output-escaping is ever bypassed. Inline event handlers
  were replaced with `static/js/behaviors.js` (data-attribute driven) plus
  nonced `<script>` blocks. `style-src` keeps `'unsafe-inline'` (inline
  `style=` is pervasive and low-risk). The Django admin is exempted. If you add
  a new inline `<script>`, give it `nonce="{{ csp_nonce }}"`; avoid inline
  `on*=` handlers (use `behaviors.js` data-attributes or `addEventListener`).

## Direct HTTPS (ACME / Let's Encrypt)

The app can serve HTTPS itself on **port 8443**, with certificates obtained and
auto-renewed in-app. Configure in **Site Settings → HTTPS / SSL**:

1. Set the domain (for LAN use, a DNS-only/grey-cloud A record pointing at the
   box) and add it to `ALLOWED_HOSTS` in `.env`.
2. Pick a validation method:
   - **DNS-01 via Cloudflare** (recommended): paste an API token with
     *Zone Read + DNS Edit* — no open ports required.
   - **HTTP-01**: the internet must reach port 80 on this machine
     (router-forward 80 → 3001).
3. Leave **Staging mode** on for the first attempt (untrusted test cert, no
   rate limits), click **Issue Certificate Now**, then turn staging off and
   issue again for the real certificate.

The `ops-event-tools-ssl` systemd unit idles until a certificate exists, then
serves `https://<domain>:8443`; renewals happen automatically ~30 days before
expiry and reload the listener without downtime.
