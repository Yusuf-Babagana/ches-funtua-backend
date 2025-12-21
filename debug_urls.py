import os
import django
from django.conf import settings
from django.urls import reverse

import sys
sys.path.append('c:/Users/DELL/Desktop/funt/college_cms')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

try:
    print("Attempting to reverse URLs...")
    
    # Academics
    try:
        url = reverse('student-dashboard-current-semester')
        print(f"Academics Current Semester: {url}")
    except Exception as e:
        print(f"Academics Current Semester Failed: {e}")
        
    # Finance
    try:
        url = reverse('current-invoice')
        print(f"Finance Current Invoice: {url}")
    except Exception as e:
        print(f"Finance Current Invoice Failed: {e}")

    # Check if student-dashboard-list exists (base viewset)
    try:
        url = reverse('student-dashboard-list')
        print(f"Student Dashboard List: {url}")
    except Exception as e:
        print(f"Student Dashboard List Failed: {e}")

except Exception as e:
    print(f"General Error: {e}")
