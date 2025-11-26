#!/usr/bin/env python3
"""
Setup script for transfer module testing environment

Configures Python virtual environment and installs dependencies.
Run with: python setup.sh  (or via run_tests.sh)
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def run_command(cmd, description=""):
    """Run a shell command"""
    if description:
        print(f"\n▶ {description}")
    print(f"  Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"✗ Command failed with code {e.returncode}")
        return False


def main():
    """Setup environment"""
    print("\n" + "="*70)
    print("  TRANSFER MODULE TEST ENVIRONMENT SETUP")
    print("="*70)
    
    project_root = Path(__file__).parent.absolute()
    print(f"\nProject root: {project_root}")
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print(f"\n✗ Python 3.9+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        return 1
    
    print("\n✓ Python 3.9+ detected")
    
    # Install dependencies
    print("\n" + "-"*70)
    print("Installing dependencies...")
    print("-"*70)
    
    requirements_file = project_root / "requirements.txt"
    if not requirements_file.exists():
        print(f"\n✗ requirements.txt not found at {requirements_file}")
        return 1
    
    # Install packages
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file), "-q"]
    if not run_command(cmd, "Installing packages from requirements.txt"):
        print("\n✗ Failed to install dependencies")
        return 1
    
    print("\n✓ Dependencies installed successfully")
    
    # Verify imports
    print("\n" + "-"*70)
    print("Verifying imports...")
    print("-"*70)
    
    try:
        import pytest
        print("✓ pytest")
        
        import pydantic
        print("✓ pydantic")
        
        import yaml
        print("✓ pyyaml")
        
        print("\n✓ All dependencies verified")
    
    except ImportError as e:
        print(f"\n✗ Import failed: {e}")
        return 1
    
    # Create directories if needed
    print("\n" + "-"*70)
    print("Creating directory structure...")
    print("-"*70)
    
    dirs = [
        project_root / "src",
        project_root / "tests" / "integration",
        project_root / "mocks",
        project_root / "docs",
        project_root / "logs",
        project_root / "scripts"
    ]
    
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✓ {dir_path.relative_to(project_root)}")
    
    # Create __init__.py files
    print("\n" + "-"*70)
    print("Creating package markers...")
    print("-"*70)
    
    for package_dir in [
        project_root / "src",
        project_root / "tests",
        project_root / "tests" / "integration",
        project_root / "mocks"
    ]:
        init_file = package_dir / "__init__.py"
        init_file.touch()
        print(f"✓ {init_file.relative_to(project_root)}")
    
    print("\n" + "="*70)
    print("  SETUP COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("  1. Run tests: python tests/run_suite.py")
    print("  2. View results in logs/audit_schema.json")
    print("  3. Check docs/ for root cause analysis and remediation plan")
    print("")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
