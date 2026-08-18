from django.urls import path

from . import views, views_bursar, views_hod, views_lecturer, views_registrar, views_student

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

    # --- HOD (Phase 5 -- fully migrated) ---
    path('dashboard/hod/', views_hod.dashboard, name='dashboard_hod'),
    path('dashboard/hod/students/', views_hod.students, name='hod_students'),
    path('dashboard/hod/lecturers/', views_hod.lecturers, name='hod_lecturers'),
    path('dashboard/hod/courses/', views_hod.courses, name='hod_courses'),
    path('dashboard/hod/courses/<int:course_id>/assign/', views_hod.assign_lecturer, name='hod_assign_lecturer'),
    path('dashboard/hod/approvals/', views_hod.approvals, name='hod_approvals'),
    path('dashboard/hod/approvals/<int:course_id>/', views_hod.approval_detail, name='hod_approval_detail'),
    path('dashboard/hod/approvals/<int:course_id>/approve/', views_hod.approve_results, name='hod_approve_results'),
    path('dashboard/hod/approvals/<int:course_id>/reject/', views_hod.reject_results, name='hod_reject_results'),

    # --- Registrar (Phase 6 -- fully migrated) ---
    path('dashboard/registrar/', views_registrar.dashboard, name='dashboard_registrar'),
    path('dashboard/registrar/applications/', views_registrar.applications, name='registrar_applications'),
    path('dashboard/registrar/students/', views_registrar.students, name='registrar_students'),
    path('dashboard/registrar/publication/', views_registrar.publication, name='registrar_publication'),
    path('dashboard/registrar/publication/<int:course_id>/', views_registrar.publication_detail, name='registrar_publication_detail'),
    path('dashboard/registrar/publication/<int:course_id>/publish/', views_registrar.publish_results, name='registrar_publish_results'),
    path('dashboard/registrar/publication/<int:course_id>/reject/', views_registrar.reject_results, name='registrar_reject_results'),
    path('dashboard/registrar/transcript/', views_registrar.transcript, name='registrar_transcript'),

    # --- Bursar (Phase 7 -- fully migrated) ---
    path('dashboard/bursar/', views_bursar.dashboard, name='dashboard_bursar'),
    path('dashboard/bursar/invoices/', views_bursar.invoices, name='bursar_invoices'),
    path('dashboard/bursar/invoices/<int:invoice_id>/mark-paid/', views_bursar.mark_invoice_paid, name='bursar_mark_invoice_paid'),
    path('dashboard/bursar/invoices/<int:invoice_id>/installment/', views_bursar.set_installment, name='bursar_set_installment'),
    path('dashboard/bursar/payments/verify/', views_bursar.verify_payments, name='bursar_verify_payments'),
    path('dashboard/bursar/payments/verify/<int:payment_id>/', views_bursar.verify_payment_action, name='bursar_verify_payment_action'),
    path('dashboard/bursar/receipts/', views_bursar.receipts, name='bursar_receipts'),
    path('dashboard/bursar/reports/revenue/', views_bursar.export_revenue, name='bursar_export_revenue'),

    # --- Other roles (placeholders, migrated in later phases) ---
    path('dashboard/desk-officer/', views.dashboard_desk_officer, name='dashboard_desk_officer'),
    path('dashboard/ict/', views.dashboard_ict, name='dashboard_ict'),
    path('dashboard/exam-officer/', views.dashboard_exam_officer, name='dashboard_exam_officer'),
    path('dashboard/super-admin/', views.dashboard_super_admin, name='dashboard_super_admin'),
]
