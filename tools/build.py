#!/usr/bin/env python3
"""Genera el blog estático.

Uso:
  python3 tools/build.py               # publica: dias/*/entrada.yml con publicado: true
  python3 tools/build.py --vista DIR   # vista previa con borradores/ incluidos, en DIR

Cada día vive en su carpeta (dias/04-hoi-an/) con entrada.yml, mapa.jpg,
ruta.geojson y fotos/. Los borradores van en borradores/ (no se suben a GitHub).
"""
import argparse, shutil, sys
from pathlib import Path
from datetime import date
import yaml, markdown
from jinja2 import Environment, FileSystemLoader, pass_context

RAIZ = Path(__file__).resolve().parent.parent
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
MESES_L = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
           'septiembre', 'octubre', 'noviembre', 'diciembre']
DIAS_L = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def cargar(carpeta: Path, incluir_borradores: bool):
    entradas = []
    for f in sorted(carpeta.glob('*/entrada.yml')):
        e = yaml.safe_load(f.read_text(encoding='utf-8'))
        if not e.get('publicado') and not incluir_borradores:
            continue
        e['_carpeta'] = f.parent
        d = e['fecha'] if isinstance(e['fecha'], date) else date.fromisoformat(str(e['fecha']))
        e['fecha_corta'] = f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"
        e.setdefault('fecha_texto', f"{DIAS_L[d.weekday()]} {d.day} de {MESES_L[d.month - 1]}")
        e.setdefault('fotos', [])
        e.setdefault('cuerpo', [])
        e['fotos_mapa'] = [
            {k: f.get(k) for k in ('n', 'archivo', 'hora', 'pie', 'lat', 'lon')}
            for f in e['fotos'] if f.get('lat') is not None]
        e.setdefault('tarjeta', e['mapa']['imagen'] if e.get('mapa') else '')
        entradas.append(e)
    return entradas


def entorno():
    env = Environment(loader=FileSystemLoader(RAIZ / 'tools' / 'templates'), autoescape=True)
    env.filters['md'] = lambda t: __import__('markupsafe').Markup(markdown.markdown(t or ''))
    env.filters['km'] = lambda v: f"{float(v):.1f} km".replace('.', ',')
    env.filters['foto_por_n'] = lambda n, fotos: next(f for f in fotos if f['n'] == n)
    return env


def construir(destino: Path, vista: bool):
    site = yaml.safe_load((RAIZ / 'site.yml').read_text(encoding='utf-8'))
    entradas = cargar(RAIZ / 'dias', vista)
    if vista:
        entradas += cargar(RAIZ / 'borradores', True)
    entradas.sort(key=lambda e: e['dia'])
    for e in entradas:
        e['ruta_url'] = f"dias/{e['_carpeta'].name}/"

    env = entorno()
    base = site['url_base']
    if vista:
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(RAIZ / 'assets', destino / 'assets')
    # Portada
    html = env.get_template('index.html').render(
        site=site, entradas=entradas, raiz='',
        titulo_pagina=site['titulo'], descripcion=site['intro'],
        og_imagen=base + 'assets/img/compartir.jpg', og_url=base)
    (destino / 'index.html').write_text(html, encoding='utf-8')
    # Días
    for i, e in enumerate(entradas):
        salida = destino / e['ruta_url']
        if vista and e['_carpeta'].resolve() != salida.resolve():
            shutil.copytree(e['_carpeta'], salida, dirs_exist_ok=True)
        html = env.get_template('entrada.html').render(
            site=site, e=e, raiz='../../',
            anterior=entradas[i - 1] if i > 0 else None,
            siguiente=entradas[i + 1] if i + 1 < len(entradas) else None,
            titulo_pagina=f"Día {e['dia']} · {e['titulo']} — {site['titulo']}",
            descripcion=e.get('extracto') or f"{e['fecha_texto']} · {e['lugar']}",
            og_imagen=base + e['ruta_url'] + e['tarjeta'], og_url=base + e['ruta_url'])
        (salida / 'index.html').write_text(html, encoding='utf-8')
    print(f"{len(entradas)} entradas → {destino}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--vista', type=Path, help='carpeta de vista previa (incluye borradores)')
    a = ap.parse_args()
    construir(a.vista or RAIZ, bool(a.vista))
