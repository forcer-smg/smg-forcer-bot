# -*- coding: utf-8 -*-
"""
Fix Payment Webhook - Enhanced webhook handler with better logging and error handling
Also includes manual payment verification and confirmation
"""

import os
import sys
import logging
import json
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import database
try:
    from database_postgres import Database
    db = Database()
    logger.info("✅ Connected to PostgreSQL/Supabase database")
except Exception as e:
    logger.error(f"❌ Failed to connect to database: {e}")
    sys.exit(1)

# Try to import OxaPay
try:
    from oxapay import OxaPay
    oxapay = OxaPay()
    logger.info("✅ OxaPay client initialized")
except Exception as e:
    logger.warning(f"⚠️ OxaPay not available: {e}")
    oxapay = None


def enhanced_complete_payment(invoice_id: str, track_id: Optional[str] = None) -> Dict:
    """
    Enhanced payment completion with better error handling and logging
    """
    logger.info(f"🔍 Processing payment completion for invoice: {invoice_id}")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # First, try to find payment by invoice_id
        cursor.execute("""
            SELECT * FROM payments 
            WHERE oxapay_invoice_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (invoice_id,))
        
        payment = cursor.fetchone()
        
        if not payment:
            # Try to find by track_id if provided
            if track_id:
                logger.info(f"🔍 Payment not found by invoice_id, trying track_id: {track_id}")
                cursor.execute("""
                    SELECT * FROM payments 
                    WHERE payment_id LIKE %s OR oxapay_invoice_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (f'%{track_id}%', track_id))
                payment = cursor.fetchone()
        
        if not payment:
            logger.warning(f"⚠️ Payment not found for invoice_id: {invoice_id}")
            return {
                'success': False,
                'error': 'Payment not found',
                'invoice_id': invoice_id
            }
        
        # Convert to dict
        columns = [desc[0] for desc in cursor.description]
        payment_dict = dict(zip(columns, payment))
        
        # Check if already completed
        if payment_dict['status'] == 'completed':
            logger.info(f"✅ Payment {payment_dict['id']} already completed")
            return {
                'success': True,
                'message': 'Payment already completed',
                'payment_id': payment_dict['id']
            }
        
        # Update payment status
        cursor.execute("""
            UPDATE payments 
            SET status = 'completed', completed_at = NOW()
            WHERE id = %s
        """, (payment_dict['id'],))
        
        # Create subscription based on plan
        plan_configs = {
            'test': {'requests': 100, 'days': 7},
            'premium': {'requests': 1500, 'days': 30}
        }
        
        if payment_dict['plan_type'] in plan_configs:
            config = plan_configs[payment_dict['plan_type']]
            db.create_subscription(
                payment_dict['user_id'],
                payment_dict['plan_type'],
                config['requests'],
                config['days']
            )
            logger.info(f"✅ Subscription created for user {payment_dict['user_id']}")
        
        # Handle referral rewards
        cursor.execute("""
            SELECT referred_by FROM users WHERE user_id = %s
        """, (payment_dict['user_id'],))
        
        referrer_result = cursor.fetchone()
        referrer_id = None
        
        if referrer_result and referrer_result[0]:
            referrer_id = referrer_result[0]
            
            # Check if referrer has active subscription
            referrer_sub = db.get_user_subscription(referrer_id)
            
            if referrer_sub:
                # Add 20 requests to existing subscription
                cursor.execute("""
                    UPDATE subscriptions 
                    SET requests_limit = requests_limit + 20 
                    WHERE id = %s
                """, (referrer_sub['id'],))
            else:
                # Create a free bonus subscription with 20 requests
                from datetime import datetime, timedelta
                start_date = datetime.now()
                end_date = start_date + timedelta(days=365)
                
                cursor.execute("""
                    INSERT INTO subscriptions 
                    (user_id, plan_type, status, requests_limit, requests_used, start_date, end_date)
                    VALUES (%s, 'referral_bonus', 'active', 20, 0, %s, %s)
                """, (referrer_id, start_date, end_date))
            
            # Update referral earnings
            cursor.execute("""
                UPDATE users 
                SET referral_earnings = referral_earnings + 0.0,
                    total_referrals = total_referrals + 1
                WHERE user_id = %s
            """, (referrer_id,))
            
            logger.info(f"✅ Referral reward given to user {referrer_id}")
        
        conn.commit()
        
        return {
            'success': True,
            'payment_id': payment_dict['id'],
            'user_id': payment_dict['user_id'],
            'referrer_id': referrer_id
        }
        
    except Exception as e:
        logger.error(f"❌ Error completing payment: {e}", exc_info=True)
        conn.rollback()
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        cursor.close()
        conn.close()


