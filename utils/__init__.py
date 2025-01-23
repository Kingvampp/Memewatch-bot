"""Utility package for the MemeWatch bot."""

# Import the DatabaseManager class
from .database import DatabaseManager

# Import formatting functions
from .formatting import (
    format_number,
    format_price,
    format_time_ago,
    format_percentage
)

# Define what should be available when importing from utils
__all__ = [
    'DatabaseManager',
    'format_number',
    'format_price',
    'format_time_ago',
    'format_percentage'
]
