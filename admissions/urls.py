from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ApplicationViewSet, AdmissionLetterViewSet, AdmissionSessionViewSet
)

router = DefaultRouter()
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'admission-letters', AdmissionLetterViewSet, basename='admission-letter')
router.register(r'sessions', AdmissionSessionViewSet, basename='admission-session')

urlpatterns = [
    path('', include(router.urls)),
]