#!/usr/bin/env python3
"""Dibuja el mapa de un vuelo (arcos de círculo máximo) y su ruta.geojson.

Uso: python3 tools/vuelo.py CARPETA_DEL_DIA BCN AUH HAN "Título"
     [--antes tools/rutas/x.json] [--despues tools/rutas/x.json] [--invertir]
Las rutas por carretera (--antes/--despues) se dibujan en otro color y suman sus km.
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


def main(carpeta, codigos, titulo, antes=None, despues=None, invertir=False):
    carpeta = Path(carpeta)
    pos = [AEROPUERTOS[c][1:] for c in codigos]
    tramos = [arco(pos[i], pos[i + 1]) for i in range(len(pos) - 1)]
    km = sum(gc_km(pos[i], pos[i + 1]) for i in range(len(pos) - 1))
    nombres = ' → '.join(AEROPUERTOS[c][0] for c in codigos)
    segs = [(t, '#F2B33D') for t in tramos]
    extra = []
    for cual, f in (('antes', antes), ('despues', despues)):
        if not f:
            continue
        r = json.loads(Path(f).read_text())
        coords = [tuple(p) for p in r['coords']]
        if invertir:
            coords = coords[::-1]
        extra.append((cual, r, coords))
        if cual == 'antes':
            segs.insert(0, (coords, '#5DB8F5'))
        else:
            segs.append((coords, '#5DB8F5'))
    km_tierra = sum(r['km'] for _, r, _ in extra)
    leyenda = [(f'En avión: {round(km):,} km'.replace(',', '.'), '#F2B33D')]
    if extra:
        leyenda.append((f'En coche: {km_tierra:,} km'.replace(',', '.'), '#5DB8F5'))
    img = render(segs, 'sat', titulo=titulo, leyenda=tuple(leyenda),
                 atrib='Imágenes © Esri, Maxar, Earthstar Geographics', pad=140)
    # Etiquetas de los aeropuertos
    W, H = img.size
    allp = [p for t, _ in segs for p in t]
    for z in range(18, 1, -1):
        xs, ys = zip(*[px(lo, la, z) for lo, la in allp])
        if max(xs) - min(xs) <= W - 340 and max(ys) - min(ys) <= H - 340:
            break
    x0, y0 = (max(xs) + min(xs)) / 2 - W / 2, (max(ys) + min(ys)) / 2 - H / 2
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
    etiquetas = list(zip([AEROPUERTOS[c][0] for c in codigos], pos))
    for cual, r, coords in extra:
        ext = coords[0] if cual == 'antes' else coords[-1]
        etiquetas.append(('Zaragoza', ext))
    for t, (lo, la) in etiquetas:
        x, y = px(lo, la, z)
        x, y = x - x0, y - y0
        d.ellipse((x - 12, y - 12, x + 12, y + 12), fill='white')
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill='#F2B33D')
        tw = d.textlength(t, font=f)
        if t == 'Zaragoza':   # encima y a la izquierda, para no pisar Barcelona
            tx, ty = x - tw - 24, y - 64
        else:
            tx, ty = min(max(x - tw / 2, 10), W - tw - 10), y + 20
        d.rounded_rectangle((tx - 10, ty, tx + tw + 10, ty + 42), 8, fill=(15, 20, 18))
        d.text((tx, ty + 4), t, font=f, fill='white')
    if extra:   # recuadro ampliado con el trayecto en coche
        coords = extra[0][2]
        ins = render([(coords, '#5DB8F5')], 'sat', W=560, H=360, pad=50)
        d2 = ImageDraw.Draw(ins)
        fi = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)
        d2.rounded_rectangle((12, 12, 24 + d2.textlength('Zaragoza – aeropuerto de Barcelona', font=fi), 48), 6, fill=(15, 20, 18))
        d2.text((18, 16), 'Zaragoza – aeropuerto de Barcelona', font=fi, fill='white')
        bx, by = 40, H - 360 - 60
        d.rectangle((bx - 4, by - 4, bx + 564, by + 364), fill='white')
        img.paste(ins, (bx, by))
    img.save(carpeta / 'mapa.jpg', quality=85)
    gj = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'modo': 'avion' if col == '#F2B33D' else 'coche'},
         'geometry': {'type': 'LineString', 'coordinates': [[round(a, 4), round(b, 4)] for a, b in t]}}
        for t, col in segs]}
    (carpeta / 'ruta.geojson').write_text(json.dumps(gj))
    print(f'{nombres}: {km:.0f} km en avión, {km_tierra} km en coche')
    return km


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('carpeta'); ap.add_argument('resto', nargs='+')
    ap.add_argument('--antes'); ap.add_argument('--despues'); ap.add_argument('--invertir', action='store_true')
    a = ap.parse_args()
    main(a.carpeta, a.resto[:-1], a.resto[-1], a.antes, a.despues, a.invertir)
