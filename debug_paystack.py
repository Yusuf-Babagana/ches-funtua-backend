
import os
import django
import requests
import sys

# Add project root to sys.path
sys.path.append('c:/Users/DELL/Desktop/funt/college_cms')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings

def test_paystack_init():
    print(f"PAYSTACK_SECRET_KEY: {settings.PAYSTACK_SECRET_KEY[:5]}..." if settings.PAYSTACK_SECRET_KEY else "PAYSTACK_SECRET_KEY is MISSING")
    
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "email": "test@example.com",
        "amount": 500000, # 5000 NGN
        "reference": "TEST-REF-001",
        "callback_url": f"{settings.FRONTEND_URL}/payment/verify",
        "metadata": {
            "test": "true"
        }
    }
    
    print(f"Sending request to {url}")
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        response.raise_for_status()
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_paystack_init()
