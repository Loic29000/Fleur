"""Point d'entrée de FleurAnalyse.exe : ouvre directement l'application d'analyse."""

import sys

from fleur.cli import main

if __name__ == "__main__":
    sys.exit(main(["analyse"] + sys.argv[1:]))
