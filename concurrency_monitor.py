# -*- coding: utf-8 -*-
"""
Concurrency Monitor - Monitor active users, resources, and system health
Tracks concurrent usage, resource consumption, and system performance
"""

import os
import logging
import threading
import time
import psutil
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConcurrencyMonitor:
    """Monitor concurrency, resources, and system health"""
    
    def __init__(self):
        """Initialize Concurrency Monitor"""
        self.active_users: Dict[int, datetime] = {}
        self.user_requests: Dict[int, int] = defaultdict(int)
        self.user_errors: Dict[int, int] = defaultdict(int)
        self.lock = threading.Lock()
        
        # System metrics
        self.system_metrics = {
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'memory_used_mb': 0.0,
            'memory_available_mb': 0.0,
            'disk_usage_percent': 0.0,
            'last_update': None
        }
        
        # Performance metrics
        self.performance_metrics = {
            'total_requests': 0,
            'active_requests': 0,
            'average_response_time': 0.0,
            'error_rate': 0.0,
            'requests_per_second': 0.0
        }
        
        # Update interval
        self.update_interval = 5  # Update every 5 seconds
        self.last_update = time.time()
    
    def register_user_activity(self, user_id: int):
        """Register user activity"""
        with self.lock:
            self.active_users[user_id] = datetime.now()
            self.user_requests[user_id] += 1
    
    def register_user_error(self, user_id: int):
        """Register user error"""
        with self.lock:
            self.user_errors[user_id] += 1
    
    def get_active_users(self) -> List[int]:
        """Get list of active user IDs"""
        with self.lock:
            # Remove users inactive for more than 1 hour
            now = datetime.now()
            inactive_threshold = timedelta(hours=1)
            
            active = []
            for user_id, last_activity in list(self.active_users.items()):
                if now - last_activity < inactive_threshold:
                    active.append(user_id)
                else:
                    del self.active_users[user_id]
            
            return active
    
    def get_active_user_count(self) -> int:
        """Get count of active users"""
        return len(self.get_active_users())
    
    def update_system_metrics(self):
        """Update system resource metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage_percent = disk.percent
            
            with self.lock:
                self.system_metrics.update({
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory_percent,
                    'memory_used_mb': memory_used_mb,
                    'memory_available_mb': memory_available_mb,
                    'disk_usage_percent': disk_usage_percent,
                    'last_update': datetime.now().isoformat()
                })
        
        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")
    
    def get_system_metrics(self) -> Dict:
        """Get current system metrics"""
        self.update_system_metrics()
        with self.lock:
            return self.system_metrics.copy()
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get statistics for specific user"""
        with self.lock:
            return {
                'user_id': user_id,
                'is_active': user_id in self.active_users,
                'last_activity': self.active_users.get(user_id),
                'total_requests': self.user_requests.get(user_id, 0),
                'total_errors': self.user_errors.get(user_id, 0),
                'error_rate': (
                    self.user_errors.get(user_id, 0) / max(self.user_requests.get(user_id, 1), 1)
                ) * 100
            }
    
    def get_all_stats(self) -> Dict:
        """Get all monitoring statistics"""
        with self.lock:
            active_count = len(self.active_users)
            total_requests = sum(self.user_requests.values())
            total_errors = sum(self.user_errors.values())
            
            return {
                'active_users': active_count,
                'total_requests': total_requests,
                'total_errors': total_errors,
                'error_rate': (total_errors / max(total_requests, 1)) * 100,
                'system_metrics': self.get_system_metrics(),
                'performance_metrics': self.performance_metrics.copy()
            }
    
    def check_health(self) -> tuple[bool, str]:
        """Check system health"""
        metrics = self.get_system_metrics()
        
        issues = []
        
        # Check CPU
        if metrics['cpu_percent'] > 90:
            issues.append(f"High CPU usage: {metrics['cpu_percent']:.1f}%")
        
        # Check memory
        if metrics['memory_percent'] > 90:
            issues.append(f"High memory usage: {metrics['memory_percent']:.1f}%")
        
        # Check disk
        if metrics['disk_usage_percent'] > 90:
            issues.append(f"High disk usage: {metrics['disk_usage_percent']:.1f}%")
        
        # Check error rate
        all_stats = self.get_all_stats()
        if all_stats['error_rate'] > 10:
            issues.append(f"High error rate: {all_stats['error_rate']:.1f}%")
        
        if issues:
            return False, "; ".join(issues)
        
        return True, "System healthy"
    
    def get_health_report(self) -> str:
        """Get formatted health report"""
        stats = self.get_all_stats()
        metrics = stats['system_metrics']
        health_ok, health_msg = self.check_health()
        
        report = f"""
╔═══════════════════════════════════════╗
║     SYSTEM HEALTH REPORT              ║
╚═══════════════════════════════════════╝

┌─ ACTIVE USERS ────────────────────────┐
│ Active Users: {stats['active_users']:<23} │
│ Total Requests: {stats['total_requests']:<19} │
│ Total Errors: {stats['total_errors']:<21} │
│ Error Rate: {stats['error_rate']:.2f}%{' ' * (18 - len(f'{stats['error_rate']:.2f}%'))} │
└──────────────────────────────────────┘

┌─ SYSTEM RESOURCES ────────────────────┐
│ CPU Usage: {metrics['cpu_percent']:.1f}%{' ' * (24 - len(f'{metrics['cpu_percent']:.1f}%'))} │
│ Memory Usage: {metrics['memory_percent']:.1f}%{' ' * (20 - len(f'{metrics['memory_percent']:.1f}%'))} │
│ Memory Used: {metrics['memory_used_mb']:.0f} MB{' ' * (19 - len(f'{metrics['memory_used_mb']:.0f} MB'))} │
│ Disk Usage: {metrics['disk_usage_percent']:.1f}%{' ' * (22 - len(f'{metrics['disk_usage_percent']:.1f}%'))} │
└──────────────────────────────────────┘

┌─ HEALTH STATUS ───────────────────────┐
│ Status: {'✅ HEALTHY' if health_ok else '⚠️ ISSUES DETECTED'}{' ' * (15 if health_ok else 0)} │
│ Message: {health_msg:<25} │
└──────────────────────────────────────┘
        """
        
        return report.strip()


# Global concurrency monitor instance
_monitor_instance = None
_monitor_lock = threading.Lock()

def get_concurrency_monitor() -> ConcurrencyMonitor:
    """Get or create global concurrency monitor instance"""
    global _monitor_instance
    with _monitor_lock:
        if _monitor_instance is None:
            _monitor_instance = ConcurrencyMonitor()
        return _monitor_instance
