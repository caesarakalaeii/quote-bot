#!/usr/bin/env python3
"""Simple validation script for the quote bot setup."""
import sys
import os
import importlib.util

def check_file_exists(filepath, description):
    """Check if a file exists."""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description}: {filepath} (missing)")
        return False

def check_python_import(module_name, filepath):
    """Check if a Python module can be imported."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None:
            print(f"❌ {module_name}: Cannot load module spec")
            return False
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"✅ {module_name}: Imports successfully")
        return True
    except Exception as e:
        print(f"❌ {module_name}: Import failed - {e}")
        return False

def check_requirements():
    """Check if requirements.txt dependencies are available."""
    try:
        import discord
        print("✅ discord.py: Available")
    except ImportError:
        print("❌ discord.py: Not installed (pip install discord.py)")
        return False
    
    try:
        import psycopg2
        print("✅ psycopg2: Available")
    except ImportError:
        print("❌ psycopg2: Not installed (pip install psycopg2-binary)")
        return False
    
    try:
        import dotenv
        print("✅ python-dotenv: Available")
    except ImportError:
        print("❌ python-dotenv: Not installed (pip install python-dotenv)")
        return False
    
    return True

def main():
    """Run validation checks."""
    print("🔍 Quote Bot Setup Validation\n")
    
    # Check core files
    files_ok = True
    files_to_check = [
        ("requirements.txt", "Requirements file"),
        ("config.py", "Configuration module"),
        ("database.py", "Database module"),
        ("bot.py", "Main bot file"),
        (".env.template", "Environment template"),
        ("README.md", "Documentation")
    ]
    
    for filename, description in files_to_check:
        if not check_file_exists(filename, description):
            files_ok = False
    
    print()
    
    # Check Python imports
    imports_ok = True
    modules_to_check = [
        ("config", "config.py"),
        ("database", "database.py"),
        ("bot", "bot.py")
    ]
    
    for module_name, filepath in modules_to_check:
        if not check_python_import(module_name, filepath):
            imports_ok = False
    
    print()
    
    # Check requirements
    requirements_ok = check_requirements()
    
    print()
    
    # Summary
    if files_ok and imports_ok and requirements_ok:
        print("🎉 All checks passed! The bot setup looks good.")
        print("\n📝 Next steps:")
        print("1. Set up PostgreSQL database")
        print("2. Copy .env.template to .env and configure")
        print("3. Run: python bot.py")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())