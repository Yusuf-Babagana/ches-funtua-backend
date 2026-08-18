from django.urls import path

from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('dashboard/', views.dashboard_root, name='dashboard_root'),
    path('dashboard/student/', views.dashboard_student, name='dashboard_student'),
    path('dashboard/lecturer/', views.dashboard_lecturer, name='dashboard_lecturer'),
    path('dashboard/hod/', views.dashboard_hod, name='dashboard_hod'),
    path('dashboard/registrar/', views.dashboard_registrar, name='dashboard_registrar'),
    path('dashboard/bursar/', views.dashboard_bursar, name='dashboard_bursar'),
    path('dashboard/desk-officer/', views.dashboard_desk_officer, name='dashboard_desk_officer'),
    path('dashboard/ict/', views.dashboard_ict, name='dashboard_ict'),
    path('dashboard/exam-officer/', views.dashboard_exam_officer, name='dashboard_exam_officer'),
    path('dashboard/super-admin/', views.dashboard_super_admin, name='dashboard_super_admin'),
]
