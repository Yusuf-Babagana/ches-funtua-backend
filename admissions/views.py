from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from datetime import datetime

from .models import Application, AdmissionLetter, AdmissionSession
from .serializers import (
    ApplicationSerializer, ApplicationCreateSerializer,
    ApplicationStatusUpdateSerializer, AdmissionLetterSerializer,
    AdmissionSessionSerializer
)
from users.permissions import CanManageAdmissions


class ApplicationViewSet(viewsets.ModelViewSet):
    """Application operations"""
    queryset = Application.objects.select_related(
        'first_choice_department',
        'second_choice_department',
        'reviewed_by'
    ).all()
    permission_classes = [AllowAny]  # Allow public application submission
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'session', 'programme_type', 'first_choice_department']
    search_fields = ['application_number', 'email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['submitted_date', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ApplicationCreateSerializer
        elif self.action == 'update_status':
            return ApplicationStatusUpdateSerializer
        return ApplicationSerializer
    
    def get_permissions(self):
        # Public can create and retrieve by application number
        if self.action in ['create', 'retrieve_by_number']:
            return [AllowAny()]
        # Admin staff for other actions
        return [IsAuthenticated(), CanManageAdmissions()]
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def retrieve_by_number(self, request):
        """Retrieve application by application number"""
        app_number = request.query_params.get('application_number')
        if not app_number:
            return Response(
                {'error': 'application_number parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            application = Application.objects.get(application_number=app_number)
            serializer = self.get_serializer(application)
            return Response(serializer.data)
        except Application.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated, CanManageAdmissions])
    def update_status(self, request, pk=None):
        """Update application status"""
        application = self.get_object()
        serializer = ApplicationStatusUpdateSerializer(
            application,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        
        application.reviewed_by = request.user
        application.review_date = datetime.now()
        serializer.save()
        
        return Response(ApplicationSerializer(application).data)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get application statistics"""
        queryset = self.filter_queryset(self.get_queryset())
        
        status_counts = {}
        for status_choice in Application.STATUS_CHOICES:
            status_counts[status_choice[0]] = queryset.filter(
                status=status_choice[0]
            ).count()
        
        programme_counts = {}
        for programme in Application.PROGRAMME_CHOICES:
            programme_counts[programme[0]] = queryset.filter(
                programme_type=programme[0]
            ).count()
        
        return Response({
            'total_applications': queryset.count(),
            'status_breakdown': status_counts,
            'programme_breakdown': programme_counts
        })


class AdmissionLetterViewSet(viewsets.ModelViewSet):
    """Admission letter operations"""
    queryset = AdmissionLetter.objects.select_related(
        'application',
        'department',
        'issued_by'
    ).all()
    serializer_class = AdmissionLetterSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'session', 'level']
    search_fields = ['admission_number', 'matric_number', 'application__first_name', 'application__last_name']
    ordering_fields = ['issued_date']
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageAdmissions()]
        # Allow applicants to view their own admission letter
        if self.action in ['retrieve', 'download']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def download(self, request, pk=None):
        """Track admission letter downloads"""
        letter = self.get_object()
        letter.is_downloaded = True
        letter.download_count += 1
        letter.save()
        
        serializer = self.get_serializer(letter)
        return Response(serializer.data)


class AdmissionSessionViewSet(viewsets.ModelViewSet):
    """Admission session operations"""
    queryset = AdmissionSession.objects.all()
    serializer_class = AdmissionSessionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_active']
    ordering_fields = ['start_date', 'session']
    
    def get_permissions(self):
        if self.action in ['retrieve', 'list', 'current']:
            return [AllowAny()]
        return [CanManageAdmissions()]
    
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def current(self, request):
        """Get current admission session"""
        try:
            session = AdmissionSession.objects.get(is_active=True)
            serializer = self.get_serializer(session)
            return Response(serializer.data)
        except AdmissionSession.DoesNotExist:
            return Response(
                {'error': 'No active admission session'},
                status=status.HTTP_404_NOT_FOUND
            )