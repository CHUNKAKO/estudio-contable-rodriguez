#!/usr/bin/env python3
"""Actualiza agenda_fiscal.json desde páginas oficiales ARCA y ARBA.
Diseñado para ejecución diaria. Conserva el último JSON válido si una fuente cambia o falla.
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'agenda_fiscal.json'
UA='EstudioRodriguez-AgendaFiscal/4.3 (+sitio institucional; consulta fuentes publicas oficiales)'
S=requests.Session(); S.headers.update({'User-Agent':UA})
TIMEOUT=25

def get(url):
    r=S.get(url,timeout=TIMEOUT); r.raise_for_status(); return r.text

def iso(d,m,y): return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'
def dmy_to_iso(x):
    m=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})',x)
    return iso(m.group(1),m.group(2),m.group(3)) if m else None

def arca_home():
    # La portada simple puede devolver cuerpo vacío a GitHub Actions.
    # Probamos primero el landing oficial y dejamos alternativas oficiales.
    urls = [
    'https://ftp.arca.gob.ar/',
    'https://ftp.arca.gob.ar/landing/default.asp',
    'https://arca.gob.ar/landing/default.asp',
    'https://www.arca.gob.ar/landing/default.asp',
    'https://arca.gob.ar/',
]

    soup = None
    source_url = None

    for url in urls:
        try:
            html = get(url)
            candidate = BeautifulSoup(html, 'html.parser')
            candidate_text = ' '.join(candidate.stripped_strings)

            print(
                'ARCA intento:',
                url,
                '- caracteres:',
                len(candidate_text)
            )

            if len(candidate_text) > 200:
                soup = candidate
                source_url = url
                print('ARCA fuente seleccionada:', source_url)
                print('ARCA contenido recibido:', candidate_text[:2000])
                print('--- ENLACES ARCA ---')
                for a in candidate.find_all('a', href=True):
                    print('ARCA LINK:', a.get_text(' ', strip=True)[:80], '=>', urljoin(url, a['href']))
                print('--- FIN ENLACES ARCA ---')
                break

        except Exception as e:
            print('ARCA error:', url, '-', str(e)[:160])
            continue

    if soup is None:
        return []

    # Diagnóstico del micrositio oficial de Monotributo
    print('>>> INICIANDO PRUEBA MONOTRIBUTO <<<')
    try:
        mono_url = 'https://ftp.arca.gob.ar/monotributo/default.asp'
        mono_html = get(mono_url)
        mono_soup = BeautifulSoup(mono_html, 'html.parser')
        mono_text = ' '.join(mono_soup.stripped_strings)

        print('--- DIAGNOSTICO MONOTRIBUTO ---')
        print('MONO caracteres:', len(mono_text))
        print('MONO contenido:', mono_text[:2000])

        for a in mono_soup.find_all('a', href=True):
            label = a.get_text(' ', strip=True)
            href = urljoin(mono_url, a['href'])

            if (
                'venc' in label.lower()
                or 'calend' in label.lower()
                or 'pago' in label.lower()
                or 'fecha' in label.lower()
                or 'venc' in href.lower()
                or 'calend' in href.lower()
            ):
                print('MONO LINK:', label[:100], '=>', href)

        print('--- FIN DIAGNOSTICO MONOTRIBUTO ---')

    except Exception as e:
        print('MONO ERROR:', str(e)[:200])
    
    
    text = '\n'.join(
        re.sub(r'\s+', ' ', x.strip())
        for x in soup.stripped_strings
        if x.strip()
    )

    items = []

    specs = [
        (
            'iva',
            'IVA y Libro IVA Digital',
            [
                r'IVA y Libro (?:de )?IVA Digital',
                r'IVA Simple',
            ],
            'Presentación y pago de declaración jurada'
        ),
        (
            'monotributo',
            'Monotributo',
            [r'Monotributo'],
            'Pago mensual'
        ),
        (
            'ganancias',
            'Ganancias',
            [
                r'Ganancias',
                r'Impuesto a las Ganancias',
            ],
            'Presentación y/o pago'
        ),
        (
            'sicore',
            'SICORE',
            [
                r'SICORE',
                r'Sistema de Control de Retenciones',
            ],
            'Retenciones y percepciones'
        ),
        (
            'cargas',
            'Seguridad Social',
            [
                r'Seguridad Social',
                r'Cargas Sociales',
                r'Empleadores',
            ],
            'Obligaciones de Seguridad Social'
        ),
    ]

    date_pattern = r'\b(\d{1,2})/(\d{1,2})/(202[6-9])\b'

    for cat, title, aliases, period in specs:
        positions = []

        for alias in aliases:
            positions.extend(
                m.start()
                for m in re.finditer(alias, text, re.I)
            )

        if not positions:
            continue

        rows = []

        for pos in sorted(set(positions)):
            # Buscamos principalmente hacia adelante desde el título
            # para evitar capturar fechas de la obligación anterior.
            seg = text[pos:min(len(text), pos + 1800)]

            # Cronogramas habituales por terminación de CUIT.
            for label in [
                '0-1', '2-3', '4-5', '6-7', '8-9',
                '0-2', '3-5'
            ]:
                m = re.search(
                    re.escape(label) +
                    r'.{0,180}?' +
                    date_pattern,
                    seg,
                    re.I | re.S
                )

                if m:
                    rows.append([
                        f'CUIT {label}',
                        f'{m.group(1)}/{m.group(2)}/{m.group(3)}'
                    ])

            # Obligaciones con vencimiento único para todos.
            if not rows:
                m = re.search(
                    r'(?:Todos|Todas|Todas las terminaciones)'
                    r'.{0,180}?' +
                    date_pattern,
                    seg,
                    re.I | re.S
                )

                if m:
                    rows.append([
                        'Todas las terminaciones',
                        f'{m.group(1)}/{m.group(2)}/{m.group(3)}'
                    ])

            # Último recurso: primera fecha explícita cercana al título.
            if not rows:
                m = re.search(date_pattern, seg)

                if m:
                    rows.append([
                        'Todas las terminaciones',
                        f'{m.group(1)}/{m.group(2)}/{m.group(3)}'
                    ])

            if rows:
                break

        if not rows:
            continue

        # Eliminar duplicados.
        unique_rows = []
        seen = set()

        for row in rows:
            key = tuple(row)
            if key not in seen:
                seen.add(key)
                unique_rows.append(row)

        valid_dates = [
            dmy_to_iso(row[1])
            for row in unique_rows
            if dmy_to_iso(row[1])
        ]

        if not valid_dates:
            continue

        items.append(
            dict(
                org='ARCA',
                cat=cat,
                title=title,
                period=period,
                date=min(valid_dates),
                rows=unique_rows,
                source=source_url
            )
        )

    return items

def arba_iibb_local():
    url='https://web.arba.gov.ar/vencimientos-contribuyentes-locales'
    soup=BeautifulSoup(get(url),'html.parser')
    items=[]
    # Parse tables by extracting rows containing CUIT ranges and dates; group by date column.
    tables=soup.find_all('table')
    for table in tables:
        rows=[]
        for tr in table.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'])]
            if cells: rows.append(cells)
        if not rows: continue
        header=rows[0]
        data=[r for r in rows[1:] if r and re.match(r'^[0-9]\s*[-a]\s*[0-9]$',r[0],re.I)]
        if not data: continue
        maxcols=max(len(r) for r in data)
        for col in range(1,maxcols):
            rr=[]
            for r in data:
                if len(r)>col:
                    dm=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})',r[col])
                    if dm: rr.append([f'CUIT {r[0]}',dm.group(0)])
            if rr:
                date=min(dmy_to_iso(x[1]) for x in rr)
                label=header[col] if col<len(header) else f'Anticipo {col}'
                items.append(dict(org='ARBA',cat='iibb',title='Ingresos Brutos - Locales',period=label,date=date,rows=rr,source=url))
        break
    return items

def arba_convenio():
    url='https://web.arba.gov.ar/vencimientos-contribuyentes-convenio'
    soup=BeautifulSoup(get(url),'html.parser'); items=[]
    for table in soup.find_all('table'):
        rows=[[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'])] for tr in table.find_all('tr')]
        rows=[r for r in rows if r]
        # ARBA page generally has one row per anticipo: N, month, 4 dates
        for r in rows:
            dates=re.findall(r'\d{1,2}/\d{1,2}/\d{4}',' '.join(r))
            if len(dates)>=4:
                rr=[[f'CUIT {lab}',d] for lab,d in zip(['0-2','3-5','6-7','8-9'],dates[:4])]
                date=min(dmy_to_iso(x[1]) for x in rr)
                period=' · '.join(r[:2]) if len(r)>=2 else 'Anticipo'
                items.append(dict(org='ARBA',cat='convenio',title='Convenio Multilateral',period=period,date=date,rows=rr,source=url))
        if items: break
    return items

def arba_property():
    url='https://web.arba.gov.ar/vencimientos'
    soup=BeautifulSoup(get(url),'html.parser')
    text='\n'.join(soup.stripped_strings)
    items=[]
    # Parse date headings followed by named taxes. Keep 2026 scope.
    # HTML headings make this more reliable than raw regex.
    current=None
    for el in soup.find_all(['h2','h3','h4','p','li']):
        t=el.get_text(' ',strip=True)
        m=re.search(r'\b(\d{1,2})\s+(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)\b',t,re.I)
        if m:
            months={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
            current=iso(m.group(1),months[m.group(2).lower()],2026); continue
        if not current: continue
        tl=t.lower()
        if 'inmobiliario' in tl or 'automotor' in tl:
            if 'automotor' in tl: cat='automotor'; title='Automotor / Patentes'
            else: cat='inmobiliario'; title=t.split('. Cuota')[0].strip() or 'Impuesto Inmobiliario'
            q=re.search(r'Cuota\s+([^\n]+)',t,re.I)
            period='Cuota '+q.group(1).strip() if q else 'Vencimiento'
            items.append(dict(org='ARBA',cat=cat,title=title,period=period,date=current,rows=[['Vencimiento',datetime.fromisoformat(current).strftime('%d/%m/%Y')]],source=url))
    # de-dup
    uniq={ (x['cat'],x['title'],x['period'],x['date']):x for x in items }
    return list(uniq.values())

def load_previous():
    try: return json.loads(OUT.read_text(encoding='utf-8')).get('items',[])
    except Exception: return []

def main():
    previous=load_previous(); allitems=[]; status={}
    for name,fn in [('ARCA',arca_home),('ARBA_IIBB',arba_iibb_local),('ARBA_CONVENIO',arba_convenio),('ARBA_PATRIMONIALES',arba_property)]:
        try:
            got=fn(); status[name]={'ok':bool(got),'count':len(got)}
            allitems.extend(got)
        except Exception as e:
            status[name]={'ok':False,'error':str(e)[:180],'count':0}
    # Preserve previous categories when a parser/source temporarily fails.
    if previous:
        present={(x.get('org'),x.get('cat')) for x in allitems}
        for x in previous:
            if (x.get('org'),x.get('cat')) not in present: allitems.append(x)
    # Safety validation: never publish an empty or absurd agenda.
    if len(allitems)<3:
        print('ERROR: actualización insuficiente; se conserva el último archivo válido.',file=sys.stderr); return 2
    allitems.sort(key=lambda x:(x.get('date','9999'),x.get('org',''),x.get('cat','')))
    payload={'meta':{'version':'4.3','generated_at':datetime.now(timezone.utc).isoformat(),'sources':status,'policy':'Fuentes oficiales; último dato válido se conserva ante fallos de extracción.'},'items':allitems}
    tmp=OUT.with_suffix('.json.tmp'); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(OUT)
    print(f'OK: {len(allitems)} vencimientos guardados en {OUT}')
    for k,v in status.items(): print(k,v)
    return 0
if __name__=='__main__': raise SystemExit(main())
