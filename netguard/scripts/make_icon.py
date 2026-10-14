"""Erzeugt das Programmsymbol als .ico für die Exe (wird vom Build-Skript aufgerufen)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402
from netguard.app import make_icon  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/netguard.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    icon = make_icon()
    pm = icon.pixmap(256, 256)
    if not pm.save(str(out), "ICO"):
        # Fallback: PNG, PyInstaller akzeptiert unter Windows auch PNG nicht - dann ohne Icon
        print("Icon konnte nicht als ICO gespeichert werden.")
        return 1
    print(f"Icon geschrieben: {out}")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
