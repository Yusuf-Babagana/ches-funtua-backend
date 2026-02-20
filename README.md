# College Management System (CMS) - Backend

A robust, enterprise-grade backend system for managing college operations, built with Django and Django REST Framework. This system streamlines administrative tasks, academic recording, and financial management for higher education institutions.

## 🚀 Key Features

### 👥 User & Access Management
- **Role-Based Access Control (RBAC)**: Supports roles like Student, Lecturer, HOD, Registrar, Bursar, Exam Officer, ICT Officer, and Super Admin.
- **Custom User Model**: Extended authentication system using email as the primary identifier.
- **Secure Authentication**: JWT-based authentication for secure API access.

### 📚 Academic Management
- **Department & Course Management**: Structured organization of academic units and modules.
- **Dynamic Semester Management**: Support for multiple sessions and semesters with level-specific configurations.
- **Course Registration Workflow**: Hierarchical approval process involving lecturers and exam officers.
- **Grade & Result Processing**: Automated calculation of GPA (4.0 scale) and CGPA.
- **Attendance Tracking**: Real-time monitoring of student attendance by lecturers.
- **Document Management**: Secure upload and verification of student academic documents.

### 💰 Financial Management
- **Automated Invoicing**: Generation of invoices based on department and level fee structures.
- **Payment Integration**: Seamless online payments via **Paystack**.
- **Manual Verification**: Workflow for bursars to verify bank transfers and other manual payments.
- **Electronic Receipts**: Automated generation of digital payment receipts.

### 📝 Admissions Management
- **Online Application Portal**: Streamlined process for prospective students.
- **Status Tracking**: Real-time updates on application reviews (Under Review, Shortlisted, Admitted).
- **Automated Admission Letters**: Generation and distribution of admission letters to successful candidates.

---

## 🛠️ Tech Stack

- **Framework**: Django 4.2+
- **API**: Django REST Framework (DRF)
- **Authentication**: REST Framework SimpleJWT
- **Database**: SQLite (Default), compatible with MySQL/PostgreSQL
- **Image Processing**: Pillow
- **Data Handling**: NumPy, Pandas
- **Other**: Django Filter, CORS Headers, Python Decouple

---

## 📁 Project Structure

```text
college_cms/
├── academics/          # Course, Grade, Registration, Attendance logic
├── admissions/         # Student application and admission workflow
├── apps/               # Shared application components
├── audit/              # System logs and audit trail
├── config/             # Project settings and core URL routing
├── finance/            # Fee structures, Invoices, and Payments (Paystack)
├── users/              # Custom User models, Student/Lecturer profiles
├── manage.py           # Django management script
└── requirements.txt    # Project dependencies
```

---

## ⚙️ Getting Started

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
   # On Windows
   source venv/Scripts/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**
   Create a `.env` file in the root directory and add necessary configurations (Secret Key, Paystack Keys, etc.).

5. **Apply Migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a Superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the Development Server**
   ```bash
   python manage.py runserver
   ```

---

## 🔗 API Documentation Summary

The API is structured around functional modules:

- **Authentication**: `/api/auth/`
- **Academics**: `/api/academics/`
- **Finance**: `/api/finance/`
- **Admissions**: `/api/admissions/`

---

## 🛠️ Development Tools

- `codebase_dumper.py`: Utility for exporting the codebase structure and content.
- `debug_paystack.py`: Script for testing Paystack integration.
- `test_imports.py`: Verification script for project dependencies.

---

## 📄 License

This project is licensed under the MIT License.