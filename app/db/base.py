"""
Database Base Configuration Module

This module establishes the SQLAlchemy declarative base which all ORM models inherit from.
It provides the foundation for database table definitions and relationships.

Author: Vectra Project
License: AGPL-3.0
"""

from sqlalchemy.orm import declarative_base

# Create the declarative base class
# All ORM models must inherit from this base to be registered with SQLAlchemy
Base = declarative_base()
