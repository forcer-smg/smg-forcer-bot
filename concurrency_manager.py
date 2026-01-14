# -*- coding: utf-8 -*-
"""
Concurrency Manager - Request queuing, connection pooling, and resource management
Handles 500+ concurrent users with proper resource limits and queuing
"""

import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from collections import deque
from datetime import datetime, timedelta
import psutil
import os

logger = logging.getLogger(__name__)


class RequestQueue:
    """Thread-safe request queue with priority"""
    
    def __init__(self, max_size: int = 1000):
        self.queue = deque()
        self.max_size = max_size
        self.lock = threading.Lock()
        self.total_processed = 0
        self.total_dropped = 0
    
    def add(self, item: Any, priority: int = 0) -> bool:
        """Add item to queue with priority (lower = higher priority)"""
        with self.lock:
            if len(self.queue) >= self.max_size:
                self.total_dropped += 1
                return False
            
            self.queue.append((priority, time.time(), item))
            self.queue = deque(sorted(self.queue, key=lambda x: (x[0], x[1])))
            return True
    
    def get(self) -> Optional[Any]:
        """Get next item from queue"""
        with self.lock:
            if not self.queue:
                return None
            _, _, item = self.queue.popleft()
            self.total_processed += 1
            return item
    
    def size(self) -> int:
        """Get current queue size"""
        with self.lock:
            return len(self.queue)
    
    def clear(self):
        """Clear queue"""
        with self.lock:
            self.queue.clear()


