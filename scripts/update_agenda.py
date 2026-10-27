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
    items = []

    # Meses publicados por ARCA en formato abreviado.
    meses = {
        'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4,
        'MAY': 5, 'JUN': 6, 'JUL': 7, 'AGO': 8,
        'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12
    }

    # ---------------------------------------------------------
    # MONOTRIBUTO
    # ---------------------------------------------------------
    # El micrositio oficial publica:
    # "Próximos vencimientos OCT 20 Pago mensual"
    mono_urls = [
        'https://ftp.arca.gob.ar/monotributo/default.asp',
        'https://www.arca.gob.ar/monotributo/default.asp',
    ]

    for mono_url in mono_urls:
        try:
            mono_html = get(mono_url)
            mono_soup = BeautifulSoup(mono_html, 'html.parser')

            mono_text = ' '.join(
                re.sub(r'\s+', ' ', x.strip())
                for x in mono_soup.stripped_strings
                if x.strip()
            )
           
            print('MONO TEXTO:', repr(mono_text[-500:]))
            print('MONO CONTIENE PAGO MENSUAL:', 'pago mensual' in mono_text.lower())
            
            mono_match = re.search(
                r'(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)'
                r'\s+(\d{1,2}).{0,300}?Pago\s+mensual',
                mono_text,
                re.I | re.S
            )

            if not mono_match:
                continue

            mes_txt = mono_match.group(1).upper()
            dia = int(mono_match.group(2))
            mes = meses[mes_txt]

            # El micrositio muestra el próximo vencimiento.
            # Determinamos el año tomando como referencia la fecha actual.
            hoy = datetime.now()
            anio = hoy.year

            # Si en diciembre ARCA ya publica un vencimiento de enero,
            # corresponde al año siguiente.
            if hoy.month == 12 and mes == 1:
                anio += 1

            mono_date = iso(dia, mes, anio)

            items.append(
                dict(
                    org='ARCA',
                    cat='monotributo',
                    title='Monotributo',
                    period='Pago mensual',
                    date=mono_date,
                    rows=[
                        [
                            'Todas las terminaciones',
                            f'{dia:02d}/{mes:02d}/{anio}'
                        ]
                    ],
                    source=mono_url
                )
            )

            print(
                'ARCA Monotributo:',
                mono_date,
                '- fuente:',
                mono_url
            )

            break

        except Exception as e:
            print(
                'ARCA Monotributo error:',
                mono_url,
                '-',
                str(e)[:160]
            )

    # ---------------------------------------------------------
    # DIAGNÓSTICO IVA
    # ---------------------------------------------------------
    iva_urls = [
        'https://seti.afip.gob.ar/av/seleccionVencimientos.do',
    ]
    for iva_url in iva_urls:
        print('IVA PROBANDO URL:', iva_url)
        
        try:
            iva_html = get(iva_url)
            iva_soup = BeautifulSoup(iva_html, 'html.parser')

            iva_text = ' '.join(
                re.sub(r'\s+', ' ', x.strip())
                for x in iva_soup.stripped_strings
                if x.strip()
            )

            print(
                'IVA INTENTO:',
                iva_url,
                '- caracteres:',
                len(iva_text)
            )

            if iva_text:
                print(
                    'IVA TEXTO:',
                    repr(iva_text[:1200])
                )
                print('--- FORMULARIOS ARCA ---')

                for form in iva_soup.find_all('form'):
                    print(
                        'FORM:',
                        'action=', form.get('action'),
                        'method=', form.get('method')
                    )

                    for campo in form.find_all(['input', 'select', 'button']):
                        print(
                            'CAMPO:',
                            campo.name,
                            'name=', campo.get('name'),
                            'value=', campo.get('value'),
                            'type=', campo.get('type')
                        )

                        if campo.name == 'select':
                            for opcion in campo.find_all('option'):
                                print(
                                    'OPCION:',
                                    'value=', opcion.get('value'),
                                    'texto=', opcion.get_text(' ', strip=True)
                                )

                print('--- FIN FORMULARIOS ARCA ---')
                for a in iva_soup.find_all('a', href=True):
                    label = a.get_text(' ', strip=True)
                    href = urljoin(iva_url, a['href'])

                    print(
                        'ARCA LINK:',
                        label[:120],
                        '=>',
                        href
                    )

        except Exception as e:
            print(
                'IVA ERROR:',
                iva_url,
                '-',
                str(e)[:160]
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
