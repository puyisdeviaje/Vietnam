#!/usr/bin/env python3
"""Dibuja el mapa de un vuelo (arcos de círculo máximo) y su ruta.geojson.

Uso: python3 tools/vuelo.py CARPETA_DEL_DIA BCN AUH HAN "Título"
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mapa import render, px
from PIL import ImageDraw, ImageFont

AEROPUERTOS = {
    'BCN': ('Barcelona', 2.0785, 41.2971),
    'AUH': ('Abu Dabi', 54.6511, 24.4330),
    'HAN': ('Hanói', 105.8072, 21.2212),
    'DAD': ('Da Nang', 108.1992, 16.0439),
}


def gc_km(a, b):
    (lo1, la1), (lo2, la2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def arco(a, b, n=80):
    (lo1, la1), (lo2, la2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    d = gc_km(a, b) / 6371
    pts = []
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = A * math.cos(la1) * math.cos(lo1) + B * math.cos(la2) * math.cos(lo2)
        y = A * math.cos(la1) * math.sin(lo1) + B * math.cos(la2) * math.sin(lo2)
        z = A * math.sin(la1) + B * math.sin(la2)
        pts.append((math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y)))))
    return pts


def main(carpeta, codigos, titulo):
    carpeta = Path(carpeta)
    pos = [AEROPUERTOS[c][1:] for c in codigos]
    tramos = [arco(pos[i], pos[i + 1]) for i in range(len(pos) - 1)]
    km = sum(gc_km(pos[i], pos[i + 1]) for i in range(len(pos) - 1))
    nombres = ' → '.join(AEROPUERTOS[c][0] for c in codigos)
    img = render([(t, '#F2B33D') for t in tramos], 'sat', titulo=titulo,
                 leyenda=((f'En avión: {round(km):,} km'.replace(',', '.'), '#F2B33D'),),
                 atrib='Imágenes © Esri, Maxar, Earthstar Geographics', pad=170)
    # Etiquetas de los aeropuertos
    W, H = img.size
    allp = [p for t in tramos for p in t]
    for z in range(18, 1, -1):
        xs, ys = zip(*[px(lo, la, z) for lo, la in allp])
        if max(xs) - min(xs) <= W - 340 and max(ys) - min(ys) <= H - 340:
            break
    x0, y0 = (max(xs) + min(xs)) / 2 - W / 2, (max(ys) + min(ys)) / 2 - H / 2
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
    for c, (lo, la) in zip(codigos, pos):
        x, y = px(lo, la, z)
        x, y = x - x0, y - y0
        d.ellipse((x - 12, y - 12, x + 12, y + 12), fill='white')
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill='#F2B33D')
        t = AEROPUERTOS[c][0]
        tw = d.textlength(t, font=f)
        tx = min(max(x - tw / 2, 10), W - tw - 10)
        d.rounded_rectangle((tx - 10, y + 20, tx + tw + 10, y + 62), 8, fill=(15, 20, 18))
        d.text((tx, y + 24), t, font=f, fill='white')
    img.save(carpeta / 'mapa.jpg', quality=85)
    gj = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'modo': 'avion'},
         'geometry': {'type': 'LineString', 'coordinates': [[round(a, 4), round(b, 4)] for a, b in t]}} for t in tramos]}
    (carpeta / 'ruta.geojson').write_text(json.dumps(gj))
    print(f'{nombres}: {km:.0f} km')
    return km


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:-1], sys.argv[-1])
