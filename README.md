# College Management System (CMS) - Backend Architecture & Technical Guide

A robust, enterprise-grade backend system for managing college operations, built with Django and Django REST Framework. This system streamlines administrative tasks, academic recording, and financial management for higher education institutions.

**Notice to AI Agents:** This `README.md` provides detailed internal logics, entity relationships, and operational flows to aid in debugging, refactoring, and feature expansion.

---

## � System Architecture & Core Modules

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

## � Known Context & Historical Debugging Logs
For any AI continuing work on this system, be aware of past issues and logic expansions:
- **Registration Block Message Error:** Previously, students couldn't register for courses if their fees weren't paid. A business rule allows a **2-course exception** for unpaid students. If encountering registration block bugs, verify `academics` views to ensure this 2-course exception bypasses the strict `is_payment_verified` rule dynamically.
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
   Create a `.env` file in the root directory (ensure Paystack keys, DB config, and JWT Secret).
5. **Apply Migrations and Run**
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

### Included Development Utilities
- `codebase_dumper.py`: Utility for exporting the local codebase contexts for LLM injections.
- `debug_paystack.py`: Sandbox script for quickly testing Paystack keys.
- `test_imports.py`: Quick verification to check for circular dependency issues.