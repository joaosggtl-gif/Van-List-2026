# Van List 2026

Web-based fleet assignment system for assigning drivers to vans with multi-user authentication, role-based access control, daily persistence, audit logging, and XLSX export.

## Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12 / FastAPI |
| Database | SQLite (WAL mode) with ACID constraints |
| ORM + Migrations | SQLAlchemy + Alembic |
| Authentication | JWT (httpOnly cookies + Bearer tokens) |
| Password Hashing | bcrypt via passlib |
| Frontend | Jinja2 + Bootstrap 5 + Vanilla JS |
| Import/Export | pandas + openpyxl |
| Tests | pytest (55 tests) |
| Deployment | Docker + docker-compose |

## Quick Start (Local)

```bash
cd "Van List 2026"
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** and login with:
- **Username:** `admin`
- **Password:** `admin123`

> Change the default password immediately after first login.

## Quick Start (Docker)

```bash
cd "Van List 2026"
docker compose up -d
```

## Authentication & Access Control

### Roles

| Role | Assignments | Upload | Manage Users | Toggle Vans/Drivers | Audit Log | Export |
|---|---|---|---|---|---|---|
| **Admin** | Create/Edit/Delete | Yes | Yes | Yes | Yes | Yes |
| **Operator** | Create/Edit/Delete | No | No | No | No | Yes |
| **Read-only** | View only | No | No | No | No | Yes |

### How Authentication Works

1. Users login via `/login` page
2. Server issues JWT token stored in httpOnly cookie (browser) or returned as Bearer token (API)
3. All pages and API endpoints require valid authentication
4. Token expires after 8 hours (configurable via `JWT_EXPIRE_MINUTES`)
5. Permissions enforced at both API and UI levels

### Managing Users

1. Login as admin
2. Go to **Users** page
3. Create new users with assigned roles
4. Edit roles, reset passwords, activate/deactivate users

### API Authentication

For programmatic access, use Bearer token:

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# Use token
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/assignments?date_from=2026-01-05
```

## Audit Trail

Every data-modifying action is logged with:
- **User** who performed the action
- **Action type** (create, update, delete, login, upload, export)
- **Entity** affected (assignment, van, driver, user)
- **Details** of what changed
- **Timestamp**

View the audit log at `/audit` (admin only).

## How to Import Lists

### Vans

1. Login as admin
2. Go to **Upload** page
3. Upload CSV/XLSX with columns: `code` (required), `description` (optional)

```csv
code,description
VAN-001,Ford Transit White
VAN-002,Mercedes Sprinter Blue
```

### Drivers

Upload CSV/XLSX with columns: `employee_id` (required), `name` (required)

```csv
employee_id,name
EMP-001,John Smith
EMP-002,Maria Garcia
```

Re-uploading updates existing records (by `code` or `employee_id`), never duplicates.

## Daily Operations

### Weekly View (Home Page)

- Shows 7-day weekly overview with all assignments
- Navigate between weeks with Prev/Next buttons
- Click any day to drill down to daily view

### Daily Assignment Page

1. Navigate to a day
2. Use autocomplete to select a **driver** (only shows unassigned drivers for that date)
3. Use autocomplete to select a **van** (only shows available vans for that date)
4. Click **Assign**
5. To remove: click the trash icon (operator/admin only)

### Blocking Rules

- One van per driver per day (DB constraint `uq_date_van`)
- One driver per van per day (DB constraint `uq_date_driver`)
- Autocomplete filters already-assigned items
- API returns 409 with clear error message on conflict

## Week Numbering

- **Week 1:** 2025-12-28 (Sun) to 2026-01-03 (Sat)
- **Formula:** `Week N = floor((date - 2025-12-28) / 7) + 1`
- Weeks always start on Sunday, 7 days each

## XLSX Export

- **Daily:** Click "Export Day XLSX" or `GET /api/export/daily?target_date=2026-01-05`
- **Weekly:** Click "Export Week XLSX" or `GET /api/export/weekly?week=2`

### Columns

| Column | Description |
|---|---|
| Date | Assignment date |
| Week # | Week number |
| Driver ID | Employee ID |
| Driver Name | Full name |
| Van Code | Van identifier |
| Van Description | Van description |
| Status | "Assigned" |
| Created At | When assignment was created |
| Updated At | Last modification time |
| Notes | Optional notes |

## Backup & Restore

### Manual Backup

```bash
chmod +x backup.sh
./backup.sh
```

### Automated Backup (cron)

```bash
crontab -e
0 23 * * * cd "/path/to/Van List 2026" && ./backup.sh >> backups/cron.log 2>&1
```

### Restore

```bash
# Stop the server
cp backups/vanlist_backup_YYYYMMDD_HHMMSS.db data/vanlist.db
# Restart the server
```

## Configuration

