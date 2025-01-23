"""Formatting utilities for the MemeWatch bot."""
from datetime import datetime, timezone
from utils.database import DatabaseManager  # ✓ Should work
from utils.formatting import (             # ✓ Should work
    format_number,
    format_price,
    format_time_ago,
    format_percentage
)

def format_number(num):
    """Format large numbers into readable strings with K, M, B, T suffixes"""
    try:
        num = float(num)
        if num >= 1_000_000_000_000:  # Trillion
            return f"{num/1_000_000_000_000:.2f}T"
        elif num >= 1_000_000_000:  # Billion
            return f"{num/1_000_000_000:.2f}B"
        elif num >= 1_000_000:  # Million
            return f"{num/1_000_000:.2f}M"
        elif num >= 1_000:  # Thousand
            return f"{num/1_000:.2f}K"
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return "0.00"

def format_price(price):
    """Format price with appropriate decimal places based on size"""
    try:
        price = float(price)
        if price < 0.0001:
            return f"${price:.10f}"
        elif price < 0.01:
            return f"${price:.6f}"
        elif price < 1:
            return f"${price:.4f}"
        else:
            return f"${price:.2f}"
    except (ValueError, TypeError):
        return "$0.00"

def format_time_ago(timestamp):
    """Convert timestamp to 'time ago' format"""
    if not timestamp:
        return "Unknown"
        
    try:
        # Convert milliseconds to seconds if necessary
        if timestamp > 1e12:
            timestamp = timestamp / 1000
            
        then = datetime.fromtimestamp(timestamp, timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - then
        
        if delta.days > 365:
            return f"{delta.days // 365}y"
        elif delta.days > 30:
            return f"{delta.days // 30}mo"
        elif delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m"
        return f"{delta.seconds}s"
    except (ValueError, TypeError):
        return "Unknown"

def format_percentage(value):
    """Format percentage with appropriate sign and decimals"""
    try:
        value = float(value)
        if value > 0:
            return f"+{value:.1f}%"
        return f"{value:.1f}%"
    except (ValueError, TypeError):
        return "0.0%"