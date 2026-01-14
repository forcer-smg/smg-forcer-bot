# -*- coding: utf-8 -*-
"""
Telegram Rate Limiter - Per-chat leaky bucket with Retry-After support
Implements proper rate limiting per Telegram's guidelines:
- Max 1 message per second per chat
- Max 20-30 per minute per chat (groups)
- Respect Retry-After header from 429 responses
- Use jitter to prevent thundering herd
"""

import time
import asyncio
import logging
import random
from typing import Optional, Dict, Any
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ChatRateLimiter:
    """Per-chat rate limiter with leaky bucket algorithm"""
    
    def __init__(self, chat_id: int, is_group: bool = False):
        """
        Initialize per-chat rate limiter
        
        Args:
            chat_id: Telegram chat ID
            is_group: True if this is a group chat (stricter limits)
        """
        self.chat_id = chat_id
        self.is_group = is_group
        
        # Leaky bucket: track message timestamps
        # Max 1 msg/sec, max 20-30/min (30 for groups, 20 for private)
        self.max_per_second = 1
        self.max_per_minute = 30 if is_group else 20
        
        # Message timestamps (leaky bucket)
        self.message_timestamps = deque(maxlen=self.max_per_minute)
        
        # Cooldown until when this chat is paused (from Retry-After)
        self.cooldown_until = None
        
        logger.debug(f"ChatRateLimiter initialized for chat {chat_id} (group: {is_group})")
    
    def can_send(self) -> bool:
        """
        Check if we can send a message to this chat
        
        Returns:
            True if allowed, False if should wait
        """
        now = time.time()
        
        # Check if chat is in cooldown (from Retry-After)
        if self.cooldown_until and now < self.cooldown_until:
            return False
        
        # Remove old timestamps (older than 1 second)
        cutoff = now - 1.0
        while self.message_timestamps and self.message_timestamps[0] < cutoff:
            self.message_timestamps.popleft()
        
        # Check per-second limit
        recent_count = len([ts for ts in self.message_timestamps if ts > cutoff])
        if recent_count >= self.max_per_second:
            return False
        
        # Remove old timestamps (older than 1 minute)
        minute_cutoff = now - 60.0
        while self.message_timestamps and self.message_timestamps[0] < minute_cutoff:
            self.message_timestamps.popleft()
        
        # Check per-minute limit
        minute_count = len(self.message_timestamps)
        if minute_count >= self.max_per_minute:
            return False
        
        return True
    
    def record_sent(self):
        """Record that a message was sent to this chat"""
        now = time.time()
        self.message_timestamps.append(now)
    
    def pause_for(self, seconds: float, jitter: bool = True):
        """
        Pause this chat for a period (e.g., from Retry-After)
        
        Args:
            seconds: Seconds to wait
            jitter: Add random jitter (0.7-1.3x multiplier)
        """
        if jitter:
            # Add jitter: random(0.7-1.3) to prevent thundering herd
            jitter_multiplier = random.uniform(0.7, 1.3)
            seconds = seconds * jitter_multiplier
        
        self.cooldown_until = time.time() + seconds
        logger.info(f"Chat {self.chat_id} paused for {seconds:.2f}s (cooldown until {self.cooldown_until:.2f})")
    
    def get_wait_time(self) -> float:
        """
        Get how long to wait before next message can be sent
        
        Returns:
            Wait time in seconds (0 if can send now)
        """
        now = time.time()
        
        # Check cooldown
        if self.cooldown_until and now < self.cooldown_until:
            return self.cooldown_until - now
        
        # Check per-second limit
        if self.message_timestamps:
            oldest_recent = min([ts for ts in self.message_timestamps if ts > now - 1.0], default=None)
            if oldest_recent:
                wait = 1.0 - (now - oldest_recent)
                if wait > 0:
                    return wait
        
        # Check per-minute limit
        if len(self.message_timestamps) >= self.max_per_minute:
            oldest = self.message_timestamps[0]
            wait = 60.0 - (now - oldest)
            if wait > 0:
                return wait
        
        return 0.0