Set environment variables or create `.env` file (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-...` | JWT signing key (use `openssl rand -hex 32`) |
| `DATABASE_URL` | `sqlite:///data/vanlist.db` | Database connection string |
| `JWT_EXPIRE_MINUTES` | `480` | Token expiry (8 hours) |
| `DEFAULT_ADMIN_USERNAME` | `admin` | Initial admin username |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | Initial admin password |

## Cloud Deployment

### Docker Compose (recommended)

```bash
# Generate a secret key
export SECRET_KEY=$(openssl rand -hex 32)
export DEFAULT_ADMIN_PASSWORD=your-secure-password

docker compose up -d
```

Data persists in Docker volumes `vanlist-data` and `vanlist-backups`.

### Cloud Platforms

The Docker image works with:
- **AWS:** ECS, App Runner, EC2
- **GCP:** Cloud Run, GCE
- **Azure:** Container Apps, ACI
- **Any VPS:** Docker installed

For production, consider:
1. Set a strong `SECRET_KEY`
2. Change default admin password
3. Use HTTPS (reverse proxy with nginx/Caddy)
4. Set up automated backups
5. Monitor disk space for SQLite database

## Tests

```bash
pytest tests/ -v
```

**55 tests** covering:
- Week calculation (14 tests)
- Assignment blocking + CRUD (8 tests)
- Authentication (7 tests)
- RBAC permissions (11 tests)
- Audit logging (2 tests)
- Upload + validation (8 tests)
- XLSX export (5 tests)

## API Endpoints

### Auth

| Method | URL | Role | Description |
|---|---|---|---|
| POST | `/api/auth/login` | public | Login, returns JWT |
| POST | `/api/auth/logout` | any | Clear session cookie |
| GET | `/api/auth/me` | any | Current user info |
| GET | `/api/auth/users` | admin | List all users |
| POST | `/api/auth/users` | admin | Create user |
| PUT | `/api/auth/users/{id}` | admin | Update user |

### Assignments

| Method | URL | Role | Description |
|---|---|---|---|
| GET | `/api/assignments?date_from=&date_to=` | any | List assignments |
| POST | `/api/assignments` | operator+ | Create assignment |
| PUT | `/api/assignments/{id}` | operator+ | Update assignment |
| DELETE | `/api/assignments/{id}` | operator+ | Delete assignment |
| GET | `/api/assignments/available-vans?assignment_date=&q=` | any | Available vans |
| GET | `/api/assignments/available-drivers?assignment_date=&q=` | any | Available drivers |

### Data Management

| Method | URL | Role | Description |
|---|---|---|---|
| GET | `/api/vans` | any | List vans |
| GET | `/api/vans/search?q=` | any | Search vans |
| POST | `/api/vans/{id}/toggle` | admin | Toggle van active/inactive |
| GET | `/api/drivers` | any | List drivers |
| GET | `/api/drivers/search?q=` | any | Search drivers |
| POST | `/api/drivers/{id}/toggle` | admin | Toggle driver active/inactive |
| POST | `/api/upload/vans` | admin | Upload vans CSV/XLSX |
| POST | `/api/upload/drivers` | admin | Upload drivers CSV/XLSX |
| GET | `/api/export/daily?target_date=` | any | Export daily XLSX |
| GET | `/api/export/weekly?week=` | any | Export weekly XLSX |

## Data Model

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│    vans      │     │ daily_assignments │     │   drivers   │
├─────────────┤     ├──────────────────┤     ├─────────────┤
│ id (PK)     │◄────│ van_id (FK)      │     │ id (PK)     │
│ code (UQ)   │     │ driver_id (FK)   │────►│ employee_id │
│ description │     │ assignment_date  │     │ name        │
│ active      │     │ notes            │     │ active      │
│ created_at  │     │ created_at       │     │ created_at  │
│ updated_at  │     │ updated_at       │     │ updated_at  │
└─────────────┘     │ UQ(date,van_id)  │     └─────────────┘
                    │ UQ(date,driver_id)│
                    └──────────────────┘

┌─────────────┐     ┌──────────────────┐
│    users     │     │   audit_logs     │
├─────────────┤     ├──────────────────┤
│ id (PK)     │◄────│ user_id (FK)     │
│ username(UQ)│     │ username         │
│ full_name   │     │ action           │
│ hashed_pwd  │     │ entity_type      │
│ role        │     │ entity_id        │
│ active      │     │ details          │
│ created_at  │     │ created_at       │
└─────────────┘     └──────────────────┘
```

## Security

- **JWT in httpOnly cookies** - not accessible via JavaScript, prevents XSS token theft
- **bcrypt password hashing** - industry-standard, salted
- **RBAC at API level** - role check on every endpoint, not just UI
- **UNIQUE constraints** - database-level enforcement of business rules
- **FOREIGN KEY RESTRICT** - prevents orphan data
- **SQLite WAL mode** - safe concurrent reads during writes
- **CSRF-safe** - JWT cookie with SameSite=Lax
