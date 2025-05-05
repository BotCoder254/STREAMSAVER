import sys
import importlib
import platform
import os

def check_package_installed(package_name):
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False

if __name__ == "__main__":
    print("StreamSaver Pro - Dependency Checker")
    print("-" * 40)
    print(f"Python version: {platform.python_version()}")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Processor: {platform.processor()}")
    print("-" * 40)
    
    # Check required packages
    required_packages = {
        "flet": "UI Framework",
        "yt_dlp": "YouTube Download Library",
        "youtubesearchpython": "YouTube Search API",
        "psutil": "System Resource Monitor",
        "plotly": "Plotting Library for Statistics",
        "PIL": "Python Imaging Library (Pillow)"
    }
    
    all_installed = True
    for package, description in required_packages.items():
        is_installed = check_package_installed(package)
        status = "✓ Installed" if is_installed else "✗ Not installed"
        print(f"{package} ({description}): {status}")
        
        if not is_installed:
            all_installed = False
    
    print("-" * 40)
    if all_installed:
        print("All dependencies are installed. You're ready to run StreamSaver Pro!")
        print("Run with: python app.py")
    else:
        print("Some dependencies are missing. Please install them with:")
        print("pip install -r requirements.txt")
    
    # Check for ffmpeg
    print("-" * 40)
    print("Checking for ffmpeg...")
    ffmpeg_found = False
    
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        ffmpeg_found = True
    except FileNotFoundError:
        # Check in common Windows directories
        ffmpeg_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        
        for path in ffmpeg_paths:
            if os.path.exists(path):
                ffmpeg_found = True
                break
    
    if ffmpeg_found:
        print("ffmpeg: ✓ Installed")
        print("Full audio conversion features will be available.")
    else:
        print("ffmpeg: ✗ Not installed")
        print("For full audio conversion features, please install ffmpeg:")
        print("- Windows: Download from https://ffmpeg.org/download.html")
        print("- macOS: Install with Homebrew: brew install ffmpeg")
        print("- Linux: Install with your package manager (apt, yum, etc.)") 