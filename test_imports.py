try:
    from academics.models import Department
    from users.models import Student
    print("✅ Imports successful! Circular dependency resolved.")
except ImportError as e:
    print(f"❌ Import failed: {e}")
except Exception as e:
    print(f"❌ An error occurred: {e}")
