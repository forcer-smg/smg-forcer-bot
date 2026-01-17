# -*- coding: utf-8 -*-
"""
Evaluation & Monitoring System
Tracks task success rates, error patterns, and performance metrics
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


class EvaluationSystem:
    """Evaluation and monitoring system for AI task performance"""
    
    def __init__(self, base_dir: str = "/app/evaluation_data"):
        """
        Initialize evaluation system
        
        Args:
            base_dir: Base directory for storing evaluation data
        """
        self.base_dir = Path(base_dir)
        self.metrics_dir = self.base_dir / "metrics"
        self.errors_dir = self.base_dir / "errors"
        self.feedback_dir = self.base_dir / "feedback"
        
        # Create directories
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self.errors_dir.mkdir(parents=True, exist_ok=True)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory metrics cache (last 1000 tasks)
        self.metrics_cache = []
        self.error_patterns = defaultdict(int)
    
    def record_task_execution(self,
                             task_id: str,
                             task_description: str,
                             success: bool,
                             duration: float,
                             iterations: int,
                             errors: List[str],
                             user_id: Optional[int] = None,
                             metadata: Optional[Dict] = None) -> None:
        """
        Record a task execution for evaluation
        
        Args:
            task_id: Unique task identifier
            task_description: Task description
            success: Whether task completed successfully
            duration: Task duration in seconds
            iterations: Number of iterations taken
            errors: List of errors encountered
            user_id: User ID (optional)
            metadata: Additional metadata
        """
        record = {
            "task_id": task_id,
            "task_description": task_description[:500],  # Truncate
            "success": success,
            "duration": duration,
            "iterations": iterations,
            "error_count": len(errors),
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # Save to file
        try:
            record_file = self.metrics_dir / f"{task_id}.json"
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            
            # Add to cache
            self.metrics_cache.append(record)
            if len(self.metrics_cache) > 1000:
                self.metrics_cache = self.metrics_cache[-1000:]
            
            # Track error patterns
            for error in errors:
                error_type = self._classify_error(error)
                self.error_patterns[error_type] += 1
            
            logger.info(f"Recorded task execution: {task_id} (success={success}, duration={duration:.2f}s)")
        except Exception as e:
            logger.error(f"Error recording task execution: {e}")
    
    def record_error(self,
                    task_id: str,
                    error_message: str,
                    error_type: str,
                    context: Optional[Dict] = None) -> None:
        """
        Record a specific error for analysis
        
        Args:
            task_id: Task ID where error occurred
            error_message: Error message
            error_type: Error classification
            context: Additional context
        """
        error_record = {
            "task_id": task_id,
            "error_message": error_message[:1000],  # Truncate
            "error_type": error_type,
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            error_file = self.errors_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(error_file, 'w', encoding='utf-8') as f:
                json.dump(error_record, f, indent=2, ensure_ascii=False)
            
            # Update error patterns
            self.error_patterns[error_type] += 1
            
            logger.info(f"Recorded error: {error_type} for task {task_id}")
        except Exception as e:
            logger.error(f"Error recording error: {e}")
    
    def get_success_rate(self, days: int = 7) -> Dict[str, Any]:
        """
        Calculate success rate metrics
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with success rate metrics
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Filter recent records
        recent_records = [
            r for r in self.metrics_cache
            if datetime.fromisoformat(r["timestamp"]) >= cutoff_date
        ]
        
        if not recent_records:
            return {
                "success_rate": 0.0,
                "total_tasks": 0,
                "successful_tasks": 0,
                "failed_tasks": 0,
                "average_duration": 0.0,
                "average_iterations": 0.0
            }
        
        successful = sum(1 for r in recent_records if r["success"])
        total = len(recent_records)
        success_rate = successful / total if total > 0 else 0.0
        
        durations = [r["duration"] for r in recent_records if r["duration"] > 0]
        iterations = [r["iterations"] for r in recent_records if r["iterations"] > 0]
        
        return {
            "success_rate": success_rate,
            "total_tasks": total,
            "successful_tasks": successful,
            "failed_tasks": total - successful,
            "average_duration": statistics.mean(durations) if durations else 0.0,
            "average_iterations": statistics.mean(iterations) if iterations else 0.0,
            "median_duration": statistics.median(durations) if durations else 0.0,
            "median_iterations": statistics.median(iterations) if iterations else 0.0
        }
    
    def get_error_analysis(self, days: int = 7) -> Dict[str, Any]:
        """
        Analyze error patterns
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with error analysis
        """
        # Get top error patterns
        top_errors = sorted(
            self.error_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_error_types": len(self.error_patterns),
            "top_errors": [
                {"error_type": error_type, "count": count}
                for error_type, count in top_errors
            ],
            "most_common_error": top_errors[0][0] if top_errors else None
        }
    
    def get_performance_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Get performance trends over time
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with performance trends
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Group by day
        daily_metrics = defaultdict(lambda: {"success": 0, "total": 0, "durations": [], "iterations": []})
        
        for record in self.metrics_cache:
            record_date = datetime.fromisoformat(record["timestamp"])
            if record_date >= cutoff_date:
                day_key = record_date.strftime("%Y-%m-%d")
                daily_metrics[day_key]["total"] += 1
                if record["success"]:
                    daily_metrics[day_key]["success"] += 1
                if record["duration"] > 0:
                    daily_metrics[day_key]["durations"].append(record["duration"])
                if record["iterations"] > 0:
                    daily_metrics[day_key]["iterations"].append(record["iterations"])
        
        # Calculate daily success rates
        trends = []
        for day, metrics in sorted(daily_metrics.items()):
            success_rate = metrics["success"] / metrics["total"] if metrics["total"] > 0 else 0.0
            avg_duration = statistics.mean(metrics["durations"]) if metrics["durations"] else 0.0
            avg_iterations = statistics.mean(metrics["iterations"]) if metrics["iterations"] else 0.0
            
            trends.append({
                "date": day,
                "success_rate": success_rate,
                "total_tasks": metrics["total"],
                "average_duration": avg_duration,
                "average_iterations": avg_iterations
            })
        
        return {
            "trends": trends,
            "improving": self._detect_improvement(trends),
            "regressing": self._detect_regression(trends)
        }
    
    def record_feedback(self,
                       task_id: str,
                       feedback_type: str,
                       feedback_data: Dict,
                       user_id: Optional[int] = None) -> None:
        """
        Record user feedback
        
        Args:
            task_id: Task ID
            feedback_type: Type of feedback (positive, negative, correction, etc.)
            feedback_data: Feedback data
            user_id: User ID (optional)
        """
        feedback_record = {
            "task_id": task_id,
            "feedback_type": feedback_type,
            "feedback_data": feedback_data,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            feedback_file = self.feedback_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedback_record, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Recorded feedback: {feedback_type} for task {task_id}")
        except Exception as e:
            logger.error(f"Error recording feedback: {e}")
    
    def check_for_regressions(self, threshold: float = 0.1) -> List[Dict]:
        """
        Check for performance regressions
        
        Args:
            threshold: Success rate drop threshold (e.g., 0.1 = 10% drop)
        
        Returns:
            List of detected regressions
        """
        trends = self.get_performance_trends(days=7)
        
        regressions = []
        for i in range(1, len(trends["trends"])):
            prev_rate = trends["trends"][i-1]["success_rate"]
            curr_rate = trends["trends"][i]["success_rate"]
            
            if prev_rate > 0 and (prev_rate - curr_rate) >= threshold:
                regressions.append({
                    "date": trends["trends"][i]["date"],
                    "previous_rate": prev_rate,
                    "current_rate": curr_rate,
                    "drop": prev_rate - curr_rate
                })
        
        return regressions
    
    def _classify_error(self, error_message: str) -> str:
        """Classify error type from error message"""
        error_lower = error_message.lower()
        
        if "module not found" in error_lower or "no module named" in error_lower:
            return "module_not_found"
        elif "package" in error_lower and ("not available" in error_lower or "has no installation candidate" in error_lower):
            return "package_not_found"
        elif "git clone" in error_lower and "fatal" in error_lower:
            return "git_clone_failed"
        elif "file not found" in error_lower or "no such file" in error_lower:
            return "file_not_found"
        elif "permission denied" in error_lower:
            return "permission_denied"
        elif "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        elif "syntax error" in error_lower:
            return "syntax_error"
        elif "connection" in error_lower and ("refused" in error_lower or "timeout" in error_lower):
            return "connection_error"
        else:
            return "unknown_error"
    
    def _detect_improvement(self, trends: List[Dict]) -> bool:
        """Detect if performance is improving"""
        if len(trends) < 3:
            return False
        
        recent = trends[-3:]
        success_rates = [t["success_rate"] for t in recent]
        
        # Check if success rate is increasing
        return success_rates[-1] > success_rates[0]
    
    def _detect_regression(self, trends: List[Dict]) -> bool:
        """Detect if performance is regressing"""
        if len(trends) < 3:
            return False
        
        recent = trends[-3:]
        success_rates = [t["success_rate"] for t in recent]
        
        # Check if success rate is decreasing
        return success_rates[-1] < success_rates[0]
    
    def get_summary_report(self) -> str:
        """
        Generate a summary report of system performance
        
        Returns:
            Formatted summary report
        """
        success_metrics = self.get_success_rate(days=7)
        error_analysis = self.get_error_analysis(days=7)
        trends = self.get_performance_trends(days=7)
        regressions = self.check_for_regressions()
        
        report = f"""
# Evaluation System Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Success Metrics (Last 7 Days)
- Success Rate: {success_metrics['success_rate']:.1%}
- Total Tasks: {success_metrics['total_tasks']}
- Successful: {success_metrics['successful_tasks']}
- Failed: {success_metrics['failed_tasks']}
- Average Duration: {success_metrics['average_duration']:.2f}s
- Average Iterations: {success_metrics['average_iterations']:.1f}

## Error Analysis
- Total Error Types: {error_analysis['total_error_types']}
- Most Common Error: {error_analysis['most_common_error'] or 'N/A'}
- Top Errors:
"""
        for error in error_analysis['top_errors'][:5]:
            report += f"  - {error['error_type']}: {error['count']} occurrences\n"
        
        report += f"""
## Performance Trends
- Improving: {trends['improving']}
- Regressing: {trends['regressing']}

## Regressions Detected
"""
        if regressions:
            for reg in regressions:
                report += f"  - {reg['date']}: {reg['drop']:.1%} drop ({reg['previous_rate']:.1%} → {reg['current_rate']:.1%})\n"
        else:
            report += "  - No regressions detected\n"
        
        return report
