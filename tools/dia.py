#!/usr/bin/env python3
"""Prepara un día a partir del GPX de OsmAnd y las fotos.

Uso:
  python3 tools/dia.py CARPETA_DEL_DIA ruta.gpx [foto1.jpg foto2.jpg ...]
        [--desfase-camara SEGUNDOS] [--titulo "Texto del mapa"]

Hace:
  - limpia el GPX (quita los ratos parado, donde el GPS «baila»),
  - separa tramos a pie / bici / vehículo por la velocidad,
  - dibuja mapa.jpg (satélite) y ruta.geojson,
  - redimensiona las fotos (1600 px, sin datos GPS) en fotos/ y las coloca
    en la ruta por su hora (o por su GPS si la hora no sirve),
  - imprime el bloque YAML (mapa, fotos, km) para pegar en entrada.yml.
"""
import argparse, math, sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from mapa import render, px

COLOR = {'pie': '#FF8A5B', 'bici': '#7BD389', 'vehiculo': '#5DB8F5'}
NOMBRE = {'pie': 'A pie', 'bici': 'En bici', 'vehiculo': 'En vehículo'}


def dist(a, b):
    R = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 2 * R * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def leer_gpx(f):
    ns = {'g': 'http://www.topografix.com/GPX/1/1'}
    pts = []
    for p in ET.parse(f).iterfind('.//g:trkpt', ns):
        t = datetime.fromisoformat(p.find('g:time', ns).text.replace('Z', '+00:00'))
        pts.append((float(p.get('lat')), float(p.get('lon')), t))
    return pts


def clasificar(pts, ventana=60):
    """Velocidad suavizada (±ventana s) → modo de cada punto ('parado', 'pie', 'bici', 'vehiculo')."""
    modos = []
    j0 = j1 = 0
    for i, p in enumerate(pts):
        while (p[2] - pts[j0][2]).total_seconds() > ventana:
            j0 += 1
        while j1 < len(pts) - 1 and (pts[j1 + 1][2] - p[2]).total_seconds() <= ventana:
            j1 += 1
        dt = (pts[j1][2] - pts[j0][2]).total_seconds() or 1
        # desplazamiento neto: si el GPS baila en el sitio, el neto es casi cero
        v = dist(pts[j0], pts[j1]) / dt * 3.6
        modos.append('parado' if v < 1.5 else 'pie' if v < 7.5 else 'bici' if v < 18 else 'vehiculo')
    # Une huecos cortos (semáforos, paradas de bus) con el modo de alrededor
    for _ in range(2):
        i = 0
        while i < len(modos):
            j = i
            while j < len(modos) and modos[j] == modos[i]:
                j += 1
            dur = (pts[j - 1][2] - pts[i][2]).total_seconds()
            if 0 < i and j < len(modos) and dur < 180 and modos[i - 1] == modos[j]:
                for k in range(i, j):
                    modos[k] = modos[i - 1]
            i = j
    return modos


def tramos(pts, modos):
    out, cur = [], None
    for p, m in zip(pts, modos):
        if m == 'parado':
            cur = None
            continue
        if not cur or cur['modo'] != m:
            cur = {'modo': m, 'pts': [out[-1]['pts'][-1]] if out and out[-1]['pts'] and cur else []}
            out.append(cur)
        cur['pts'].append(p)
    tr = [t for t in out if len(t['pts']) > 2]
    for t in tr:
        t['km'] = sum(dist(t['pts'][i], t['pts'][i + 1]) for i in range(len(t['pts']) - 1)) / 1000
    tr = [t for t in tr if t['km'] > 0.05]
    # Tramos «bici» cortos suelen ser un vehículo arrancando o frenando: van con el vecino más largo
    for i, t in enumerate(tr):
        if t['modo'] == 'bici' and t['km'] < 1:
            vec = [v for v in (tr[i - 1] if i else None, tr[i + 1] if i + 1 < len(tr) else None) if v and v['modo'] != 'bici']
            if vec:
                t['modo'] = max(vec, key=lambda v: v['km'])['modo']
    # Une tramos seguidos del mismo modo
    unidos = []
    for t in tr:
        if unidos and unidos[-1]['modo'] == t['modo'] and unidos[-1]['pts'][-1] == t['pts'][0]:
            unidos[-1]['pts'] += t['pts'][1:]
            unidos[-1]['km'] += t['km']
        else:
            unidos.append(t)
    return unidos


