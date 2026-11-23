"""Point d'entrée de FleurAnalyse.exe : ouvre directement l'application d'analyse.

Les options générales (--db, --history) et celles de l'analyse (--sans-import,
--navigateur) sont acceptées dans n'importe quel ordre.
"""

import sys

from fleur.cli import main

SUB_OPTIONS = ("--sans-import", "--navigateur")


def build_argv(argv: list[str]) -> list[str]:
    sub = [a for a in argv if a in SUB_OPTIONS]
    rest = [a for a in argv if a not in SUB_OPTIONS and a != "analyse"]
    return rest + ["analyse"] + sub


if __name__ == "__main__":
    try:
        sys.exit(main(build_argv(sys.argv[1:])))
    except SystemExit:
        raise
    except Exception as exc:  # programme sans console : on montre l'erreur
        import logging
        logging.getLogger("fleur").exception("FleurAnalyse : erreur au démarrage")
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            _app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, "Fleur analyse", f"Erreur au démarrage :\n{exc}")
        except Exception:
            pass
        sys.exit(1)
