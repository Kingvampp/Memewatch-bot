from datetime import datetime, timezone

def format_number(num):
    if num >= 1_000_000_000_000:  # Trillion
        return f"{num/1_000_000_000_000:.2f}T"
    elif num >= 1_000_000_000:  # Billion
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:  # Million
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:  # Thousand
        return f"{num/1_000:.2f}K"
    return f"{num:.2f}"

def format_price(price):
    if price < 0.0001:
        return f"${price:.10f}"
    elif price < 0.01:
        return f"${price:.6f}"
    else:
        return f"${price:.4f}"

def format_time_ago(timestamp):
    if not timestamp:
        return "Unknown"
    then = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - then
    
    if delta.days > 0:
        return f"{delta.days}d"
    elif delta.seconds >= 3600:
        return f"{delta.seconds // 3600}h"
    elif delta.seconds >= 60:
        return f"{delta.seconds // 60}m"
    return f"{delta.seconds}s" 
