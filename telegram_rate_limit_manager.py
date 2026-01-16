# -*- coding: utf-8 -*-
"""
Telegram Rate Limit Manager - Intelligently pause/resume updates based on rate limits
Tracks 429 errors and automatically pauses sending updates when rate limited
"""

import time
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TelegramRateLimitManager:
    """Manage Telegram API rate limits with intelligent pause/resume"""
    
    def __init__(self):
        """Initialize rate limit manager"""
        # Track rate limit events per chat
        self.rate_limit_events: Dict[int, list] = {}  # chat_id -> list of timestamps
        # Track if paused per chat
        self.paused_chats: Dict[int, bool] = {}  # chat_id -> is_paused
        # Track pause end time per chat
        self.pause_until: Dict[int, float] = {}  # chat_id -> timestamp when pause ends
        # Track consecutive 429 errors
        self.consecutive_429s: Dict[int, int] = {}  # chat_id -> count
        # Maximum consecutive 429s before pausing
        self.max_consecutive_429s = 3
        # Default pause duration (seconds)
        self.default_pause_duration = 60  # 1 minute
        # Maximum pause duration
        self.max_pause_duration = 300  # 5 minutes
    
    def record_rate_limit(self, chat_id: int, retry_after: Optional[int] = None):
        """
        Record a rate limit event (429 error)
        
        Args:
            chat_id: Telegram chat ID
            retry_after: Retry-After header value (seconds)
        """
        current_time = time.time()
        
        # Initialize if needed
        if chat_id not in self.rate_limit_events:
            self.rate_limit_events[chat_id] = []
            self.consecutive_429s[chat_id] = 0
        
        # Record the event
        self.rate_limit_events[chat_id].append(current_time)
        self.consecutive_429s[chat_id] += 1
        
        # Clean old events (keep last hour)
        hour_ago = current_time - 3600
        self.rate_limit_events[chat_id] = [
            ts for ts in self.rate_limit_events[chat_id] if ts > hour_ago
        ]
        
        # Determine pause duration
        if retry_after:
            pause_duration = min(retry_after + 10, self.max_pause_duration)  # Add 10s buffer
        else:
            # Exponential backoff based on consecutive 429s
            pause_duration = min(
                self.default_pause_duration * (2 ** min(self.consecutive_429s[chat_id] - 1, 3)),
                self.max_pause_duration
            )
        
        # Pause if we've hit too many consecutive 429s
        if self.consecutive_429s[chat_id] >= self.max_consecutive_429s:
            self.pause_chat(chat_id, pause_duration)
            logger.warning(f"[RATE-LIMIT] Pausing updates for chat {chat_id} for {pause_duration}s (consecutive 429s: {self.consecutive_429s[chat_id]})")
        else:
            logger.warning(f"[RATE-LIMIT] Rate limit hit for chat {chat_id} (consecutive: {self.consecutive_429s[chat_id]}/{self.max_consecutive_429s})")
    
    def pause_chat(self, chat_id: int, duration: int):
        """
        Pause sending updates for a chat
        
        Args:
            chat_id: Telegram chat ID
            duration: Pause duration in seconds
        """
        self.paused_chats[chat_id] = True
        self.pause_until[chat_id] = time.time() + duration
        logger.info(f"[RATE-LIMIT] Paused chat {chat_id} until {datetime.fromtimestamp(self.pause_until[chat_id]).strftime('%H:%M:%S')}")
    
    def resume_chat(self, chat_id: int):
        """Resume sending updates for a chat"""
        if chat_id in self.paused_chats:
            self.paused_chats[chat_id] = False
            self.consecutive_429s[chat_id] = 0  # Reset counter on resume
            logger.info(f"[RATE-LIMIT] Resumed chat {chat_id}")
    
    def is_paused(self, chat_id: int) -> bool:
        """
        Check if chat is currently paused
        
        Args:
            chat_id: Telegram chat ID
        
        Returns:
            True if paused, False otherwise
        """
        if chat_id not in self.paused_chats:
            return False
        
        if not self.paused_chats[chat_id]:
            return False
        
        # Check if pause period has expired
        if chat_id in self.pause_until:
            if time.time() >= self.pause_until[chat_id]:
                # Pause expired, resume
                self.resume_chat(chat_id)
                return False
        
        return True
    
    def should_send_update(self, chat_id: int) -> bool:
        """
        Check if we should send an update (not rate limited)
        
        Args:
            chat_id: Telegram chat ID
        
        Returns:
            True if we should send, False if paused
        """
        if self.is_paused(chat_id):
            logger.debug(f"[RATE-LIMIT] Skipping update for chat {chat_id} (paused)")
            return False
        
        return True
    
    def record_successful_send(self, chat_id: int):
        """
        Record a successful message send (resets consecutive 429 counter)
        
        Args:
            chat_id: Telegram chat ID
        """
        if chat_id in self.consecutive_429s:
            if self.consecutive_429s[chat_id] > 0:
                logger.debug(f"[RATE-LIMIT] Successful send for chat {chat_id}, resetting 429 counter")
            self.consecutive_429s[chat_id] = 0
    
    def get_pause_remaining(self, chat_id: int) -> Optional[float]:
        """
        Get remaining pause time for a chat
        
        Args:
            chat_id: Telegram chat ID
        
        Returns:
            Remaining seconds, or None if not paused
        """
        if not self.is_paused(chat_id):
            return None
        
        if chat_id in self.pause_until:
            remaining = self.pause_until[chat_id] - time.time()
            return max(0, remaining)
        
        return None


# Global instance
_rate_limit_manager_instance = None

def get_rate_limit_manager() -> TelegramRateLimitManager:
    """Get or create global rate limit manager instance"""
    global _rate_limit_manager_instance
    if _rate_limit_manager_instance is None:
        _rate_limit_manager_instance = TelegramRateLimitManager()
    return _rate_limit_manager_instance
