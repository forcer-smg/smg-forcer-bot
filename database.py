# -*- coding: utf-8 -*-
"""
Database management for SMG-Forcer Telegram Bot
Handles users, subscriptions, payments, and referrals
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import json

DB_FILE = "smg_forcer.db"
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                total_referrals INTEGER DEFAULT 0,
                referral_earnings REAL DEFAULT 0.0,
                is_blocked INTEGER DEFAULT 0,
                FOREIGN KEY (referred_by) REFERENCES users(user_id)
            )
        """)
        
        # Add is_blocked column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Add user_mode column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_mode TEXT DEFAULT 'auto'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Subscriptions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                status TEXT,
                requests_used INTEGER DEFAULT 0,
                requests_limit INTEGER,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Payments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                amount REAL,
                currency TEXT DEFAULT 'USD',
                payment_id TEXT UNIQUE,
                oxapay_invoice_id TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Daily usage tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date DATE,
                message_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, date)
            )
        """)
        
        # Referral transactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referral_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        """)
        
        # Admin users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    # User management
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
        """Get or create user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            # Generate referral code
            referral_code = f"SMG{user_id}{hash(str(user_id)) % 10000}"
            
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, referral_code)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, referral_code))
            
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
        
        conn.close()
        return dict(user) if user else None
    
    def update_user(self, user_id: int, **kwargs):
        """Update user information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        cursor.execute(f"UPDATE users SET {updates} WHERE user_id = ?", values)
        conn.commit()
        conn.close()
    
    def get_user_mode(self, user_id: int) -> str:
        """Get user's current mode (plan, ask, debug, auto)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_mode FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row['user_mode']:
            return row['user_mode']
        return 'auto'  # Default mode
    
    def set_user_mode(self, user_id: int, mode: str) -> bool:
        """Set user's mode (plan, ask, debug, auto)"""
        if mode not in ['plan', 'ask', 'debug', 'auto']:
            logger.warning(f"Invalid mode: {mode}, defaulting to 'auto'")
            mode = 'auto'
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET user_mode = ? WHERE user_id = ?", (mode, user_id))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    # Subscription management
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Get active subscription for user (prioritizes paid plans over referral bonus)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # First, expire any subscriptions that have passed their end_date
        # Use datetime comparison - SQLite datetime('now') returns local time
        # Compare as strings since we're storing in 'YYYY-MM-DD HH:MM:SS' format
        cursor.execute("""
            UPDATE subscriptions 
            SET status = 'expired' 
            WHERE user_id = ? AND status = 'active' 
            AND datetime(end_date) <= datetime('now', 'localtime')
        """, (user_id,))
        conn.commit()
        
        # Get paid subscription first (including temp subscriptions)
        # Compare dates properly - use 'localtime' modifier to match stored timezone
        cursor.execute("""
            SELECT * FROM subscriptions 
            WHERE user_id = ? AND status = 'active' 
            AND datetime(end_date) > datetime('now', 'localtime')
            AND plan_type != 'referral_bonus'
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        
        sub = cursor.fetchone()
        
        # If no paid subscription, get referral bonus
        if not sub:
            cursor.execute("""
                SELECT * FROM subscriptions 
                WHERE user_id = ? AND status = 'active' 
                AND datetime(end_date) > datetime('now', 'localtime')
                AND plan_type = 'referral_bonus'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            sub = cursor.fetchone()
        
        conn.close()
        return dict(sub) if sub else None
    
    def get_all_user_subscriptions(self, user_id: int) -> List[Dict]:
        """Get all active subscriptions for user (including referral bonuses)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM subscriptions 
            WHERE user_id = ? AND status = 'active' 
            AND datetime(end_date) > datetime('now', 'localtime')
            ORDER BY 
                CASE WHEN plan_type = 'referral_bonus' THEN 1 ELSE 0 END,
                created_at DESC
        """, (user_id,))
        
        subs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return subs
    
    def create_subscription(self, user_id: int, plan_type: str, requests_limit: int, 
                          duration_days: int) -> int:
        """Create new subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Deactivate old subscriptions
        cursor.execute("""
            UPDATE subscriptions SET status = 'expired' 
            WHERE user_id = ? AND status = 'active'
        """, (user_id,))
        
        # Create new subscription
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)
        
        # Format dates as strings for SQLite (without microseconds for consistency)
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            INSERT INTO subscriptions 
            (user_id, plan_type, status, requests_limit, start_date, end_date)
            VALUES (?, ?, 'active', ?, ?, ?)
        """, (user_id, plan_type, requests_limit, start_date_str, end_date_str))
        
        sub_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return sub_id
    
    def create_temporary_subscription(self, user_id: int, requests_limit: int, 
                                    duration_minutes: int = None, duration_days: int = None) -> Optional[int]:
        """Create temporary subscription (for admin manual upgrades)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Ensure user exists in users table
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                # User doesn't exist, create a basic user record
                cursor.execute("""
                    INSERT OR IGNORE INTO users (user_id, first_name, created_at)
                    VALUES (?, ?, ?)
                """, (user_id, f"User {user_id}", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
            
            # Deactivate old subscriptions
            cursor.execute("""
                UPDATE subscriptions SET status = 'expired' 
                WHERE user_id = ? AND status = 'active'
            """, (user_id,))
            
            # Create new temporary subscription
            start_date = datetime.now()
            if duration_minutes:
                end_date = start_date + timedelta(minutes=duration_minutes)
                plan_type = f"temp_{duration_minutes}min"
            elif duration_days:
                end_date = start_date + timedelta(days=duration_days)
                plan_type = f"temp_{duration_days}days"
            else:
                # Default to 1 day if nothing specified
                end_date = start_date + timedelta(days=1)
                plan_type = "temp_1day"
            
            # Format dates as strings for SQLite (without microseconds for consistency)
            start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
            end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                INSERT INTO subscriptions 
                (user_id, plan_type, status, requests_limit, start_date, end_date)
                VALUES (?, ?, 'active', ?, ?, ?)
            """, (user_id, plan_type, requests_limit, start_date_str, end_date_str))
            
            sub_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            if sub_id:
                return sub_id
            else:
                return None
        except Exception as e:
            conn.rollback()
            conn.close()
            print(f"Error creating temporary subscription: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def increment_usage(self, user_id: int) -> bool:
        """Increment usage count and check limits (admins have unlimited access but usage is tracked)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if user is admin - admins have unlimited access but usage is still tracked
            is_admin_user = self.is_admin(user_id)
            
            # Get subscription
            sub = self.get_user_subscription(user_id)
            
            if sub:
                # Paid subscription - check request limit (unless admin)
                if not is_admin_user and sub['requests_used'] >= sub['requests_limit']:
                    return False
                
                # Track usage for admins too
                cursor.execute("""
                    UPDATE subscriptions 
                    SET requests_used = requests_used + 1 
                    WHERE id = ?
                """, (sub['id'],))
            else:
                # Free tier - ONE-TIME 3 requests (no daily refresh) unless admin
                # Check lifetime usage, not daily
                cursor.execute("""
                    SELECT SUM(message_count) as total_usage FROM daily_usage 
                    WHERE user_id = ?
                """, (user_id,))
                
                usage = cursor.fetchone()
                total_usage = usage['total_usage'] if usage and usage['total_usage'] else 0
                
                # Check limit before incrementing (unless admin) - 3 requests lifetime
                if not is_admin_user and total_usage >= 3:
                    return False
                
                # Track usage (use today's date for tracking, but count is lifetime)
                today = datetime.now().date()
                cursor.execute("""
                    INSERT INTO daily_usage (user_id, date, message_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, date) 
                    DO UPDATE SET message_count = message_count + 1
                """, (user_id, today))
            
            conn.commit()
            # Log with more detail about user type
            if is_admin_user:
                user_type = "admin"
            elif sub:
                user_type = f"subscription ({sub.get('plan_type', 'unknown')})"
            else:
                user_type = "free tier"
            logger.info(f"Usage incremented for user {user_id} (type: {user_type})")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error incrementing usage for user {user_id}: {e}", exc_info=True)
            return False
        finally:
            conn.close()
    
    def get_user_usage_stats(self, user_id: int) -> Dict:
        """Get user usage statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if admin
        is_admin_user = self.is_admin(user_id)
        
        # Get subscription (this will also expire old subscriptions)
        sub = self.get_user_subscription(user_id)
        
        # Get lifetime usage for free tier (not daily - one-time 3 requests)
        cursor.execute("""
            SELECT SUM(message_count) as total_usage FROM daily_usage 
            WHERE user_id = ?
        """, (user_id,))
        
        usage_row = cursor.fetchone()
        total_usage = usage_row['total_usage'] if usage_row and usage_row['total_usage'] else 0
        
        # For paid users, still show today's usage
        today = datetime.now().date()
        cursor.execute("""
            SELECT message_count FROM daily_usage 
            WHERE user_id = ? AND date = ?
        """, (user_id, today))
        today_row = cursor.fetchone()
        today_count = today_row['message_count'] if today_row else 0
        
        conn.close()
        
        if sub:
            # Get all subscriptions to combine limits if user has multiple
            all_subs = self.get_all_user_subscriptions(user_id)
            total_limit = sum(s['requests_limit'] for s in all_subs)
            total_used = sum(s['requests_used'] for s in all_subs)
            
            # Format plan type for display
            plan_type_display = sub['plan_type']
            if plan_type_display.startswith('temp_'):
                # Format temp plans nicely
                if 'min' in plan_type_display:
                    plan_type_display = f"Temp ({plan_type_display.split('_')[1]})"
                elif 'days' in plan_type_display:
                    plan_type_display = f"Temp ({plan_type_display.split('_')[1]})"
            
            # Admins have unlimited access, but show subscription details if they have a temp subscription
            if is_admin_user:
                # If admin has a temp subscription, show it (but still allow unlimited usage)
                if plan_type_display.startswith('Temp'):
                    return {
                        'plan_type': plan_type_display,
                        'status': sub['status'],
                        'requests_used': total_used,
                        'requests_limit': total_limit,  # Show actual limit for temp subscriptions
                        'remaining': total_limit - total_used,
                        'end_date': sub['end_date'],
                        'today_usage': today_count,
                        'is_premium': True,
                        'is_admin': True,
                        'has_referral_bonus': any(s['plan_type'] == 'referral_bonus' for s in all_subs)
                    }
                else:
                    # Regular admin without temp subscription - unlimited
                    return {
                        'plan_type': plan_type_display,
                        'status': sub['status'],
                        'requests_used': total_used,
                        'requests_limit': float('inf'),  # Unlimited for admins
                        'remaining': float('inf'),  # Unlimited for admins
                        'end_date': sub['end_date'],
                        'today_usage': today_count,
                        'is_premium': True,
                        'is_admin': True,
                        'has_referral_bonus': any(s['plan_type'] == 'referral_bonus' for s in all_subs)
                    }
            else:
                return {
                    'plan_type': plan_type_display,
                    'status': sub['status'],
                    'requests_used': total_used,
                    'requests_limit': total_limit,
                    'remaining': total_limit - total_used,
                    'end_date': sub['end_date'],
                    'today_usage': today_count,
                    'is_premium': True,
                    'is_admin': False,
                    'has_referral_bonus': any(s['plan_type'] == 'referral_bonus' for s in all_subs)
                }
        else:
            # Admins have unlimited even without subscription
            if is_admin_user:
                return {
                    'plan_type': 'admin',
                    'status': 'active',
                    'requests_used': today_count,
                    'requests_limit': float('inf'),  # Unlimited for admins
                    'remaining': float('inf'),  # Unlimited for admins
                    'today_usage': today_count,
                    'is_premium': True,
                    'is_admin': True
                }
            else:
                # Free tier: 3 lifetime requests (no daily refresh)
                return {
                    'plan_type': 'free',
                    'status': 'active',
                    'requests_used': total_usage,
                    'requests_limit': 3,
                    'remaining': max(0, 3 - total_usage),
                    'today_usage': total_usage,  # Show lifetime usage
                    'is_premium': False,
                    'is_admin': False
                }
    
    # Payment management
    def create_payment(self, user_id: int, plan_type: str, amount: float, 
                      oxapay_invoice_id: str) -> int:
        """Create payment record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        payment_id = f"SMG{user_id}{int(datetime.now().timestamp())}"
        
        cursor.execute("""
            INSERT INTO payments 
            (user_id, plan_type, amount, payment_id, oxapay_invoice_id, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (user_id, plan_type, amount, payment_id, oxapay_invoice_id))
        
        pay_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return pay_id
    
    def complete_payment(self, oxapay_invoice_id: str):
        """Mark payment as completed and activate subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM payments 
            WHERE oxapay_invoice_id = ? AND status = 'pending'
        """, (oxapay_invoice_id,))
        
        payment = cursor.fetchone()
        if not payment:
            conn.close()
            return False
        
        payment = dict(payment)
        
        # Update payment status
        cursor.execute("""
            UPDATE payments 
            SET status = 'completed', completed_at = datetime('now')
            WHERE id = ?
        """, (payment['id'],))
        
        # Create subscription based on plan
        plan_configs = {
            'test': {'requests': 100, 'days': 7},
            'premium': {'requests': 1500, 'days': 30}
        }
        
        if payment['plan_type'] in plan_configs:
            config = plan_configs[payment['plan_type']]
            self.create_subscription(
                payment['user_id'],
                payment['plan_type'],
                config['requests'],
                config['days']
            )
        
        # Referral reward: Give referrer 20 free requests
        cursor.execute("""
            SELECT referred_by FROM users WHERE user_id = ?
        """, (payment['user_id'],))
        
        referrer_result = cursor.fetchone()
        if referrer_result and referrer_result['referred_by']:
            referrer_id = referrer_result['referred_by']
            
            # Check if referrer has active subscription
            referrer_sub = self.get_user_subscription(referrer_id)
            
            if referrer_sub:
                # Add 20 requests to existing subscription
                cursor.execute("""
                    UPDATE subscriptions 
                    SET requests_limit = requests_limit + 20 
                    WHERE id = ?
                """, (referrer_sub['id'],))
            else:
                # Create a free bonus subscription with 20 requests
                from datetime import datetime, timedelta
                start_date = datetime.now()
                end_date = start_date + timedelta(days=365)  # 1 year validity
                
                cursor.execute("""
                    INSERT INTO subscriptions 
                    (user_id, plan_type, status, requests_limit, requests_used, start_date, end_date)
                    VALUES (?, 'referral_bonus', 'active', 20, 0, ?, ?)
                """, (referrer_id, start_date, end_date))
            
            # Update referral earnings
            cursor.execute("""
                UPDATE users 
                SET referral_earnings = referral_earnings + 0.0,
                    total_referrals = total_referrals + 1
                WHERE user_id = ?
            """, (referrer_id,))
            
            # Record referral transaction
            cursor.execute("""
                INSERT INTO referral_transactions 
                (referrer_id, referred_id, amount)
                VALUES (?, ?, 20)
            """, (referrer_id, payment['user_id']))
            
            # Store referrer info for notification (will be handled separately)
            referrer_notified = referrer_id
        
        conn.commit()
        conn.close()
        
        # Return referrer ID if bonus was given
        if 'referrer_notified' in locals():
            return referrer_id
        return True
    
    # Referral system
    def get_referral_code(self, user_id: int) -> Optional[str]:
        """Get user's referral code"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result['referral_code'] if result else None
    
    def use_referral_code(self, user_id: int, referral_code: str) -> bool:
        """Use referral code (when new user signs up) - NO REWARD YET, only links them"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Find referrer
        cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
        referrer = cursor.fetchone()
        
        if not referrer or referrer['user_id'] == user_id:
            conn.close()
            return False
        
        referrer_id = referrer['user_id']
        
        # Check if already referred
        cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user and user['referred_by']:
            conn.close()
            return False  # Already used a referral
        
        # Update user - link them to referrer (reward comes when they buy)
        cursor.execute("""
            UPDATE users 
            SET referred_by = ? 
            WHERE user_id = ?
        """, (referrer_id, user_id))
        
        # Don't update referral count yet - only when they actually purchase
        # The reward will be given in complete_payment()
        
        conn.commit()
        conn.close()
        return True
    
    def get_referral_stats(self, user_id: int) -> Dict:
        """Get referral statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT total_referrals, referral_earnings 
            FROM users WHERE user_id = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            'total_referrals': result['total_referrals'] if result else 0,
            'earnings': result['referral_earnings'] if result else 0.0
        }
    
    # Admin functions
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def add_admin(self, user_id: int):
        """Add admin user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT u.*, 
                   (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id = u.user_id) as sub_count,
                   (SELECT status FROM subscriptions s WHERE s.user_id = u.user_id AND s.status = 'active' LIMIT 1) as current_status
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return users
    
    def get_all_subscriptions(self, limit: int = 100) -> List[Dict]:
        """Get all subscriptions (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.*, u.username, u.first_name
            FROM subscriptions s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (limit,))
        
        subs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return subs
    
    def get_all_payments(self, limit: int = 100) -> List[Dict]:
        """Get all payments (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Use LEFT JOIN to handle payments without users
        cursor.execute("""
            SELECT p.*, u.username, u.first_name
            FROM payments p
            LEFT JOIN users u ON p.user_id = u.user_id
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (limit,))
        
        payments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return payments
    
    def get_dashboard_stats(self) -> Dict:
        """Get dashboard statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_users = cursor.fetchone()['count']
        
        # Active subscriptions
        cursor.execute("""
            SELECT COUNT(*) as count FROM subscriptions 
            WHERE status = 'active' AND datetime(end_date) > datetime('now', 'localtime')
        """)
        active_subs = cursor.fetchone()['count']
        
        # Total revenue
        cursor.execute("""
            SELECT SUM(amount) as total FROM payments 
            WHERE status = 'completed'
        """)
        revenue = cursor.fetchone()['total'] or 0.0
        
        # Today's new users
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE DATE(created_at) = DATE('now')
        """)
        today_users = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'total_users': total_users,
            'active_subscriptions': active_subs,
            'total_revenue': revenue,
            'today_new_users': today_users
        }
    
    def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return bool(result and result['is_blocked']) if result else False
    
    def block_user(self, user_id: int) -> bool:
        """Block a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def unblock_user(self, user_id: int) -> bool:
        """Unblock a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def downgrade_user(self, user_id: int) -> bool:
        """Downgrade user by expiring all active subscriptions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subscriptions 
            SET status = 'expired' 
            WHERE user_id = ? AND status = 'active'
        """, (user_id,))
        conn.commit()
        success = cursor.rowcount >= 0  # Success even if no subscriptions to expire
        conn.close()
        return success

