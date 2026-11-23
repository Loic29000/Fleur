"""Point d'entrée de FleurAnalyse.exe : ouvre directement l'application d'analyse.

Les options générales (--db, --history) et celles de l'analyse (--sans-import,
--navigateur) sont acceptées dans n'importe quel ordre.
"""

import sys

from fleur.cli import main

SUB_OPTIONS = ("--sans-import", "--navigateur")
SUB_WITH_VALUE = ("--onglet",)


def build_argv(argv: list[str]) -> list[str]:
    sub, rest, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a in SUB_OPTIONS:
            sub.append(a)
        elif a in SUB_WITH_VALUE and i + 1 < len(argv):
            sub += [a, argv[i + 1]]
            i += 1
        elif a != "analyse":
            rest.append(a)
        i += 1
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
