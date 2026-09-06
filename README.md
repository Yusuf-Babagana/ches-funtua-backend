# College Management System (CMS) - Backend Architecture & Technical Guide

A robust, enterprise-grade backend system for managing college operations, built with Django and Django REST Framework. This system streamlines administrative tasks, academic recording, and financial management for higher education institutions.

**Notice to AI Agents:** This `README.md` provides detailed internal logics, entity relationships, and operational flows to aid in debugging, refactoring, and feature expansion.

---

## 🏗️ System Architecture & Core Modules

The system is designed with a monolithic Django architecture, highly decoupled into functional "apps" (`users`, `academics`, `finance`, `admissions`, `audit`).

### 1. 👥 Users App (Role-Based Access Control)
The core of the system’s permissions uses a custom `User` model tied to email authentication with JWT. Roles dictate exactly what actions can be taken in the Academic and Finance modules.
- **Roles:** `student`, `lecturer`, `hod`, `registrar`, `bursar`, `desk-officer`, `ict`, `exam-officer`, `super-admin`.
- **Profiles:**
  - `Student`: Extends `User`. Contains `matric_number`, `level` (100, 200, 300), `status` (active, graduated), and maps to a `Department`.
  - `Lecturer`: Extends `User`. Contains `staff_id`, `designation` (Professor, etc.), and `is_hod` flag.
  - `StaffProfile`: For administrative staff.

### 2. 📚 Academics App (Course & Grade Workflow)
This app manages the lifecycle of a student's academic journey.
- **Core Entities:** `Department`, `Course`, `Semester`, `AcademicLevelConfiguration` (manages level-specific open/close registration windows).
- **Course Registration (`CourseRegistration`):**
  - **Prerequisites:** Students must have passed (`A`, `B`, `C`, `D`) prerequisite courses before registering for advanced courses.
  - **Capacity:** Controlled via `CourseOffering.capacity`.
  - **Approval Workflow (Strict Linear Progression):**
    1. **Pending:** Student requests registration.
    2. **Lecturer Approval (`approved_lecturer`):** Handled by the course lecturer or designated advisor.
    3. **Payment Verification Check:** Before the next stage, `CourseRegistration.verify_payment()` checks if a fully `paid` `Invoice` exists for the current semester in the `Finance` module.
    4. **Exam Officer Approval (`registered`):** Final approval. Status becomes `registered`.
- **Grading System (`Grade` & `StudentAcademicRecord`):**
  - Uses a **4.0 GPA Scale**. `calculate_grade_points()` automates credit calculation.
  - **Grade Approval Workflow:**
    1. **Draft:** Lecturer enters draft scores.
    2. **Submitted:** Lecturer submits, awaiting HOD approval.
    3. **HOD Approved:** Awaiting Exam Officer.
    4. **Verified:** Awaiting Registrar.
    5. **Published:** Visible to the student.

### 3. 💰 Finance App (Invoicing & Paystack)
Handles institutional revenue tracking using external payment gateways.
- **Core Entities:** `FeeStructure`, `Invoice`, `Payment`, `PaystackTransaction`, `PaymentReceipt`.
- **Invoicing Logic:** Generating an `Invoice` dynamically pulls the `FeeStructure` based on the student's `department`, `level`, `session`, and `semester`.
- **Payment Verification Flow (Paystack):**
  1. Student initiates payment -> `Payment` record created with `status='pending'`.
  2. Frontend communicates with Paystack.
  3. Paystack verification endpoint (`/api/finance/paystack/verify/`) confirms the payment and maps it to `PaystackTransaction`.
  4. `Payment` is marked `completed`.
  5. Associated `Invoice.amount_paid` is updated. If `amount_paid >= amount`, `Invoice.status` moves to `paid`.
  6. **Cross-module Effect:** Setting an invoice to `paid` allows the `CourseRegistration` module to let Exam Officers approve courses (relieves the *"Registration Block"*).

### 4. 📝 Admissions & Documents App
- Tracks prospect applications (`Under Review` -> `Shortlisted` -> `Admitted`).
- `StudentDocument` uploads require administrative verification (`pending` -> `verified`).

---

