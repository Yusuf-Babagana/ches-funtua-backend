from django.urls import path

from . import views, views_lecturer, views_student

app_name = 'portal'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('dashboard/', views.dashboard_root, name='dashboard_root'),

    # --- Student (Phase 3 -- fully migrated) ---
    path('dashboard/student/', views_student.dashboard, name='dashboard_student'),
    path('dashboard/student/courses/', views_student.courses, name='student_courses'),
    path('dashboard/student/courses/<int:registration_id>/drop/', views_student.drop_course, name='student_drop_course'),
    path('dashboard/student/registration/', views_student.registration, name='student_registration'),
    path('dashboard/student/results/', views_student.results, name='student_results'),
    path('dashboard/student/transcript/', views_student.transcript, name='student_transcript'),
    path('dashboard/student/exam-card/', views_student.exam_card, name='student_exam_card'),
    path('dashboard/student/fees/', views_student.fees, name='student_fees'),
    path('dashboard/student/fees/pay/<int:invoice_id>/', views_student.pay_invoice, name='student_pay_invoice'),
    path('dashboard/student/payments/', views_student.payments, name='student_payments'),
    path('dashboard/student/payments/verify/', views_student.payment_verify, name='student_payment_verify'),
    path('dashboard/student/payments/<int:payment_id>/receipt/', views_student.receipt, name='student_receipt'),
    path('dashboard/student/print-schedule/', views_student.print_schedule, name='student_print_schedule'),
    path('dashboard/student/settings/', views_student.settings_view, name='student_settings'),

    # --- Lecturer (Phase 4 -- fully migrated) ---
    path('dashboard/lecturer/', views_lecturer.dashboard, name='dashboard_lecturer'),
    path('dashboard/lecturer/courses/', views_lecturer.courses, name='lecturer_courses'),
    path('dashboard/lecturer/courses/<int:course_id>/', views_lecturer.gradebook, name='lecturer_gradebook'),
    path('dashboard/lecturer/courses/<int:course_id>/students/', views_lecturer.course_students, name='lecturer_course_students'),
    path('dashboard/lecturer/attendance/', views_lecturer.attendance, name='lecturer_attendance'),
    path('dashboard/lecturer/attendance/<int:course_id>/mark/', views_lecturer.mark_attendance, name='lecturer_mark_attendance'),

    # --- Other roles (placeholders, migrated in later phases) ---
    path('dashboard/hod/', views.dashboard_hod, name='dashboard_hod'),
    path('dashboard/registrar/', views.dashboard_registrar, name='dashboard_registrar'),
    path('dashboard/bursar/', views.dashboard_bursar, name='dashboard_bursar'),
    path('dashboard/desk-officer/', views.dashboard_desk_officer, name='dashboard_desk_officer'),
    path('dashboard/ict/', views.dashboard_ict, name='dashboard_ict'),
    path('dashboard/exam-officer/', views.dashboard_exam_officer, name='dashboard_exam_officer'),
    path('dashboard/super-admin/', views.dashboard_super_admin, name='dashboard_super_admin'),
]