class TelegramRateLimiter:
    """Global rate limiter with per-chat tracking"""
    
    def __init__(self):
        """Initialize global rate limiter"""
        # Per-chat rate limiters
        self.chat_limiters: Dict[int, ChatRateLimiter] = {}
        
        # Global backoff (for global rate limits)
        self.global_backoff_until = None
        
        logger.info("Telegram Rate Limiter initialized with per-chat leaky bucket")
    
    def get_chat_limiter(self, chat_id: int, is_group: bool = False) -> ChatRateLimiter:
        """
        Get or create rate limiter for a chat
        
        Args:
            chat_id: Telegram chat ID
            is_group: True if group chat
        
        Returns:
            ChatRateLimiter instance
        """
        if chat_id not in self.chat_limiters:
            self.chat_limiters[chat_id] = ChatRateLimiter(chat_id, is_group)
        return self.chat_limiters[chat_id]
    
    def can_send_message(self, chat_id: Optional[int] = None) -> bool:
        """
        Check if we can send a message
        
        Args:
            chat_id: Optional chat ID for per-chat checking
        
        Returns:
            True if can send, False if should wait
        """
        # Check global backoff
        if self.global_backoff_until and time.time() < self.global_backoff_until:
            return False
        
        # Check per-chat if chat_id provided
        if chat_id:
            limiter = self.get_chat_limiter(chat_id)
            return limiter.can_send()
        
        return True
    
    async def wait_if_needed(self, chat_id: Optional[int] = None) -> float:
        """
        Wait if rate limit would be hit
        
        Args:
            chat_id: Optional chat ID for per-chat waiting
        
        Returns:
            Time waited in seconds
        """
        # Check global backoff
        now = time.time()
        if self.global_backoff_until and now < self.global_backoff_until:
            wait_time = self.global_backoff_until - now
            logger.info(f"Waiting for global backoff: {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            return wait_time
        
        # Check per-chat if chat_id provided
        if chat_id:
            limiter = self.get_chat_limiter(chat_id)
            wait_time = limiter.get_wait_time()
            if wait_time > 0:
                logger.debug(f"Waiting for chat {chat_id} rate limit: {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        return 0.0
    
    def record_message_sent(self, chat_id: Optional[int] = None):
        """
        Record that a message was sent
        
        Args:
            chat_id: Optional chat ID for per-chat tracking
        """
        if chat_id:
            limiter = self.get_chat_limiter(chat_id)
            limiter.record_sent()
    
    def handle_rate_limit(self, retry_after: Optional[int] = None, chat_id: Optional[int] = None):
        """
        Handle Telegram API rate limit error (429)
        
        Args:
            retry_after: Seconds to wait from Retry-After header
            chat_id: Optional chat ID for per-chat cooldown
        """
        if retry_after:
            # Use Telegram's Retry-After value
            wait_time = retry_after
            
            # Add jitter: random(0.7-1.3) to prevent thundering herd
            jitter_multiplier = random.uniform(0.7, 1.3)
            wait_time = wait_time * jitter_multiplier
            
            logger.warning(f"Rate limit hit - Retry-After: {retry_after}s, waiting {wait_time:.2f}s (with jitter)")
            
            if chat_id:
                # Pause this specific chat
                limiter = self.get_chat_limiter(chat_id)
                limiter.pause_for(wait_time, jitter=False)  # Already applied jitter
            else:
                # Global backoff
                self.global_backoff_until = time.time() + wait_time
        else:
            # No Retry-After - use exponential backoff
            wait_time = 5.0  # Default 5 seconds
            logger.warning(f"Rate limit hit (no Retry-After) - waiting {wait_time}s")
            
            if chat_id:
                limiter = self.get_chat_limiter(chat_id)
                limiter.pause_for(wait_time)
            else:
                self.global_backoff_until = time.time() + wait_time
    
    def handle_timeout(self, error: Exception, chat_id: Optional[int] = None):
        """
        Handle Telegram API timeout
        
        Args:
            error: The timeout error
            chat_id: Optional chat ID
        """
        # Use exponential backoff for timeouts
        wait_time = 2.0  # Start with 2 seconds
        
        logger.warning(f"Telegram API timeout - waiting {wait_time}s")
        
        if chat_id:
            limiter = self.get_chat_limiter(chat_id)
            limiter.pause_for(wait_time)
        else:
            self.global_backoff_until = time.time() + wait_time


# Global instance
_telegram_rate_limiter_instance = None

def get_telegram_rate_limiter() -> TelegramRateLimiter:
    """Get or create global Telegram rate limiter instance"""
    global _telegram_rate_limiter_instance
    if _telegram_rate_limiter_instance is None:
        _telegram_rate_limiter_instance = TelegramRateLimiter()
    return _telegram_rate_limiter_instance