def exif_foto(f):
    im = Image.open(f)
    ex = im.getexif()
    t = ex.get_ifd(0x8769).get(36867) or ex.get(306)
    gps = ex.get_ifd(0x8825)
    ll = None
    if gps and 2 in gps and 4 in gps:
        g = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        ll = (g(gps[2]) * (-1 if gps.get(1) == 'S' else 1), g(gps[4]) * (-1 if gps.get(3) == 'W' else 1))
    return (datetime.strptime(t, '%Y:%m:%d %H:%M:%S') if t else None), ll, ex.get_ifd(0x8769).get(36881)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('carpeta'); ap.add_argument('gpx'); ap.add_argument('fotos', nargs='*')
    ap.add_argument('--desfase-camara', type=float, default=0, help='segundos a sumar a la hora de la cámara')
    ap.add_argument('--zona', default='+07:00', help='zona horaria de las fotos sin zona (Vietnam +07:00)')
    ap.add_argument('--titulo', default='')
    ap.add_argument('--hora-foto', action='append', default=[], metavar='N=HH:MM',
                    help='hora de una foto sin datos (p. ej. 2=08:35), en la zona indicada')
    a = ap.parse_args()
    carpeta = Path(a.carpeta); (carpeta / 'fotos').mkdir(parents=True, exist_ok=True)

    pts = leer_gpx(a.gpx)
    modos = clasificar(pts)
    tr = tramos(pts, modos)
    km = {}
    for t in tr:
        km[t['modo']] = km.get(t['modo'], 0) + t['km']

    segs = [([(p[1], p[0]) for p in t['pts']], COLOR[t['modo']]) for t in tr]
    ley = tuple((f"{NOMBRE[m]}: {v:.1f} km".replace('.', ','), COLOR[m]) for m, v in km.items())
    img = render(segs, 'sat', titulo=a.titulo, leyenda=ley, atrib='Imágenes © Esri, Maxar, Earthstar Geographics')
    z, x0, y0, W, H = img.proyeccion
    img.save(carpeta / 'mapa.jpg', quality=85)
    gj = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'modo': t['modo'], 'km': round(t['km'], 2)},
         'geometry': {'type': 'LineString', 'coordinates': [[round(p[1], 6), round(p[0], 6)] for p in t['pts']]}}
        for t in tr]}
    (carpeta / 'ruta.geojson').write_text(json.dumps(gj))

    # Fotos
    h, m = int(a.zona[1:3]), int(a.zona[4:6])
    tz = timezone(timedelta(hours=h, minutes=m) * (-1 if a.zona[0] == '-' else 1))
    fotos = []
    for i, f in enumerate(a.fotos, 1):
        t, ll, offset = exif_foto(f)
        manual = dict(x.split('=') for x in a.hora_foto).get(str(i))
        if manual:
            hh, mm = map(int, manual.split(':'))
            t, offset = pts[0][2].astimezone(tz).replace(hour=hh, minute=mm, second=0, tzinfo=None), None
        lugar = None
        if t:
            if offset:
                t = t.replace(tzinfo=datetime.strptime(offset, '%z').tzinfo)
            else:
                t = t.replace(tzinfo=tz)
            t += timedelta(seconds=a.desfase_camara)
            cerca = min(pts, key=lambda p: abs((p[2] - t).total_seconds()))
            if abs((cerca[2] - t).total_seconds()) < 900:
                lugar = (cerca[0], cerca[1])
        if not lugar and ll:
            lugar = ll
        im = ImageOps.exif_transpose(Image.open(f)).convert('RGB')
        im.thumbnail((1600, 1600))
        nombre = f'fotos/{i:02d}.jpg'
        im.save(carpeta / nombre, quality=82, optimize=True, progressive=True)   # sin EXIF
        d = {'n': i, 'archivo': nombre, 'hora': t.astimezone(tz).strftime('%H:%M') if t else '', 'pie': ''}
        if im.height > im.width:
            d['vertical'] = True
        if lugar:
            X, Y = px(lugar[1], lugar[0], z)
            d.update(lat=round(lugar[0], 6), lon=round(lugar[1], 6),
                     x=round((X - x0) / W * 100, 1), y=round((Y - y0) / H * 100, 1))
        fotos.append(d)

    # Numera las fotos por orden cronológico (las que no tienen hora, al final)
    fotos.sort(key=lambda d: (d['hora'] == '', d['hora']))
    for n, d in enumerate(fotos, 1):
        nuevo = f'fotos/{n:02d}.jpg'
        if d['archivo'] != nuevo:
            (carpeta / d['archivo']).rename(carpeta / (nuevo + '.tmp'))
            d['_tmp'] = True
        d['n'], d['archivo'] = n, nuevo
    for d in fotos:
        if d.pop('_tmp', False):
            (carpeta / (d['archivo'] + '.tmp')).rename(carpeta / d['archivo'])

    est_km = {'pie': round(km.get('pie', 0), 1), 'bici': round(km.get('bici', 0), 1)}
    veh = round(km.get('vehiculo', 0), 1)
    print('# --- pegar en entrada.yml ---')
    print(f"mapa: {{imagen: mapa.jpg, ruta: ruta.geojson, km_pie: {est_km['pie']}, km_vehiculo: {veh}}}")
    print('fotos:')
    for d in fotos:
        print('  - ' + json.dumps(d, ensure_ascii=False))
    print(f"# km: a pie {est_km['pie']}, bici {est_km['bici']}, vehículo {veh} (repartir entre coche/bus/barco)")
    print(f"# pasos estimados a pie: {round(est_km['pie'] * 1300)}")
    sin = [d['n'] for d in fotos if 'lat' not in d]
    if sin:
        print(f"# OJO: fotos sin hora ni GPS útiles, sin colocar en la ruta: {sin}")


if __name__ == '__main__':
    main()