def process_webhook_data(webhook_data: Dict) -> Dict:
    """
    Process webhook data from OxaPay
    Handles different webhook formats
    """
    logger.info(f"📥 Received webhook data: {json.dumps(webhook_data, indent=2)}")
    
    # Try different possible field names
    invoice_id = (
        webhook_data.get('invoiceId') or 
        webhook_data.get('invoice_id') or 
        webhook_data.get('invoiceID') or
        webhook_data.get('id')
    )
    
    track_id = (
        webhook_data.get('trackId') or 
        webhook_data.get('track_id') or
        webhook_data.get('trackID') or
        webhook_data.get('orderId') or
        webhook_data.get('order_id')
    )
    
    status = (
        webhook_data.get('status') or 
        webhook_data.get('Status') or
        webhook_data.get('payment_status')
    )
    
    logger.info(f"📋 Extracted data:")
    logger.info(f"   Invoice ID: {invoice_id}")
    logger.info(f"   Track ID: {track_id}")
    logger.info(f"   Status: {status}")
    
    if not invoice_id and not track_id:
        logger.error("❌ No invoice_id or track_id found in webhook data")
        return {
            'success': False,
            'error': 'Missing invoice_id or track_id'
        }
    
    if status != 'paid':
        logger.warning(f"⚠️ Payment status is not 'paid': {status}")
        return {
            'success': False,
            'error': f'Payment status is {status}, not paid'
        }
    
    # Complete payment
    result = enhanced_complete_payment(invoice_id or track_id, track_id)
    
    return result


def manual_confirm_payment(invoice_id: str, track_id: Optional[str] = None):
    """Manually confirm a payment"""
    logger.info(f"🔧 Manually confirming payment...")
    logger.info(f"   Invoice ID: {invoice_id}")
    if track_id:
        logger.info(f"   Track ID: {track_id}")
    
    # Verify with OxaPay first
    if oxapay:
        logger.info("🔍 Verifying payment with OxaPay API...")
        verification = oxapay.verify_payment(invoice_id)
        
        if verification:
            if verification.get('paid'):
                logger.info(f"✅ Payment verified as PAID by OxaPay")
                logger.info(f"   Amount: {verification.get('amount')} {verification.get('currency')}")
            else:
                logger.warning(f"⚠️ Payment status: {verification.get('status')}")
                response = input("❓ Payment not marked as paid. Continue anyway? (y/n): ").strip().lower()
                if response != 'y':
                    logger.info("⏭️ Cancelled")
                    return
        else:
            logger.warning("⚠️ Could not verify with OxaPay, continuing anyway...")
    
    # Complete payment
    result = enhanced_complete_payment(invoice_id, track_id)
    
    if result.get('success'):
        logger.info("✅ Payment confirmed successfully!")
        logger.info(f"   Payment ID: {result.get('payment_id')}")
        logger.info(f"   User ID: {result.get('user_id')}")
        if result.get('referrer_id'):
            logger.info(f"   Referrer ID: {result.get('referrer_id')} (bonus given)")
    else:
        logger.error(f"❌ Failed to confirm payment: {result.get('error')}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix Payment Webhook and Manual Payment Confirmation')
    parser.add_argument('--invoice-id', type=str, help='OxaPay Invoice ID')
    parser.add_argument('--track-id', type=str, help='OxaPay Track ID')
    parser.add_argument('--webhook-data', type=str, help='Webhook JSON data (as string)')
    
    args = parser.parse_args()
    
    if args.webhook_data:
        # Process webhook data
        try:
            webhook_data = json.loads(args.webhook_data)
            result = process_webhook_data(webhook_data)
            print(json.dumps(result, indent=2))
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON: {e}")
    elif args.invoice_id or args.track_id:
        # Manual confirmation
        manual_confirm_payment(args.invoice_id or args.track_id, args.track_id)
    else:
        logger.info("Usage:")
        logger.info("  python fix_payment_webhook.py --invoice-id <invoice_id>")
        logger.info("  python fix_payment_webhook.py --track-id <track_id>")
        logger.info("  python fix_payment_webhook.py --webhook-data '{\"invoiceId\": \"...\", \"status\": \"paid\"}'")
