# -*- coding: utf-8 -*-
"""
Hybrid database adapter - automatically uses PostgreSQL if DATABASE_URL is set,
otherwise falls back to SQLite
"""

import os
import logging

logger = logging.getLogger(__name__)

# Check if DATABASE_URL is set (PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    # Use PostgreSQL
    try:
        from database_postgres import Database
        logger.info("Using PostgreSQL database (from DATABASE_URL)")
    except ImportError:
        logger.warning("DATABASE_URL set but psycopg2 not installed. Falling back to SQLite.")
        logger.warning("Install with: pip install psycopg2-binary")
        from database import Database
        logger.info("Using SQLite database (fallback)")
else:
    # Use SQLite (default)
    from database import Database
    logger.info("Using SQLite database (default)")

# Export Database class
__all__ = ['Database']

