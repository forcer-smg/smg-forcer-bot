# -*- coding: utf-8 -*-
"""
Telegram Rate Limiter - Handle Telegram API rate limits and timeouts gracefully
Prevents API timeouts and rate limit errors during long-running tasks
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TelegramRateLimiter:
    """Handle Telegram API rate limits and timeouts"""
    
    def __init__(self, max_messages_per_second: int = 25, max_messages_per_minute: int = 20):
        """
        Initialize rate limiter
        
        Args:
            max_messages_per_second: Maximum messages per second (Telegram limit is 30, we use 25 for safety)
            max_messages_per_minute: Maximum messages per minute (for burst protection)
        """
        self.max_mps = max_messages_per_second
        self.max_mpm = max_messages_per_minute
        
        # Track message timestamps
        self.message_timestamps = deque(maxlen=1000)  # Keep last 1000 timestamps
        self.minute_timestamps = deque(maxlen=100)  # Keep last 100 timestamps for minute window
        
        # Track failures for exponential backoff
        self.consecutive_failures = 0
        self.last_failure_time = None
        self.backoff_until = None
        
        logger.info(f"Telegram Rate Limiter initialized: {max_messages_per_second} msg/s, {max_messages_per_minute} msg/min")
    
    def can_send_message(self) -> bool:
        """
        Check if we can send a message without hitting rate limit
        
        Returns:
            True if we can send, False if we should wait
        """
        now = time.time()
        
        # Check if we're in backoff period
        if self.backoff_until and now < self.backoff_until:
            return False
        
        # Remove old timestamps (older than 1 second)
        cutoff = now - 1.0
        while self.message_timestamps and self.message_timestamps[0] < cutoff:
            self.message_timestamps.popleft()
        
        # Check messages per second
        if len(self.message_timestamps) >= self.max_mps:
            logger.debug(f"Rate limit: {len(self.message_timestamps)} messages in last second (max: {self.max_mps})")
            return False
        
        # Remove old timestamps (older than 1 minute)
        minute_cutoff = now - 60.0
        while self.minute_timestamps and self.minute_timestamps[0] < minute_cutoff:
            self.minute_timestamps.popleft()
        
        # Check messages per minute
        if len(self.minute_timestamps) >= self.max_mpm:
            logger.debug(f"Rate limit: {len(self.minute_timestamps)} messages in last minute (max: {self.max_mpm})")
            return False
        
        return True
    
    async def wait_if_needed(self) -> float:
        """
        Wait if rate limit would be hit, return wait time
        
        Returns:
            Time waited in seconds
        """
        if self.can_send_message():
            return 0.0
        
        # Calculate wait time
        now = time.time()
        
        # Wait until we can send
        wait_time = 0.0
        
        # Check backoff period
        if self.backoff_until and now < self.backoff_until:
            wait_time = self.backoff_until - now
            logger.info(f"Waiting for backoff period: {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            return wait_time
        
        # Wait for messages per second limit
        if self.message_timestamps:
            oldest = self.message_timestamps[0]
            time_since_oldest = now - oldest
            if time_since_oldest < 1.0:
                wait_time = 1.0 - time_since_oldest
                logger.debug(f"Waiting for rate limit: {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        # Wait for messages per minute limit
        if self.minute_timestamps:
            oldest = self.minute_timestamps[0]
            time_since_oldest = now - oldest
            if time_since_oldest < 60.0:
                wait_time = 60.0 - time_since_oldest
                logger.debug(f"Waiting for minute rate limit: {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        return wait_time
    
    def record_message_sent(self):
        """Record that a message was sent"""
        now = time.time()
        self.message_timestamps.append(now)
        self.minute_timestamps.append(now)
        
        # Reset failure count on successful send
        if self.consecutive_failures > 0:
            self.consecutive_failures = 0
            self.backoff_until = None
    
    def handle_timeout(self, error: Exception) -> Dict[str, Any]:
        """
        Handle Telegram API timeout
        
        Args:
            error: The timeout error
        
        Returns:
            Dictionary with retry information
        """
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        # Exponential backoff: 1s, 2s, 4s, 8s, max 30s
        backoff_time = min(2 ** (self.consecutive_failures - 1), 30)
        self.backoff_until = time.time() + backoff_time
        
        logger.warning(f"Telegram API timeout (failure #{self.consecutive_failures}), backing off for {backoff_time}s")
        
        return {
            'should_retry': True,
            'backoff_time': backoff_time,
            'retry_after': self.backoff_until
        }
    
    def handle_rate_limit(self, retry_after: int = None) -> Dict[str, Any]:
        """
        Handle Telegram API rate limit error
        
        Args:
            retry_after: Seconds to wait before retry (from API response)
        
        Returns:
            Dictionary with retry information
        """
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        # Use API's retry_after if provided, otherwise use exponential backoff
        if retry_after:
            backoff_time = retry_after
        else:
            backoff_time = min(2 ** (self.consecutive_failures - 1), 30)
        
        self.backoff_until = time.time() + backoff_time
        
        logger.warning(f"Telegram API rate limit (failure #{self.consecutive_failures}), waiting {backoff_time}s")
        
        return {
            'should_retry': True,
            'backoff_time': backoff_time,
            'retry_after': self.backoff_until
        }
    
    async def send_with_retry(self, 
                              send_func, 
                              max_retries: int = 3,
                              *args, 
                              **kwargs) -> Any:
        """
        Send message with automatic retry on timeout/rate limit
        
        Args:
            send_func: Async function to send message (e.g., update.message.reply_text)
            max_retries: Maximum retry attempts
            *args, **kwargs: Arguments to pass to send_func
        
        Returns:
            Result from send_func
        """
        for attempt in range(max_retries):
            try:
                # Wait if needed
                await self.wait_if_needed()
                
                # Try to send
                result = await send_func(*args, **kwargs)
                
                # Record successful send
                self.record_message_sent()
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a timeout
                if 'timeout' in error_str or 'timed out' in error_str:
                    retry_info = self.handle_timeout(e)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_info['backoff_time'])
                        continue
                    else:
                        logger.error(f"Max retries reached for timeout: {e}")
                        raise
                
                # Check if it's a rate limit
                elif 'rate limit' in error_str or 'too many requests' in error_str or '429' in error_str:
                    # Try to extract retry_after from error
                    retry_after = None
                    if 'retry_after' in error_str:
                        try:
                            # Extract number after "retry_after"
                            import re
                            match = re.search(r'retry_after[:\s]+(\d+)', error_str)
                            if match:
                                retry_after = int(match.group(1))
                        except:
                            pass
                    
                    retry_info = self.handle_rate_limit(retry_after)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_info['backoff_time'])
                        continue
                    else:
                        logger.error(f"Max retries reached for rate limit: {e}")
                        raise
                
                # Other errors - retry with exponential backoff
                else:
                    if attempt < max_retries - 1:
                        backoff = min(2 ** attempt, 10)  # 1s, 2s, 4s, max 10s
                        logger.warning(f"Error sending message (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.error(f"Max retries reached: {e}")
                        raise
        
        # Should never reach here, but just in case
        raise Exception("Failed to send message after all retries")


# Global instance
_telegram_rate_limiter_instance = None

def get_telegram_rate_limiter(max_mps: int = 25, max_mpm: int = 20) -> TelegramRateLimiter:
    """Get or create global Telegram rate limiter instance"""
    global _telegram_rate_limiter_instance
    if _telegram_rate_limiter_instance is None:
        _telegram_rate_limiter_instance = TelegramRateLimiter(max_mps, max_mpm)
    return _telegram_rate_limiter_instance
