import os
from pathlib import Path

def load_env():
    path = Path(__file__).with_name('.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#'): continue
            key, sep, value = line.partition('=')
            if sep and key.strip().replace('_','').isalnum():
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
