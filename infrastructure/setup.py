#!/usr/bin/env python3
"""Setup script for CDK Python environment."""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and handle errors."""
    print(f"\n➜ {description}...")
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"✅ {description} completed")
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        sys.exit(1)


def main():
    """Set up Python CDK environment."""
    print("🚀 Setting up HelioTime CDK (Python)")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✅ Python version: {sys.version}")
    
    # Create virtual environment if it doesn't exist
    venv_path = Path(".venv")
    if not venv_path.exists():
        run_command(
            f"{sys.executable} -m venv .venv",
            "Creating virtual environment"
        )
    else:
        print("✅ Virtual environment already exists")
    
    # Determine pip path based on OS
    if os.name == 'nt':  # Windows
        pip_path = ".venv\\Scripts\\pip"
        activate_cmd = ".venv\\Scripts\\activate"
    else:  # Unix/MacOS
        pip_path = ".venv/bin/pip"
        activate_cmd = "source .venv/bin/activate"
    
    # Upgrade pip
    run_command(
        f"{pip_path} install --upgrade pip",
        "Upgrading pip"
    )
    
    # Install requirements
    run_command(
        f"{pip_path} install -r requirements.txt",
        "Installing CDK dependencies"
    )
    
    # Install AWS CDK globally if not present
    try:
        subprocess.run("cdk --version", shell=True, check=True, capture_output=True)
        print("✅ AWS CDK is already installed")
    except:
        print("⚠️  AWS CDK not found globally")
        print("   Install with: npm install -g aws-cdk")
    
    print("\n" + "=" * 50)
    print("✅ Setup complete!")
    print("\nNext steps:")
    print(f"1. Activate virtual environment: {activate_cmd}")
    print("2. Synthesize stacks: cdk synth")
    print("3. Deploy shared stack: cdk deploy HelioTimeSharedStack")
    print("4. Deploy dev stack: cdk deploy HelioTimeDevStack")
    print("\nOr use the Makefile: make deploy-dev")


if __name__ == "__main__":
    main()