# -*- coding: utf-8 -*-
"""
OxaPay Crypto Payment Integration
"""

import requests
import hashlib
import hmac
from typing import Dict, Optional
import os
from dotenv import load_dotenv
from HacxGPT import Config

load_dotenv(dotenv_path=Config.ENV_FILE)

OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY")
OXAPAY_MERCHANT_ID = os.getenv("OXAPAY_MERCHANT_ID")
OXAPAY_API_URL = "https://api.oxapay.com/merchants/request"

# If only merchant ID is provided (common case), use it as API key
# Many OxaPay setups use merchant ID as the API key for authentication
if OXAPAY_MERCHANT_ID and (not OXAPAY_API_KEY or OXAPAY_API_KEY == "your_oxapay_api_key"):
    OXAPAY_API_KEY = OXAPAY_MERCHANT_ID

# Subscription plans
PLANS = {
    'test': {
        'name': 'Test Plan',
        'price': 15.0,
        'duration_days': 7,
        'requests': 100,
        'description': '1 Week - 100 Requests'
    },
    'premium': {
        'name': 'Premium Plan',
        'price': 100.0,
        'duration_days': 30,
        'requests': 1500,
        'description': '1 Month - 1500 Requests'
    }
}


class OxaPay:
    def __init__(self, api_key: str = None, merchant_id: str = None):
        self.api_key = api_key or OXAPAY_API_KEY
        self.merchant_id = merchant_id or OXAPAY_MERCHANT_ID
        self.api_url = OXAPAY_API_URL
    
    def create_invoice(self, amount: float, currency: str = "USD", 
                      order_id: str = None, callback_url: str = None,
                      description: str = None) -> Dict:
        """
        Create payment invoice
        Returns invoice URL and invoice ID
        """
        if not self.api_key or not self.merchant_id:
            raise ValueError("OxaPay API credentials not configured")
        
        payload = {
            "merchant": self.merchant_id,
            "amount": amount,
            "currency": currency,
            "orderId": order_id or f"SMG{int(__import__('time').time())}",
            "description": description or "SMG-Forcer Subscription",
            "callbackUrl": callback_url or "",
            "returnUrl": callback_url or "",
            "underPaidCover": 0,
            "lifetime": 30,  # 30 minutes
            "feePaidByPayer": 0
        }
        
        # Create signature
        signature_string = f"{self.merchant_id}{payload['amount']}{payload['currency']}{payload['orderId']}{self.api_key}"
        signature = hashlib.sha256(signature_string.encode()).hexdigest()
        payload['sign'] = signature
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Log full response for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"OxaPay API Response: {data}")
            
            if data.get('result') == 100:
                # Try multiple possible field names for invoice ID
                # OxaPay API returns 'trackId' as the invoice identifier
                invoice_id = (
                    data.get('trackId') or  # Primary field name used by OxaPay
                    data.get('track_id') or
                    data.get('invoiceId') or 
                    data.get('invoice_id') or 
                    data.get('invoiceID') or
                    data.get('id') or
                    data.get('invoice')
                )
                
                pay_link = data.get('payLink') or data.get('pay_link') or data.get('url')
                
                # If invoice_id is not in response, extract it from payLink URL
                # URL format: https://pay.oxapay.com/{merchant_id}/{invoice_id}
                if not invoice_id and pay_link:
                    try:
                        import re
                        # Extract invoice ID from URL (last number after last slash)
                        match = re.search(r'/(\d+)/?$', pay_link.rstrip('/'))
                        if match:
                            invoice_id = match.group(1)
                            logger.info(f"Extracted invoice_id from URL: {invoice_id}")
                    except Exception as e:
                        logger.warning(f"Could not extract invoice_id from URL: {e}")
                
                if not invoice_id:
                    logger.error(f"Invoice ID not found in response or URL. Response: {data}")
                    return {
                        'success': False,
                        'error': 'Invoice ID not found in API response'
                    }
                
                return {
                    'success': True,
                    'invoice_id': invoice_id,
                    'invoice_url': pay_link,
                    'order_id': payload['orderId']
                }
            else:
                error_msg = data.get('errMsg', f"API returned result code: {data.get('result')}")
                logger.error(f"OxaPay API error: {error_msg}, Full response: {data}")
                return {
                    'success': False,
                    'error': error_msg
                }
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"OxaPay API exception: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def verify_payment(self, invoice_id: str) -> Dict:
        """
        Verify payment status
        """
        if not self.api_key or not self.merchant_id:
            raise ValueError("OxaPay API credentials not configured")
        
        verify_url = "https://api.oxapay.com/merchants/inquiry"
        
        payload = {
            "merchant": self.merchant_id,
            "invoiceId": invoice_id
        }
        
        signature_string = f"{self.merchant_id}{invoice_id}{self.api_key}"
        signature = hashlib.sha256(signature_string.encode()).hexdigest()
        payload['sign'] = signature
        
        try:
            response = requests.post(verify_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('result') == 100:
                return {
                    'success': True,
                    'status': data.get('status'),
                    'paid': data.get('status') == 'paid',
                    'amount': data.get('amount'),
                    'currency': data.get('currency')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('errMsg', 'Unknown error')
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_subscription_payment(self, user_id: int, plan_type: str, 
                                   callback_url: str = None) -> Dict:
        """Create payment for subscription plan"""
        if plan_type not in PLANS:
            return {'success': False, 'error': 'Invalid plan type'}
        
        plan = PLANS[plan_type]
        order_id = f"SMG{user_id}{int(__import__('time').time())}"
        
        description = f"SMG-Forcer {plan['name']} - {plan['description']}"
        
        result = self.create_invoice(
            amount=plan['price'],
            currency="USD",
            order_id=order_id,
            callback_url=callback_url,
            description=description
        )
        
        if result['success']:
            result['plan_type'] = plan_type
            result['amount'] = plan['price']
            result['user_id'] = user_id
        
        return result


def get_plan_info(plan_type: str) -> Optional[Dict]:
    """Get plan information"""
    return PLANS.get(plan_type)

