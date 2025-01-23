# Create a test_imports.py file
try:
    from utils.database import DatabaseManager
    from utils.formatting import format_number, format_price, format_time_ago, format_percentage
    print("✅ All imports working correctly!")
except ImportError as e:
    print(f"❌ Import error: {str(e)}") 