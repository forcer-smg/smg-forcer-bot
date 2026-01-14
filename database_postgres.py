# -*- coding: utf-8 -*-
"""
PostgreSQL database adapter for SMG-Forcer Telegram Bot
Use this instead of database.py when using PostgreSQL/Supabase
Updated: All critical methods implemented
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import json
from urllib.parse import urlparse, parse_qs, urlencode, quote_plus, unquote_plus

# Try to import psycopg2 (PostgreSQL adapter)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logging.warning("psycopg2 not installed. Install with: pip install psycopg2-binary")

logger = logging.getLogger(__name__)

# Version: 2.0 - All critical methods implemented
DB_ADAPTER_VERSION = "2.0"


class Database:
    """PostgreSQL database adapter - compatible with existing database.py interface"""
    
    def __init__(self, connection_string: str = None):
        """
        Initialize PostgreSQL connection
        
        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
                Or use environment variables: DATABASE_URL
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")
        
        # Get connection string from environment or parameter
        raw_connection_string = connection_string or os.getenv("DATABASE_URL")
        
        if not raw_connection_string:
            raise ValueError(
                "DATABASE_URL environment variable or connection_string parameter required.\n"
                "Format: postgresql://user:password@host:port/database"
            )
        
        # Parse and properly encode the connection string to handle special characters
        try:
            parsed = urlparse(raw_connection_string)
            # Reconstruct with proper encoding
            if parsed.password:
                # URL encode the password to handle special characters like !
                encoded_password = quote_plus(parsed.password)
                # Reconstruct the connection string
                self.connection_string = f"{parsed.scheme}://{parsed.username}:{encoded_password}@{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
            else:
                self.connection_string = raw_connection_string
        except Exception as e:
            logger.warning(f"Failed to parse DATABASE_URL, using as-is: {e}")
            self.connection_string = raw_connection_string
        
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        conn = psycopg2.connect(self.connection_string)
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    referral_code TEXT UNIQUE,
                    referred_by BIGINT,
                    total_referrals INTEGER DEFAULT 0,
                    referral_earnings REAL DEFAULT 0.0,
                    is_blocked INTEGER DEFAULT 0,
                    user_mode TEXT DEFAULT 'auto',
                    FOREIGN KEY (referred_by) REFERENCES users(user_id)
                )
            """)
            
            # Add user_mode column if it doesn't exist (for existing databases)
            # Use a separate transaction to avoid aborting the main transaction
            try:
                # Check if column exists first
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='users' AND column_name='user_mode'
                """)
                column_exists = cursor.fetchone() is not None
                
                if not column_exists:
                    cursor.execute("ALTER TABLE users ADD COLUMN user_mode TEXT DEFAULT 'auto'")
                    conn.commit()
            except Exception as e:
                # Rollback on any error to clear the transaction state
                conn.rollback()
                # Check if it's a duplicate column error
                error_str = str(e).lower()
                if 'already exists' in error_str or 'duplicate' in error_str:
                    logger.debug("user_mode column already exists")
                else:
                    logger.warning(f"Could not add user_mode column: {e}")
            
            # Subscriptions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
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
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
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
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date DATE,
                    message_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE(user_id, date)
                )
            """)
            
            # Referral transactions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_transactions (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT,
                    referred_id BIGINT,
                    amount REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                    FOREIGN KEY (referred_id) REFERENCES users(user_id)
                )
            """)
            
            # Admin users
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Document templates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_templates (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT,
                    description TEXT,
                    template_data JSONB,
                    file_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_global BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_usage_user_date ON daily_usage(user_id, date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_templates_user_id ON document_templates(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_templates_type ON document_templates(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_templates_category ON document_templates(category)")
            
            conn.commit()
            logger.info("PostgreSQL database initialized successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error initializing database: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    # User management methods (same interface as SQLite version)
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
        """Get or create user"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                # Generate referral code
                referral_code = f"SMG{user_id}{hash(str(user_id)) % 10000}"
                
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, referral_code)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, username, first_name, referral_code))
                
                conn.commit()
                
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user = cursor.fetchone()
            
            return dict(user) if user else None
        finally:
            cursor.close()
            conn.close()
    
    def update_user(self, user_id: int, **kwargs):
        """Update user information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            updates = ", ".join([f"{k} = %s" for k in kwargs.keys()])
            values = list(kwargs.values()) + [user_id]
            
            cursor.execute(f"UPDATE users SET {updates} WHERE user_id = %s", values)
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def get_user_mode(self, user_id: int) -> str:
        """Get user's current mode (plan, ask, debug, auto)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT user_mode FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if row and row.get('user_mode'):
                return row['user_mode']
            return 'auto'  # Default mode
        except Exception as e:
            # If column doesn't exist, return default
            error_str = str(e).lower()
            if 'column' in error_str and 'user_mode' in error_str:
                logger.debug("user_mode column doesn't exist yet, returning default")
            else:
                logger.warning(f"Error getting user mode: {e}")
            return 'auto'
        finally:
            cursor.close()
            conn.close()
    
    def set_user_mode(self, user_id: int, mode: str) -> bool:
        """Set user's mode (plan, ask, debug, auto)"""
        if mode not in ['plan', 'ask', 'debug', 'auto']:
            logger.warning(f"Invalid mode: {mode}, defaulting to 'auto'")
            mode = 'auto'
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE users SET user_mode = %s WHERE user_id = %s", (mode, user_id))
            conn.commit()
            success = cursor.rowcount > 0
            return success
        except Exception as e:
            error_str = str(e).lower()
            if 'column' in error_str and 'user_mode' in error_str:
                # Column doesn't exist, try to add it
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN user_mode TEXT DEFAULT 'auto'")
                    conn.commit()
                    # Retry the update
                    cursor.execute("UPDATE users SET user_mode = %s WHERE user_id = %s", (mode, user_id))
                    conn.commit()
                    return cursor.rowcount > 0
                except Exception as e2:
                    logger.error(f"Error adding user_mode column: {e2}")
                    conn.rollback()
                    return False
            else:
                logger.error(f"Error setting user mode: {e}")
                conn.rollback()
                return False
        finally:
            cursor.close()
            conn.close()
    
    # Note: All other methods need to be converted from SQLite to PostgreSQL syntax
    # This is a template - you'll need to convert datetime functions and syntax
    # For now, keeping the same interface but you'll need to implement all methods
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """Get active subscription for user"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Expire old subscriptions
            cursor.execute("""
                UPDATE subscriptions 
                SET status = 'expired' 
                WHERE user_id = %s AND status = 'active' 
                AND end_date <= NOW()
            """, (user_id,))
            conn.commit()
            
            # Get paid subscription first
            cursor.execute("""
                SELECT * FROM subscriptions 
                WHERE user_id = %s AND status = 'active' 
                AND end_date > NOW()
                AND plan_type != 'referral_bonus'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            
            sub = cursor.fetchone()
            
            # If no paid subscription, get referral bonus
            if not sub:
                cursor.execute("""
                    SELECT * FROM subscriptions 
                    WHERE user_id = %s AND status = 'active' 
                    AND end_date > NOW()
                    AND plan_type = 'referral_bonus'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                sub = cursor.fetchone()
            
            return dict(sub) if sub else None
        finally:
            cursor.close()
            conn.close()
    
    # Add other methods as needed - convert SQLite syntax to PostgreSQL
    # Key differences:
    # - SQLite: ? placeholders → PostgreSQL: %s placeholders
    # - SQLite: datetime('now') → PostgreSQL: NOW()
    # - SQLite: INTEGER PRIMARY KEY → PostgreSQL: SERIAL PRIMARY KEY
    # - SQLite: sqlite3.Row → PostgreSQL: RealDictCursor
    
    def get_all_user_subscriptions(self, user_id: int) -> List[Dict]:
        """Get all active subscriptions for user (including referral bonuses)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT * FROM subscriptions 
                WHERE user_id = %s AND status = 'active' 
                AND end_date > NOW()
                ORDER BY 
                    CASE WHEN plan_type = 'referral_bonus' THEN 1 ELSE 0 END,
                    created_at DESC
            """, (user_id,))
            
            subs = [dict(row) for row in cursor.fetchall()]
            return subs
        finally:
            cursor.close()
            conn.close()
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return result is not None
        finally:
            cursor.close()
            conn.close()
    
    def add_admin(self, user_id: int):
        """Add admin user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO admins (user_id) 
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def get_user_usage_stats(self, user_id: int) -> Dict:
        """Get user usage statistics"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Check if admin
            is_admin_user = self.is_admin(user_id)
            
            # Get subscription (this will also expire old subscriptions)
            sub = self.get_user_subscription(user_id)
            
            # Get lifetime usage for free tier (not daily - one-time 3 requests)
            cursor.execute("""
                SELECT SUM(message_count) as total_usage FROM daily_usage 
                WHERE user_id = %s
            """, (user_id,))
            
            usage_row = cursor.fetchone()
            total_usage = usage_row['total_usage'] if usage_row and usage_row['total_usage'] else 0
            
            # For paid users, still show today's usage
            today = datetime.now().date()
            cursor.execute("""
                SELECT message_count FROM daily_usage 
                WHERE user_id = %s AND date = %s
            """, (user_id, today))
            today_row = cursor.fetchone()
            today_count = today_row['message_count'] if today_row else 0
            
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
                    # Get lifetime usage
                    cursor.execute("""
                        SELECT SUM(message_count) as total_usage FROM daily_usage 
                        WHERE user_id = %s
                    """, (user_id,))
                    usage_row = cursor.fetchone()
                    total_usage = usage_row['total_usage'] if usage_row and usage_row['total_usage'] else 0
                    
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
        finally:
            cursor.close()
            conn.close()
    
    def create_subscription(self, user_id: int, plan_type: str, requests_limit: int, 
                          duration_days: int) -> int:
        """Create new subscription"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Deactivate old subscriptions
            cursor.execute("""
                UPDATE subscriptions SET status = 'expired' 
                WHERE user_id = %s AND status = 'active'
            """, (user_id,))
            
            # Create new subscription
            start_date = datetime.now()
            end_date = start_date + timedelta(days=duration_days)
            
            cursor.execute("""
                INSERT INTO subscriptions 
                (user_id, plan_type, status, requests_limit, start_date, end_date)
                VALUES (%s, %s, 'active', %s, %s, %s)
                RETURNING id
            """, (user_id, plan_type, requests_limit, start_date, end_date))
            
            sub_id = cursor.fetchone()[0]
            conn.commit()
            return sub_id
        finally:
            cursor.close()
            conn.close()
    
    def create_temporary_subscription(self, user_id: int, requests_limit: int, 
                                    duration_minutes: int = None, duration_days: int = None) -> Optional[int]:
        """Create temporary subscription (for admin manual upgrades)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Ensure user exists in users table
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                # User doesn't exist, create a basic user record
                cursor.execute("""
                    INSERT INTO users (user_id, first_name, created_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, f"User {user_id}"))
                conn.commit()
            
            # Deactivate old subscriptions
            cursor.execute("""
                UPDATE subscriptions SET status = 'expired' 
                WHERE user_id = %s AND status = 'active'
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
            
            cursor.execute("""
                INSERT INTO subscriptions 
                (user_id, plan_type, status, requests_limit, start_date, end_date)
                VALUES (%s, %s, 'active', %s, %s, %s)
                RETURNING id
            """, (user_id, plan_type, requests_limit, start_date, end_date))
            
            sub_id = cursor.fetchone()[0]
            conn.commit()
            return sub_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating temporary subscription: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def create_payment(self, user_id: int, plan_type: str, amount: float, 
                      oxapay_invoice_id: str) -> int:
        """Create payment record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            payment_id = f"SMG{user_id}{int(datetime.now().timestamp())}"
            
            cursor.execute("""
                INSERT INTO payments 
                (user_id, plan_type, amount, payment_id, oxapay_invoice_id, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                RETURNING id
            """, (user_id, plan_type, amount, payment_id, oxapay_invoice_id))
            
            pay_id = cursor.fetchone()[0]
            conn.commit()
            return pay_id
        finally:
            cursor.close()
            conn.close()
    
    def complete_payment(self, oxapay_invoice_id: str):
        """Mark payment as completed and activate subscription"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT * FROM payments 
                WHERE oxapay_invoice_id = %s AND status = 'pending'
            """, (oxapay_invoice_id,))
            
            payment = cursor.fetchone()
            if not payment:
                return False
            
            payment = dict(payment)
            
            # Update payment status
            cursor.execute("""
                UPDATE payments 
                SET status = 'completed', completed_at = NOW()
                WHERE id = %s
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
                SELECT referred_by FROM users WHERE user_id = %s
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
                        WHERE id = %s
                    """, (referrer_sub['id'],))
                else:
                    # Create a free bonus subscription with 20 requests
                    start_date = datetime.now()
                    end_date = start_date + timedelta(days=365)  # 1 year validity
                    
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
                
                # Record referral transaction
                cursor.execute("""
                    INSERT INTO referral_transactions 
                    (referrer_id, referred_id, amount)
                    VALUES (%s, %s, %s)
                """, (referrer_id, payment['user_id'], 0.0))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error completing payment: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_referral_code(self, user_id: int) -> Optional[str]:
        """Get user's referral code"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT referral_code FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return result['referral_code'] if result else None
        finally:
            cursor.close()
            conn.close()
    
    def use_referral_code(self, user_id: int, referral_code: str) -> bool:
        """Use referral code (when new user signs up) - NO REWARD YET, only links them"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Find referrer
            cursor.execute("SELECT user_id FROM users WHERE referral_code = %s", (referral_code,))
            referrer = cursor.fetchone()
            
            if not referrer or referrer['user_id'] == user_id:
                return False
            
            referrer_id = referrer['user_id']
            
            # Check if already referred
            cursor.execute("SELECT referred_by FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            
            if user and user['referred_by']:
                return False  # Already used a referral
            
            # Update user - link them to referrer (reward comes when they buy)
            cursor.execute("""
                UPDATE users 
                SET referred_by = %s 
                WHERE user_id = %s
            """, (referrer_id, user_id))
            
            # Don't update referral count yet - only when they actually purchase
            # The reward will be given in complete_payment()
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error using referral code: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def get_referral_stats(self, user_id: int) -> Dict:
        """Get referral statistics"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT total_referrals, referral_earnings 
                FROM users WHERE user_id = %s
            """, (user_id,))
            
            result = cursor.fetchone()
            
            return {
                'total_referrals': result['total_referrals'] if result else 0,
                'earnings': result['referral_earnings'] if result else 0.0
            }
        finally:
            cursor.close()
            conn.close()
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all users (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT u.*, 
                       (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id = u.user_id) as sub_count,
                       (SELECT status FROM subscriptions s WHERE s.user_id = u.user_id AND s.status = 'active' LIMIT 1) as current_status
                FROM users u
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            users = [dict(row) for row in cursor.fetchall()]
            return users
        finally:
            cursor.close()
            conn.close()
    
    def get_all_subscriptions(self, limit: int = 100) -> List[Dict]:
        """Get all subscriptions (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT s.*, u.username, u.first_name
                FROM subscriptions s
                JOIN users u ON s.user_id = u.user_id
                ORDER BY s.created_at DESC
                LIMIT %s
            """, (limit,))
            
            subs = [dict(row) for row in cursor.fetchall()]
            return subs
        finally:
            cursor.close()
            conn.close()
    
    def get_all_payments(self, limit: int = 100) -> List[Dict]:
        """Get all payments (admin function)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Use LEFT JOIN to handle payments without users
            cursor.execute("""
                SELECT p.*, u.username, u.first_name
                FROM payments p
                LEFT JOIN users u ON p.user_id = u.user_id
                ORDER BY p.created_at DESC
                LIMIT %s
            """, (limit,))
            
            payments = [dict(row) for row in cursor.fetchall()]
            return payments
        finally:
            cursor.close()
            conn.close()
    
    def get_dashboard_stats(self) -> Dict:
        """Get dashboard statistics"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Total users
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            # Active subscriptions
            cursor.execute("""
                SELECT COUNT(*) as count FROM subscriptions 
                WHERE status = 'active' AND end_date > NOW()
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
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            today_users = cursor.fetchone()['count']
            
            return {
                'total_users': total_users,
                'active_subscriptions': active_subs,
                'total_revenue': revenue,
                'today_new_users': today_users
            }
        finally:
            cursor.close()
            conn.close()
    
    def block_user(self, user_id: int) -> bool:
        """Block a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = %s", (user_id,))
            conn.commit()
            success = cursor.rowcount > 0
            return success
        finally:
            cursor.close()
            conn.close()
    
    def unblock_user(self, user_id: int) -> bool:
        """Unblock a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = %s", (user_id,))
            conn.commit()
            success = cursor.rowcount > 0
            return success
        finally:
            cursor.close()
            conn.close()
    
    def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT is_blocked FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return bool(result and result['is_blocked']) if result else False
        finally:
            cursor.close()
            conn.close()
    
    def downgrade_user(self, user_id: int) -> bool:
        """Downgrade user by expiring all active subscriptions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE subscriptions 
                SET status = 'expired' 
                WHERE user_id = %s AND status = 'active'
            """, (user_id,))
            conn.commit()
            success = cursor.rowcount >= 0  # Success even if no subscriptions to expire
            return success
        except Exception as e:
            conn.rollback()
            logger.error(f"Error downgrading user: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def increment_usage(self, user_id: int) -> bool:
        """Increment usage count and check limits (admins have unlimited access but usage is tracked)"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
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
                    WHERE id = %s
                """, (sub['id'],))
            else:
                # Free tier - ONE-TIME 3 requests (no daily refresh) unless admin
                # Check lifetime usage, not daily
                cursor.execute("""
                    SELECT SUM(message_count) as total_usage FROM daily_usage 
                    WHERE user_id = %s
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
                    VALUES (%s, %s, 1)
                    ON CONFLICT (user_id, date) 
                    DO UPDATE SET message_count = daily_usage.message_count + 1
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
            cursor.close()
            conn.close()

