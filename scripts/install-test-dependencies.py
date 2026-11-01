"""Install the application's test dependencies without optional model runtimes."""
from pathlib import Path
import subprocess
import sys
requirements = [line.strip() for line in Path('requirements.txt').read_text().splitlines()
    if line.strip() and not line.startswith('#') and not line.startswith(('rembg', 'onnxruntime'))]
subprocess.run([sys.executable, '-m', 'pip', 'install', *requirements], check=True)