## 🧭 Known Context & Historical Debugging Logs
For any AI continuing work on this system, be aware of past issues and logic expansions:
- **Registration cap is credit-unit based, not a course count:** students can't exceed `MAX_CREDIT_UNITS_UNPAID` (8) total registered credit units while unpaid, or `MAX_CREDIT_UNITS_PAID` (24) once fees are paid -- see `academics/constants.py`, the single source of truth imported by both the DRF API (`academics/views_registration.py`, `views_student.py`, `views_desk_officer.py`) and the `portal` app's student/desk-officer services. This replaced three previously-inconsistent course-*count* caps (2 unpaid/15 paid on self-service, 6 on the desk-officer override) that had drifted apart from each other -- if you're about to add a new registration entry point, import the constant, don't hardcode a number.
- **Lecturer Registration (`users.views.py`):** The `AuthViewSet` required a custom `register_lecturer` action mapped to `LecturerCreateSerializer`.
- **Payment Status Update Failures:** When Paystack verifies a payment, the callback/verification view *must* accurately trigger the `Invoice.update_status()` method. Bug occurrences in the past involve "Internal Server Error" on Paystack verification, meaning `has_paid_fees` (handled via `Invoice.is_tuition_paid()`) wasn't correctly unblocking the academic registration.
- **Login Fixes:** Mobile/Frontend logic depends on explicitly expecting `username` (which maps to the user's `email`) for JWT retrieval.

---

## 🛠️ API & Endpoint Overview
The API is heavily grouped and secured by JWT.
- **Authentication**: `/api/auth/` (Login, Registration)
- **Finance**: `/api/finance/` Handles Paystack intents, `current-invoice/`, and verifying Paystack.
- **Academics**: `/api/academics/` Grades, Course Registration, Approvals.
- **Admissions**: `/api/admissions/`

---

## 🖥️ Frontend: `portal` app (Django templates -- production frontend)
The production frontend is **this Django project itself**, not a separate deployment. The
`portal` app (session-authenticated, server-rendered templates under `templates/dashboard/`
and `templates/portal/`) is a full, real implementation of every one of the 9 roles
(student, lecturer, hod, registrar, bursar, desk-officer, ict, super-admin) plus the public
landing/login pages -- it replaced a previously-separate Next.js frontend that used to be
deployed on Vercel and call this same DRF API cross-origin. That Next.js project is retired;
nothing about it needs to be deployed, and CORS/CSRF no longer need to allow-list a separate
frontend origin (see `config/settings.py`'s CORS/CSRF section).

The DRF JWT API above stays fully intact and independently usable -- the `portal` app's own
views call the same service-layer/model logic directly (never over HTTP to itself), so mobile
apps or any other external client can keep authenticating against `/api/auth/token/` exactly
as before. Business logic for each role lives in `portal/services_<role>.py`; `portal/views_<role>.py`
are thin views that call into it and render a template. A small `support` app (`support/models.py`:
`ChatThread`/`ChatMessage`) backs a polling-based support chat between students and desk officers,
separate from the older `academics.StudentQuery` ticket model.

Every role's dashboard, and the shared rules they depend on (the registration cap above, the
5-stage grade workflow: draft → submitted → hod_approved → verified → published), has a permanent
regression suite in `portal/tests/` -- run it with `python manage.py test portal finance.test_fix`
(use explicit app labels; see the note in that section below about why bare `manage.py test` isn't
reliable here).

---

## ⚙️ Getting Started (Local Setup)

### Prerequisites
- Python 3.9+
- pip (Python package manager)

### Installation
1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd college_cms
   ```
2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # On Windows
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Variables**
   `config/settings.py` reads config directly from the process environment (`os.environ`) --
   there's no `.env`-file loader wired in (no `python-dotenv`/`django-environ`/`python-decouple`
   in `requirements.txt`), so a `.env` file sitting in the repo does nothing on its own. Export
   the variables in your shell before running `manage.py`, or set them in your terminal profile.
   Locally, everything has a working default except the Paystack keys (test keys are baked in as
   fallbacks, so even those are optional for non-payment work). See **Environment Variables
   Reference** below for the full list.
5. **Apply Migrations and Run**
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

### Included Development Utilities
- `codebase_dumper.py`: Utility for exporting the local codebase contexts for LLM injections.
- `debug_paystack.py`: Sandbox script for quickly testing Paystack keys.
- `test_imports.py`: Quick verification to check for circular dependency issues. Not a real
  Django test (no test methods, just a print statement) -- don't run it via `manage.py test`
  (bare, label-less `manage.py test` picks it up through top-level discovery and can crash on
  Windows console encoding when it prints a ❌/✅ character; run `manage.py test portal
  finance.test_fix` instead, which only discovers real tests).

---

## ✅ Running the Test Suite
The permanent regression suite lives in `portal/tests/` (9-role fixture, cross-role workflow
tests, a full page-render sweep, and permission-boundary/security-fix coverage) plus
`finance/test_fix.py` (pre-existing, predates the `portal` app). Run both with explicit app
labels -- **not** bare `manage.py test`, which also discovers the stray `test_imports.py` script
above and crashes on it:
```bash
python manage.py test portal finance.test_fix
```
One test in `finance/test_fix.py` (`test_paystack_verify_get_method`) is marked
`@unittest.expectedFailure` -- it documents a real, pre-existing gap (`paystack-verify` only
routes POST, not the GET the test wants) that's a genuine API-surface decision, not something
fixed as part of the frontend migration. Everything else should report `OK`.

---

## 🚀 Deploying to Production (PythonAnywhere)

The app is designed to run as a single Django deployment -- no separate frontend build/deploy
step. Broad strokes for a PythonAnywhere web app pointed at this repo:

1. **Pull the code** into your PythonAnywhere console (`git clone`/`git pull`) and create a
   virtualenv, then `pip install -r requirements.txt` inside it.
2. **Set environment variables.** PythonAnywhere doesn't read a `.env` file either -- set these
   either as real env vars in a `.bashrc`/`virtualenv postactivate` sourced before the web app
   starts, or (most reliably on PA) directly in your WSGI config file
   (`/var/www/<you>_pythonanywhere_com_wsgi.py`) with `os.environ['KEY'] = 'value'` lines *before*
   the `from config.wsgi import application` line. See **Environment Variables Reference** below
   for the full list -- at minimum you need `SECRET_KEY` and `DEBUG=False`; the app will refuse to
   start under `DEBUG=False` with the placeholder secret key rather than silently running
   insecurely (`config/settings.py`).
3. **Point the WSGI file at this project.** PythonAnywhere's generated WSGI file needs your
   project path added to `sys.path` and `DJANGO_SETTINGS_MODULE` set to `config.settings`, then:
   ```python
   from config.wsgi import application
   ```
4. **Migrate and collect static files:**
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
5. **Static & media file mappings.** This project does not bundle a static-file server
   (no WhiteNoise) since PythonAnywhere serves static/media files itself via URL mappings
   configured in the *Web* tab, not through Django/WSGI. Add two mappings there:
   - URL `/static/` → Directory: the `STATIC_ROOT` path (`staticfiles/` under the project root)
   - URL `/media/` → Directory: the `MEDIA_ROOT` path (`media/` under the project root -- used by
     the Index Information form's passport-photo upload)
6. **Reload the web app** from the PythonAnywhere dashboard.

### Environment Variables Reference
| Variable | Required in prod? | Notes |
|---|---|---|
| `SECRET_KEY` | **Yes** | App refuses to boot under `DEBUG=False` with the dev placeholder. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. |
| `DEBUG` | **Yes** (`False`) | Also gates the security-hardening block below -- leaving it unset/`True` in production skips HTTPS redirect, secure cookies, etc. |
| `ALLOWED_HOSTS` | Recommended | Defaults to `localhost,127.0.0.1,funtua.pythonanywhere.com` -- override if your PA domain differs. |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Only if you have an external API consumer | The `portal` frontend is same-origin and needs neither. Only set these for a genuinely separate site/app calling the JWT API cross-origin. |
| `SECURE_SSL_REDIRECT` | Optional (defaults `True` under `DEBUG=False`) | Set `False` only if the site must also serve plain HTTP. |
| `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | Optional, off by default | HSTS is browser-cached and hard to safely undo -- deliberately opt-in, not a default, once you're sure the whole site (and subdomains, if included) will always be HTTPS. |
| `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY` | **Yes**, for real payments | Test-key fallbacks are baked in; replace with live keys for production. Never commit real keys. |