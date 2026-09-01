from django.urls import path

from . import (
    views, views_bursar, views_desk_officer, views_exam_officer, views_hod,
    views_lecturer, views_registrar, views_student,
)

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
    path('dashboard/student/fees/catalog/', views_student.fee_catalog, name='student_fee_catalog'),
    path('dashboard/student/fees/catalog/<int:fee_item_id>/pay/', views_student.pay_fee_item, name='student_pay_fee_item'),
    path('dashboard/student/practical-center/', views_student.practical_center, name='student_practical_center'),
    path('dashboard/student/index-info/', views_student.index_info, name='student_index_info'),
    path('dashboard/student/carryover/', views_student.carryover, name='student_carryover'),
    path('dashboard/student/carryover/<int:course_id>/register/', views_student.register_carryover, name='student_register_carryover'),
    path('dashboard/student/carryover/<int:registration_id>/slip/', views_student.carryover_slip, name='student_carryover_slip'),
    path('dashboard/student/support/', views_student.support, name='student_support'),
    path('dashboard/student/support/poll/', views_student.support_poll, name='student_support_poll'),
    path('dashboard/student/support/send/', views_student.support_send, name='student_support_send'),
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
    path('dashboard/lecturer/announcements/post/', views_lecturer.post_announcement, name='lecturer_post_announcement'),

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
    path('dashboard/hod/announcements/post/', views_hod.post_announcement, name='hod_post_announcement'),

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
    path('dashboard/bursar/fee-items/', views_bursar.fee_items, name='bursar_fee_items'),
    path('dashboard/bursar/fee-items/charges/<int:charge_id>/deactivate/', views_bursar.deactivate_fee_item_charge, name='bursar_deactivate_fee_item_charge'),
    path('dashboard/bursar/payments/verify/', views_bursar.verify_payments, name='bursar_verify_payments'),
    path('dashboard/bursar/payments/verify/<int:payment_id>/', views_bursar.verify_payment_action, name='bursar_verify_payment_action'),
    path('dashboard/bursar/receipts/', views_bursar.receipts, name='bursar_receipts'),
    path('dashboard/bursar/reports/revenue/', views_bursar.export_revenue, name='bursar_export_revenue'),

    # --- Exam Officer (Phase 8 -- fully migrated, minus the fake/non
    #     -persistent timetable feature -- see services_exam_officer.py) ---
    path('dashboard/exam-officer/', views_exam_officer.dashboard, name='dashboard_exam_officer'),
    path('dashboard/exam-officer/registrations/', views_exam_officer.registrations, name='eo_registrations'),
    path('dashboard/exam-officer/registrations/<int:registration_id>/approve/', views_exam_officer.approve_registration, name='eo_approve_registration'),
    path('dashboard/exam-officer/results/', views_exam_officer.results, name='eo_results'),
    path('dashboard/exam-officer/results/<int:course_id>/', views_exam_officer.result_detail, name='eo_result_detail'),
    path('dashboard/exam-officer/results/<int:course_id>/verify/', views_exam_officer.verify_results, name='eo_verify_results'),
    path('dashboard/exam-officer/results/<int:course_id>/master-sheet/', views_exam_officer.master_sheet, name='eo_master_sheet'),

    # --- Desk Officer (Phase 9 -- built as real, working pages; the old
    #     frontend's desk-officer pages were non-functional placeholders
    #     -- see services_desk_officer.py) ---
    path('dashboard/desk-officer/', views_desk_officer.dashboard, name='dashboard_desk_officer'),
    path('dashboard/desk-officer/students/', views_desk_officer.students, name='do_students'),
    path('dashboard/desk-officer/students/<int:student_id>/', views_desk_officer.student_profile, name='do_student_profile'),
    path('dashboard/desk-officer/documents/', views_desk_officer.documents, name='do_documents'),
    path('dashboard/desk-officer/documents/<int:document_id>/verify/', views_desk_officer.verify_document, name='do_verify_document'),
    path('dashboard/desk-officer/queries/', views_desk_officer.queries, name='do_queries'),
    path('dashboard/desk-officer/queries/<int:query_id>/assign/', views_desk_officer.assign_query, name='do_assign_query'),
    path('dashboard/desk-officer/queries/<int:query_id>/resolve/', views_desk_officer.resolve_query, name='do_resolve_query'),
    path('dashboard/desk-officer/payments/', views_desk_officer.payments, name='do_payments'),
    path('dashboard/desk-officer/payments/<int:payment_id>/verify/', views_desk_officer.verify_payment, name='do_verify_payment'),
    path('dashboard/desk-officer/registration/', views_desk_officer.registration, name='do_registration'),
    path('dashboard/desk-officer/support/', views_desk_officer.support_inbox, name='do_support'),
    path('dashboard/desk-officer/support/<int:thread_id>/', views_desk_officer.support_thread, name='do_support_thread'),
    path('dashboard/desk-officer/support/<int:thread_id>/poll/', views_desk_officer.support_thread_poll, name='do_support_thread_poll'),
    path('dashboard/desk-officer/support/<int:thread_id>/send/', views_desk_officer.support_thread_send, name='do_support_thread_send'),
    path('dashboard/desk-officer/support/<int:thread_id>/close/', views_desk_officer.support_close_thread, name='do_support_close_thread'),

    # --- Other roles (placeholders, migrated in later phases) ---
    path('dashboard/ict/', views.dashboard_ict, name='dashboard_ict'),
    path('dashboard/super-admin/', views.dashboard_super_admin, name='dashboard_super_admin'),
]
