"""Start both localhost services, and stop both on Ctrl+C. Windows/WSL friendly."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def main():
    root=Path(__file__).resolve().parent.parent
    node=shutil.which('node')
    if not node or not (root/'node_modules/vite/bin/vite.js').is_file():
        raise SystemExit('Install Node.js and run npm ci first.')
    for port in (8000,5173):
        with socket.socket() as sock:
            try: sock.bind(('127.0.0.1',port))
            except OSError: raise SystemExit(f'Port {port} is in use. Stop the existing service first.')
    processes=[]
    try:
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.api:app',
            '--host','127.0.0.1','--port','8000'],cwd=root))
        processes.append(subprocess.Popen([node,'node_modules/vite/bin/vite.js',
            '--host','127.0.0.1','--port','5173','--strictPort'],cwd=root))
        print('\nWar Chest: http://localhost:5173\nPress Ctrl+C to stop both services.\n',flush=True)
        while all(p.poll() is None for p in processes): time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None: p.terminate()
        for p in processes:
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill()


if __name__=='__main__': main()
