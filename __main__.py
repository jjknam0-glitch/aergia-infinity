"""
python -m aergia           → start REPL
python -m aergia file.ae   → run script
python -m aergia --version → print version
"""
import sys

def main():
    args = sys.argv[1:]
    if not args:
        from .repl import REPL; REPL().run(); return
    if args[0] in ("--version", "-v"):
        from . import __version__; print(f"Æergia∞ {__version__}"); return
    if args[0] in ("--help", "-h"):
        print(__doc__); return
    from .repl import run_script; run_script(args[0])

if __name__ == "__main__":
    main()
