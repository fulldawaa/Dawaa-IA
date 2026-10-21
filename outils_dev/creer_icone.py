"""Génère assets/raya.png et assets/raya.ico (bulle de dialogue sur fond vert)."""
from pathlib import Path

from PIL import Image, ImageDraw

RACINE = Path(__file__).resolve().parent.parent
TAILLE = 512
VERT = (31, 122, 99, 255)
BLANC = (255, 255, 255, 255)

img = Image.new("RGBA", (TAILLE, TAILLE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, TAILLE - 16, TAILLE - 16), radius=112, fill=VERT)
# Bulle de dialogue
d.rounded_rectangle((104, 120, 408, 336), radius=64, fill=BLANC)
d.polygon([(170, 320), (150, 410), (250, 330)], fill=BLANC)
# Ondes sonores dans la bulle
for i, h in enumerate((44, 92, 120, 92, 44)):
    x = 178 + i * 40
    d.rounded_rectangle((x, 228 - h // 2, x + 18, 228 + h // 2), radius=9, fill=VERT)

dossier = RACINE / "assets"
dossier.mkdir(exist_ok=True)
img.save(dossier / "raya.png")
img.resize((128, 128), Image.LANCZOS).save(RACINE / "raya" / "ui" / "raya.png")
img.save(dossier / "raya.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icônes créées dans", dossier)
