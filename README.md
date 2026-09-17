# LaunchPad

## Product Overview

LaunchPad is the operating system for college projects: **Build. Track. Verify. Showcase.** It transforms a student project from an idea into a durable Project Record with team history, academic context, mentorship, milestones, reviews, submission, verification, recognition, and archive history.

The existing community layer remains focused on project discovery and collaboration through likes, comments, follows, bookmarks, collections, contests, certificates, achievements, and notifications.

## Features

- Project Records with stable identifiers and lifecycle history
- College, department, program, academic year, and semester hierarchy
- Student, faculty, mentor, department admin, college admin, platform admin, and judge role metadata
- Team members, mentorship requests, milestones, approvals, reviews, verification, documents, and archive state
- Server-side object access checks and cross-college authorization boundaries
- Existing authentication, profiles, project discovery, social engagement, bookmarks, contests, analytics, and notifications
- Project command-center workspace with lifecycle transitions and operational context
- PostgreSQL production configuration with an optional SQLite local-validation override
- Additive Django migrations that preserve existing application data

## Technology Stack

- Python 3.11+
- Django 5.2.6
- PostgreSQL (default production database)
- SQLite (optional local testing only)
- Django templates, HTML, CSS, JavaScript, and HTMX
- Pillow for image handling

## Project Structure

- `config/` — Django settings, WSGI, ASGI, and root URLs
- `core/` — application models, views, forms, templates, static files, migrations, tests, and management commands
- `media/` — sample media files included by the source project
- `LaunchPad_Info.pdf` — original product brief
- `manage.py` — Django management entry point

The application intentionally uses the existing `core` app rather than creating disconnected empty apps. New domain entities are integrated into the existing authentication and project system.

## Requirements

Install Python 3.11 or newer and PostgreSQL for normal deployment. Install Python dependencies with:

```bash
python -m pip install -r requirements.txt
```

## Installation

```bash
git clone <repository-url>
cd launchpad
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with a unique secret key and database credentials before starting the application.

## Environment Configuration

`.env.example` is safe to copy and contains placeholders only. Important settings include:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- Optional upload, email, HTTPS, proxy, HSTS, static, and media settings

Never commit the real `.env` file or credentials.

## Database Setup

PostgreSQL is the default database. Create an empty database and configure its credentials in `.env`, then run:

```bash
python manage.py migrate
python manage.py createsuperuser
```

For local validation without PostgreSQL, use the explicit SQLite override:

```bash
DJANGO_DB_ENGINE=django.db.backends.sqlite3 \\
DJANGO_DB_NAME=local.sqlite3 \\
DJANGO_DEBUG=True \\
python manage.py migrate
```

SQLite is intended for local development and testing; PostgreSQL remains the normal production database.

## Migrations

All historical migrations are retained. The transformation adds migrations for the institutional hierarchy, Project Record foundation, lifecycle/workflow records, and safe legacy Project Record ID backfilling.

```bash
python manage.py showmigrations
python manage.py migrate
```

Existing projects with no stable identifier receive an `LP-LEGACY-######` identifier through the data migration without deleting or resetting records.

## Creating a Superuser

```bash
python manage.py createsuperuser
```

The admin site is available at `/admin/`. Role metadata for profiles can be maintained through the admin interface. Administrative actions remain protected server-side.

## Running the Development Server

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in a browser.

## Running Tests

Run all tests with an isolated SQLite database:

```bash
DJANGO_DB_ENGINE=django.db.backends.sqlite3 \\
DJANGO_DB_NAME=test.sqlite3 \\
DJANGO_DEBUG=True \\
python manage.py test core
```

Run Project Record regression tests only:

```bash
DJANGO_DB_ENGINE=django.db.backends.sqlite3 \\
DJANGO_DB_NAME=test.sqlite3 \\
DJANGO_DEBUG=True \\
python manage.py test core.tests_project_record
```

## Demo/Seed Data

The repository includes the existing seed management commands and fictional category/demo-data utilities where provided by the source project. Any generated seed records must be treated as fictional development data, not real institutions, users, adoption, partnerships, or awards.

## User Roles

- **Student** — builds Project Records, forms teams, requests mentors, manages milestones, submits work, and showcases projects.
- **Faculty / Mentor** — supervises assigned work, responds to mentorship requests, reviews proposals and milestones, and records verification.
- **Department Admin** — manages department-level project operations and reviews.
- **College Admin** — manages college-level project operations and institutional context.
- **Platform Admin** — manages platform-wide operations.
- **Judge** — reserved for assigned contest evaluation workflows.

Role and college checks are enforced on the server; hiding a navigation link is not treated as authorization.

## Project Lifecycle

Project Records support explicit lifecycle states and immutable transition events:

`IDEA → TEAM FORMATION → MENTOR ASSIGNMENT → PROPOSAL → APPROVAL → PLANNING → DEVELOPMENT → MILESTONES → REVIEW → SUBMISSION → EVALUATION → VERIFICATION → SHOWCASE → ARCHIVE`

The lifecycle workspace is available at `/projects/<id>/workspace/` for authorized project participants and institutional reviewers.

## Multi-College Architecture

Institutional records are linked through `College → Department → Program → Academic Year → Semester`. Project and profile context can reference these entities. Administrative and review endpoints check the requester's college before allowing institution-scoped actions.

## Important URLs

- `/` — public landing page
- `/projects/` — project discovery
- `/projects/create/` — create a Project Record
- `/projects/<id>/workspace/` — Project Record command center
- `/dashboard/` — authenticated dashboard
- `/contests/` — contests and submissions
- `/leaderboard/` — community leaderboard
- `/analytics/` — personal analytics
- `/admin/` — Django administration

## Troubleshooting

- If Django reports a missing secret key with `DEBUG=False`, set `DJANGO_SECRET_KEY` in `.env`.
- If PostgreSQL is unavailable locally, use the documented SQLite override for development and tests.
- If the host is rejected, add the hostname to `DJANGO_ALLOWED_HOSTS`.
- If HTTPS redirects prevent local login, use `DJANGO_DEBUG=True` or explicitly set `DJANGO_SECURE_MODE=False` for local-only development.
- Uploaded files are validated and size-limited. Executable uploads are not an intended supported document type.
- Run `python manage.py check` after changing configuration.

## Security Notes

Do not place secrets in source control. CSRF protection, authentication, upload validation, server-side permissions, tenant checks, and secure-cookie settings are retained from the existing application and extended for Project Record workflows.
