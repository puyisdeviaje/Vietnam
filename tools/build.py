#!/usr/bin/env python3
"""Genera el blog estático.

Uso:
  python3 tools/build.py               # publica: dias/*/entrada.yml con publicado: true
  python3 tools/build.py --vista DIR   # vista previa con todo (también lo no publicado) en DIR

Cada día vive en su carpeta (dias/05-22-dic-.../) con entrada.yml y, cuando
tenga contenido, mapa.jpg, ruta.geojson y fotos/. Solo se genera la página de
los días con `publicado: true`; el resto sale en gris en la portada.
"""
import argparse, shutil
from pathlib import Path
from datetime import date
import yaml, markdown
from markupsafe import Markup
from jinja2 import Environment, FileSystemLoader

RAIZ = Path(__file__).resolve().parent.parent
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
MESES_L = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
           'septiembre', 'octubre', 'noviembre', 'diciembre']
DIAS_L = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def cargar(site, todo: bool):
    cal = {c['dia']: c for c in site['calendario']}
    entradas = []
    for f in sorted((RAIZ / 'dias').glob('*/entrada.yml')):
        e = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
        if not e.get('publicado') and not todo:
            continue
        c = cal.get(e['dia'], {})
        e['_carpeta'] = f.parent
        e['ruta_url'] = f"dias/{f.parent.name}/"
        d = e['fecha'] if isinstance(e['fecha'], date) else date.fromisoformat(str(e['fecha']))
        e['fecha_corta'] = f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"
        e.setdefault('fecha_texto', f"{DIAS_L[d.weekday()]} {d.day} de {MESES_L[d.month - 1]}")
        e['titulo'] = e.get('titulo') or c.get('titulo', '')
        e['fotos'] = e.get('fotos') or []
        e['cuerpo'] = e.get('cuerpo') or []
        e['fotos_mapa'] = [{k: x.get(k) for k in ('n', 'archivo', 'hora', 'pie', 'lat', 'lon')}
                           for x in e['fotos'] if x.get('lat') is not None]
        # Imagen de la tarjeta/compartir: la del día si existe; si no, la de la cuadrícula
        if e.get('tarjeta'):
            e['imagen_url'] = e['ruta_url'] + e['tarjeta']
        elif e.get('mapa'):
            e['imagen_url'] = e['ruta_url'] + e['mapa']['imagen']
        else:
            e['imagen_url'] = c.get('foto', '')
        # Estadísticas del día (los km a pie del mapa cuentan si no se indican)
        est = e.get('estadisticas') or {}
        km = est.get('km') or {}
        mapa = e.get('mapa') or {}
        if not km.get('pie') and mapa.get('km_pie'):
            km['pie'] = mapa['km_pie']
        est['km'] = km
        est['pasos'] = est.get('pasos') or 0
        est['contadores'] = est.get('contadores') or {}
        e['estadisticas'] = est
        entradas.append(e)
    entradas.sort(key=lambda e: e['dia'])
    return entradas


def totales(site, entradas):
    t = {'km': {}, 'contadores': {}, 'dias': []}
    for tr in site['transportes']:
        t['km'][tr['clave']] = sum(num(e['estadisticas']['km'].get(tr['clave'])) for e in entradas)
    t['km_total'] = sum(t['km'].values())
    t['pasos'] = sum(num(e['estadisticas']['pasos']) for e in entradas)
    for co in site['contadores']:
        t['contadores'][co['clave']] = sum(num(e['estadisticas']['contadores'].get(co['clave'])) for e in entradas)
    t['usados'] = [tr for tr in site['transportes'] if t['km'][tr['clave']] > 0]
    for e in entradas:
        t['dias'].append({'e': e, 'km': sum(num(v) for v in e['estadisticas']['km'].values()),
                          'pasos': num(e['estadisticas']['pasos'])})
    return t


def entorno():
    env = Environment(loader=FileSystemLoader(RAIZ / 'tools' / 'templates'), autoescape=True)
    env.filters['md'] = lambda t: Markup(markdown.markdown(t or ''))
    env.filters['km'] = lambda v: f"{float(v):.1f} km".replace('.', ',')
    env.filters['entero'] = lambda v: f"{round(float(v or 0)):,}".replace(',', '.')
    env.filters['km_entero'] = env.filters['entero']
    env.filters['foto_por_n'] = lambda n, fotos: next(f for f in fotos if f['n'] == n)
    return env


def construir(destino: Path, vista: bool):
    site = yaml.safe_load((RAIZ / 'site.yml').read_text(encoding='utf-8'))
    entradas = cargar(site, vista)
    tot = totales(site, entradas)
    env = entorno()
    base = site['url_base']
    if vista:
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(RAIZ / 'assets', destino / 'assets')
    comun = dict(site=site, totales=tot)

    # Portada: cuadrícula de días
    por_dia = {e['dia']: e for e in entradas}
    calendario = []
    for c in site['calendario']:
        c = dict(c)
        c['entrada'] = por_dia.get(c['dia'])
        usa_propia = c['entrada'] and not c.get('fija') and c['entrada'].get('tarjeta')
        c['imagen'] = c['entrada']['imagen_url'] if usa_propia else c['foto']
        calendario.append(c)
    html = env.get_template('index.html').render(
        **comun, entradas=entradas, calendario=calendario, raiz='',
        titulo_pagina=site['titulo'], descripcion=site['intro'],
        og_imagen=base + 'assets/img/compartir.jpg', og_url=base)
    (destino / 'index.html').write_text(html, encoding='utf-8')

    # Estadísticas
    (destino / 'estadisticas').mkdir(parents=True, exist_ok=True)
    html = env.get_template('estadisticas.html').render(
        **comun, raiz='../', titulo_pagina=f"Estadísticas — {site['titulo']}",
        descripcion='El viaje en números', og_imagen=base + 'assets/img/compartir.jpg',
        og_url=base + 'estadisticas/')
    (destino / 'estadisticas' / 'index.html').write_text(html, encoding='utf-8')

    # Días
    for i, e in enumerate(entradas):
        salida = destino / e['ruta_url']
        if vista:
            shutil.copytree(e['_carpeta'], salida, dirs_exist_ok=True)
        html = env.get_template('entrada.html').render(
            **comun, e=e, raiz='../../',
            anterior=entradas[i - 1] if i > 0 else None,
            siguiente=entradas[i + 1] if i + 1 < len(entradas) else None,
            titulo_pagina=f"Día {e['dia']} · {e['titulo']} — {site['titulo']}",
            descripcion=e.get('extracto') or f"{e['fecha_texto']} · {e.get('lugar', '')}",
            og_imagen=base + e['imagen_url'], og_url=base + e['ruta_url'])
        (salida / 'index.html').write_text(html, encoding='utf-8')
    # Quita las páginas de días que ya no están publicados
    if not vista:
        publicados = {e['_carpeta'].name for e in entradas}
        for p in (RAIZ / 'dias').glob('*/index.html'):
            if p.parent.name not in publicados:
                p.unlink()
    print(f"{len(entradas)} días publicados → {destino}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--vista', type=Path, help='carpeta de vista previa (incluye lo no publicado)')
    a = ap.parse_args()
    construir(a.vista or RAIZ, bool(a.vista))
