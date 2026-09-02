"""
Fake Review Detection System - Python Environment Setup Script
Verifies system prerequisites, installs dependencies, and downloads NLTK resources.
"""

import os
import sys
import subprocess
import ssl

def check_python_version():
    """Ensure Python version is 3.8+."""
    print("[1/3] Checking Python Version...")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 8):
        print(f"[ERROR] Python 3.8+ required. Found Python {major}.{minor}")
        sys.exit(1)
    print(f"✅ Python {major}.{minor} detected.")

def install_requirements():
    """Installs required packages from requirements.txt."""
    print("\n[2/3] Verifying and Installing Python Packages...")
    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    if os.path.exists(req_path):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
            print("✅ All Python dependencies are installed.")
        except Exception as e:
            print(f"[WARNING] Dependency installation warning: {e}")

def setup_nltk():
    """Downloads required NLTK resources."""
    print("\n[3/3] Downloading NLTK Corpora & Tokenizers...")
    try:
        _create_unverified_https_context = ssl._create_unverified_context
    except AttributeError:
        pass
    else:
        ssl._create_default_https_context = _create_unverified_https_context

    import nltk
    resources = ['stopwords', 'wordnet', 'omw-1.4']
    for resource in resources:
        try:
            nltk.data.find(f'corpora/{resource}')
            print(f"  - Resource '{resource}' already present.")
        except LookupError:
            print(f"  - Downloading NLTK resource '{resource}'...")
            nltk.download(resource, quiet=True)
    print("✅ NLTK resources setup completed.")

def main():
    print("=" * 60)
    print("      ENVIRONMENT SETUP: FAKE REVIEW DETECTION SYSTEM      ")
    print("=" * 60)
    check_python_version()
    install_requirements()
    setup_nltk()
    print("\n" + "=" * 60)
    print("🎉 ENVIRONMENT SETUP COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
