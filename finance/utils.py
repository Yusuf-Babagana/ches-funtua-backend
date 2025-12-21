import requests
from django.conf import settings

class Paystack:
    PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
    BASE_URL = "https://api.paystack.co"

    def initialize_payment(self, email, amount, callback_url, metadata=None):
        path = "/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {self.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        
        # Amount must be in kobo (multiply by 100)
        data = {
            "email": email,
            "amount": int(float(amount) * 100),
            "callback_url": callback_url,
            "metadata": metadata or {}
        }
        
        response = requests.post(f"{self.BASE_URL}{path}", headers=headers, json=data)
        
        if response.status_code == 200:
            return True, response.json()
        return False, response.json()

    def verify_payment(self, reference):
        path = f"/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {self.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        
        response = requests.get(f"{self.BASE_URL}{path}", headers=headers)
        
        if response.status_code == 200:
            return True, response.json()
        return False, response.json()