class CircuitBreaker:
    """Circuit breaker pattern for overload protection"""
    
    def __init__(self, failure_threshold: int = 10, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open
        self.lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        with self.lock:
            if self.state == 'open':
                if self.last_failure_time and (time.time() - self.last_failure_time) > self.timeout:
                    self.state = 'half_open'
                    logger.info("Circuit breaker: Attempting recovery (half-open)")
                else:
                    raise Exception("Circuit breaker is OPEN - system overloaded")
        
        try:
            result = func(*args, **kwargs)
            # Success - reset failures
            with self.lock:
                if self.state == 'half_open':
                    self.state = 'closed'
                self.failures = 0
            return result
        except Exception as e:
            with self.lock:
                self.failures += 1
                self.last_failure_time = time.time()
                if self.failures >= self.failure_threshold:
                    self.state = 'open'
                    logger.error(f"Circuit breaker OPENED after {self.failures} failures")
            raise


class ResourceLimiter:
    """Per-user resource limits"""
    
    def __init__(self, max_memory_mb: int = 100, max_cpu_percent: float = 10.0):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent
        self.user_resources: Dict[int, Dict] = {}
        self.lock = threading.Lock()
    
    def check_limit(self, user_id: int) -> tuple[bool, str]:
        """Check if user is within resource limits"""
        with self.lock:
            if user_id not in self.user_resources:
                self.user_resources[user_id] = {
                    'memory_mb': 0,
                    'cpu_percent': 0.0,
                    'last_reset': time.time()
                }
            
            user_res = self.user_resources[user_id]
            
            # Reset if more than 1 hour old
            if time.time() - user_res['last_reset'] > 3600:
                user_res['memory_mb'] = 0
                user_res['cpu_percent'] = 0.0
                user_res['last_reset'] = time.time()
            
            if user_res['memory_mb'] > self.max_memory_mb:
                return False, f"Memory limit exceeded: {user_res['memory_mb']}MB > {self.max_memory_mb}MB"
            
            if user_res['cpu_percent'] > self.max_cpu_percent:
                return False, f"CPU limit exceeded: {user_res['cpu_percent']:.1f}% > {self.max_cpu_percent}%"
            
            return True, "OK"
    
    def record_usage(self, user_id: int, memory_mb: float, cpu_percent: float):
        """Record resource usage for user"""
        with self.lock:
            if user_id not in self.user_resources:
                self.user_resources[user_id] = {
                    'memory_mb': 0,
                    'cpu_percent': 0.0,
                    'last_reset': time.time()
                }
            
            self.user_resources[user_id]['memory_mb'] += memory_mb
            self.user_resources[user_id]['cpu_percent'] = max(
                self.user_resources[user_id]['cpu_percent'],
                cpu_percent
            )


class ConcurrencyManager:
    """Manages concurrency for 500+ users"""
    
    def __init__(self, max_concurrent: int = 500, queue_size: int = 1000):
        self.max_concurrent = max_concurrent
        self.active_requests: Dict[int, datetime] = {}
        self.active_requests_lock = threading.Lock()
        self.request_queue = RequestQueue(max_size=queue_size)
        self.circuit_breaker = CircuitBreaker()
        self.resource_limiter = ResourceLimiter()
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'active_requests': 0,
            'queued_requests': 0,
            'dropped_requests': 0,
            'errors': 0
        }
        self.stats_lock = threading.Lock()
    
    def can_accept_request(self, user_id: int) -> tuple[bool, str]:
        """Check if we can accept a new request"""
        # Check resource limits
        can_proceed, reason = self.resource_limiter.check_limit(user_id)
        if not can_proceed:
            return False, reason
        
        # Check active requests
        with self.active_requests_lock:
            active_count = len(self.active_requests)
            if active_count >= self.max_concurrent:
                return False, f"Maximum concurrent requests reached: {active_count}/{self.max_concurrent}"
        
        return True, "OK"
    
    async def process_request(self, user_id: int, handler: Callable, *args, **kwargs) -> Any:
        """Process request with concurrency management"""
        # Check if we can accept
        can_accept, reason = self.can_accept_request(user_id)
        if not can_accept:
            # Try to queue
            if self.request_queue.add((user_id, handler, args, kwargs), priority=1):
                with self.stats_lock:
                    self.stats['queued_requests'] += 1
                raise Exception(f"Request queued. {reason}")
            else:
                with self.stats_lock:
                    self.stats['dropped_requests'] += 1
                raise Exception(f"Request dropped. Queue full. {reason}")
        
        # Mark as active
        with self.active_requests_lock:
            self.active_requests[user_id] = datetime.now()
        
        with self.stats_lock:
            self.stats['total_requests'] += 1
            self.stats['active_requests'] = len(self.active_requests)
        
        try:
            # Process with circuit breaker
            result = await self.circuit_breaker.call(handler, *args, **kwargs)
            return result
        except Exception as e:
            with self.stats_lock:
                self.stats['errors'] += 1
            raise
        finally:
            # Remove from active
            with self.active_requests_lock:
                self.active_requests.pop(user_id, None)
            
            with self.stats_lock:
                self.stats['active_requests'] = len(self.active_requests)
    
    def get_stats(self) -> Dict:
        """Get concurrency statistics"""
        with self.stats_lock:
            return {
                **self.stats,
                'queue_size': self.request_queue.size(),
                'circuit_breaker_state': self.circuit_breaker.state
            }
    
    async def process_queue(self):
        """Background task to process queued requests"""
        while True:
            try:
                item = self.request_queue.get()
                if item:
                    user_id, handler, args, kwargs = item
                    try:
                        await self.process_request(user_id, handler, *args, **kwargs)
                    except Exception as e:
                        logger.error(f"Error processing queued request for user {user_id}: {e}")
                
                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(1)


# Global concurrency manager instance
_concurrency_manager_instance = None
_concurrency_manager_lock = threading.Lock()

def get_concurrency_manager(max_concurrent: int = 500) -> ConcurrencyManager:
    """Get or create global concurrency manager instance"""
    global _concurrency_manager_instance
    with _concurrency_manager_lock:
        if _concurrency_manager_instance is None:
            _concurrency_manager_instance = ConcurrencyManager(max_concurrent=max_concurrent)
        return _concurrency_manager_instance
