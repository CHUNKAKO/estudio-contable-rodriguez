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
                print('--- PRUEBA CONSULTA IVA ARCA ---')

                form = iva_soup.find('form')

                if form:
                    action = urljoin(iva_url, form.get('action', ''))

                    datos_iva = {
                        'fechaVDesde': '01/10/2026',
                        'fechaVHasta': '31/10/2026',
                        'terminacionCuit': 'Todos',
                        'impuestosSeleccionados': '1',
                    }

                    datos_seguridad_social = {
                        'fechaVDesde': '01/10/2026',
                        'fechaVHasta': '31/10/2026',
                        'terminacionCuit': 'Todos',
                        'impuestosSeleccionados': '2',
                    }

                    try:
                        respuesta_seguridad_social = S.post(
                            action,
                            data=datos_seguridad_social,
                            timeout=TIMEOUT
                        )
                        respuesta_seguridad_social.raise_for_status()

                        soup_seguridad_social = BeautifulSoup(
                            respuesta_seguridad_social.text,
                            'html.parser'
                        )

                        texto_seguridad_social = ' '.join(
                            re.sub(r'\s+', ' ', x.strip())
                            for x in soup_seguridad_social.stripped_strings
                            if x.strip()
                        )

                        marcador_seguridad_social = (
                            'Sujeto Empleadores. R.G. (D.G.I.) N° 3834'
                        )

                        pos_seguridad_social = texto_seguridad_social.find(
                            marcador_seguridad_social
                        )

                        if pos_seguridad_social != -1:
                            bloque_seguridad_social = texto_seguridad_social[
                                pos_seguridad_social:
                                pos_seguridad_social + 1800
                            ]

                            patron_seguridad_social = re.compile(
                                r'Presentación del formulario de declaración jurada '
                                r'e ingreso de aportes y contribuciones de la '
                                r'Seguridad Social y Obras Sociales, por el período '
                                r'devengado en:\s*'
                                r'([A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})',
                                re.I | re.S
                            )

                            match_seguridad_social = (
                                patron_seguridad_social.search(
                                    bloque_seguridad_social
                                )
                            )

                            if match_seguridad_social:
                                periodo_seguridad_social = (
                                    match_seguridad_social.group(1)
                                )

                                filas_seguridad_social = [
                                    [
                                        '0-1-2-3',
                                        match_seguridad_social.group(2)
                                    ],
                                    [
                                        '4-5-6',
                                        match_seguridad_social.group(3)
                                    ],
                                    [
                                        '7-8-9',
                                        match_seguridad_social.group(4)
                                    ],
                                ]

                                fechas_seguridad_social = [
                                    dmy_to_iso(
                                        match_seguridad_social.group(i)
                                    )
                                    for i in range(2, 5)
                                ]

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='seguridad_social',
                                        title='Cargas Sociales - SICOSS F.931',
                                        period=periodo_seguridad_social,
                                        date=min(fechas_seguridad_social),
                                        rows=filas_seguridad_social,
                                        source=iva_url
                                    )
                                )

                                print(
                                    'ARCA SEGURIDAD SOCIAL F931:',
                                    periodo_seguridad_social,
                                    filas_seguridad_social
                                )
                            else:
                                print(
                                    'ARCA SEGURIDAD SOCIAL F931: '
                                    'patrón no encontrado'
                                )
                        else:
                            print(
                                'ARCA SEGURIDAD SOCIAL F931: '
                                'bloque no encontrado'
                            )
                    
                    except Exception as e:
                        print(
                            'SEGURIDAD SOCIAL POST ERROR:',
                            str(e)[:300]
                        )                    
                    
                    datos_ganancias = {
                        'fechaVDesde': '01/10/2026',
                        'fechaVHasta': '31/10/2026',
                        'terminacionCuit': 'Todos',
                        'impuestosSeleccionados': '16',
                    }

                    try:
                        respuesta_ganancias = S.post(
                            action,
                            data=datos_ganancias,
                            timeout=TIMEOUT
                        )
                        respuesta_ganancias.raise_for_status()

                        soup_ganancias = BeautifulSoup(
                            respuesta_ganancias.text,
                            'html.parser'
                        )

                        texto_ganancias = ' '.join(
                            re.sub(r'\s+', ' ', x.strip())
                            for x in soup_ganancias.stripped_strings
                            if x.strip()
                        )

                        marcador_sicore = (
                            'Régimen General de retenciones y/o percepciones '
                            '(incluido el Régimen Opcional Semestral)'
                        )
                        pos_sicore = texto_ganancias.find(marcador_sicore)

                        if pos_sicore != -1:
                            bloque_sicore = texto_ganancias[
                                pos_sicore:pos_sicore + 2600
                            ]

                            patron_sicore_pagos = re.compile(
                                r'Ingreso \(Incluido el Régimen Opcional Semestral\) '
                                r'de las percepciones efectuadas en:\s*'
                                r'([A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'de las retenciones, practicadas en:\s*'
                                r'(2[º°]\s+quincena\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})'
                                r'.*?'
                                r'de las retenciones, practicadas en:\s*'
                                r'(1[º°]\s+quincena\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})',
                                re.I | re.S
                            )

                            match_sicore_pagos = patron_sicore_pagos.search(
                                bloque_sicore
                            )

                            if match_sicore_pagos:
                                periodo_sicore_pago = (
                                    match_sicore_pagos.group(1)
                                    + ' / '
                                    + match_sicore_pagos.group(2)
                                )

                                filas_sicore_pago = [
                                    ['0-1-2-3', match_sicore_pagos.group(3)],
                                    ['4-5-6', match_sicore_pagos.group(4)],
                                    ['7-8-9', match_sicore_pagos.group(5)],
                                ]

                                fechas_sicore_pago = [
                                    dmy_to_iso(match_sicore_pagos.group(i))
                                    for i in range(3, 6)
                                ]

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='sicore',
                                        title='SICORE - Percepciones y retenciones',
                                        period=periodo_sicore_pago,
                                        date=min(fechas_sicore_pago),
                                        rows=filas_sicore_pago,
                                        source=iva_url
                                    )
                                )

                                periodo_sicore_1q = (
                                    match_sicore_pagos.group(6)
                                )

                                filas_sicore_1q = [
                                    ['0-1-2-3', match_sicore_pagos.group(7)],
                                    ['4-5-6', match_sicore_pagos.group(8)],
                                    ['7-8-9', match_sicore_pagos.group(9)],
                                ]

                                fechas_sicore_1q = [
                                    dmy_to_iso(match_sicore_pagos.group(i))
                                    for i in range(7, 10)
                                ]

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='sicore',
                                        title='SICORE - Retenciones 1ª quincena',
                                        period=periodo_sicore_1q,
                                        date=min(fechas_sicore_1q),
                                        rows=filas_sicore_1q,
                                        source=iva_url
                                    )
                                )

                                print(
                                    'ARCA SICORE PAGOS:',
                                    periodo_sicore_pago,
                                    filas_sicore_pago
                                )

                                print(
                                    'ARCA SICORE 1Q:',
                                    periodo_sicore_1q,
                                    filas_sicore_1q
                                )
                            else:
                                print(
                                    'ARCA SICORE PAGOS: patrón no encontrado'
                                )

                            patron_sicore_info = re.compile(
                                r'SICORE - SISTEMA DE CONTROL DE RETENCIONES'
                                r'.*?'
                                r'Información \(Régimen General\) de las '
                                r'retenciones y/o percepciones, practicadas en:\s*'
                                r'([A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})',
                                re.I | re.S
                            )

                            match_sicore_info = patron_sicore_info.search(
                                bloque_sicore
                            )

                            if match_sicore_info:
                                periodo_sicore_info = (
                                    match_sicore_info.group(1)
                                )

                                filas_sicore_info = [
                                    ['0-1-2-3', match_sicore_info.group(2)],
                                    ['4-5-6', match_sicore_info.group(3)],
                                    ['7-8-9', match_sicore_info.group(4)],
                                ]

                                fechas_sicore_info = [
                                    dmy_to_iso(match_sicore_info.group(i))
                                    for i in range(2, 5)
                                ]

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='sicore',
                                        title='SICORE - Información F. 744',
                                        period=periodo_sicore_info,
                                        date=min(fechas_sicore_info),
                                        rows=filas_sicore_info,
                                        source=iva_url
                                    )
                                )

                                print(
                                    'ARCA SICORE INFORMACION:',
                                    periodo_sicore_info,
                                    filas_sicore_info
                                )
                            else:
                                print(
                                    'ARCA SICORE INFORMACION: patrón no encontrado'
                                )
                        else:
                            print(
                                'ARCA SICORE: bloque no encontrado'
                            )

                        marcador_ganancias = 'GANANCIAS PERSONAS JURÍDICAS - Versión 20.0'
                        pos_ganancias = texto_ganancias.find(marcador_ganancias)

                        if pos_ganancias != -1:
                            bloque_ganancias = texto_ganancias[
                                pos_ganancias:pos_ganancias + 1000
                            ]

                            patron_ganancias = re.compile(
                                r'Presentación del formulario de declaración jurada, '
                                r'correspondiente a:\s*'
                                r'(ejercicios con cierre en [A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})'
                                r'.*?Ingreso del saldo resultante:\s*'
                                r'(ejercicios con cierre en [A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4})'
                                r'.*?'
                                r'0-1-2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5-6\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'7-8-9\s+(\d{1,2}/\d{1,2}/\d{4})',
                                re.I | re.S
                            )

                            match_ganancias = patron_ganancias.search(
                                bloque_ganancias
                            )

                            if match_ganancias:
                                periodo_ganancias = match_ganancias.group(1)

                                filas_ddjj = [
                                    ['0-1-2-3', match_ganancias.group(2)],
                                    ['4-5-6', match_ganancias.group(3)],
                                    ['7-8-9', match_ganancias.group(4)],
                                ]

                                filas_saldo = [
                                    ['0-1-2-3', match_ganancias.group(6)],
                                    ['4-5-6', match_ganancias.group(7)],
                                    ['7-8-9', match_ganancias.group(8)],
                                ]

                                fechas_ddjj = [
                                    dmy_to_iso(match_ganancias.group(i))
                                    for i in range(2, 5)
                                ]

                                fechas_saldo = [
                                    dmy_to_iso(match_ganancias.group(i))
                                    for i in range(6, 9)
                                ]

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='ganancias',
                                        title='Ganancias Personas Jurídicas - DDJJ',
                                        period=periodo_ganancias,
                                        date=min(fechas_ddjj),
                                        rows=filas_ddjj,
                                        source=iva_url
                                    )
                                )

                                items.append(
                                    dict(
                                        org='ARCA',
                                        cat='ganancias',
                                        title='Ganancias Personas Jurídicas - Saldo',
                                        period=periodo_ganancias,
                                        date=min(fechas_saldo),
                                        rows=filas_saldo,
                                        source=iva_url
                                    )
                                )

                                print(
                                    'ARCA Ganancias PJ DDJJ:',
                                    periodo_ganancias,
                                    filas_ddjj
                                )

                                print(
                                    'ARCA Ganancias PJ SALDO:',
                                    periodo_ganancias,
                                    filas_saldo
                                )
                            else:
                                print(
                                    'ARCA Ganancias PJ: patrón no encontrado'
                                )
                        else:
                            print(
                                'ARCA Ganancias PJ: bloque no encontrado'
                            )
                    
                    except Exception as e:
                        print(
                            'GANANCIAS POST ERROR:',
                            str(e)[:300]
                        )
                            
                    try:
                        respuesta_iva = S.post(
                            action,
                            data=datos_iva,
                            timeout=TIMEOUT
                        )
                        respuesta_iva.raise_for_status()

                        soup_resultado = BeautifulSoup(
                            respuesta_iva.text,
                            'html.parser'
                        )

                        texto_resultado = ' '.join(
                            re.sub(r'\s+', ' ', x.strip())
                            for x in soup_resultado.stripped_strings
                            if x.strip()
                        )

                        marcador_iva = 'Presentación de la declaración jurada mensual'
                        pos_iva = texto_resultado.find(marcador_iva)

                        if pos_iva != -1:
                            bloque_iva = texto_resultado[pos_iva:pos_iva + 600]

                            patron_iva = re.compile(
                                r'correspondiente a:\s*'
                                r'([A-Za-zÁÉÍÓÚáéíóúñÑ]+/\d{4}).*?'
                                r'0-1\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'2-3\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'4-5\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'6-7\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
                                r'8-9\s+(\d{1,2}/\d{1,2}/\d{4})',
                                re.I | re.S
                                )

                        match_iva = patron_iva.search(bloque_iva)

                        if match_iva:
                            periodo_iva = match_iva.group(1)

                            filas_iva = [
                                ['0-1', match_iva.group(2)],
                                ['2-3', match_iva.group(3)],
                                ['4-5', match_iva.group(4)],
                                ['6-7', match_iva.group(5)],
                                ['8-9', match_iva.group(6)],
                                ]

                            fechas_iva = [
                                dmy_to_iso(match_iva.group(i))
                                for i in range(2, 7)
                                ]

                            items.append(
                                dict(
                                    org='ARCA',
                                    cat='iva',
                                    title='IVA',
                                    period=periodo_iva,
                                    date=min(fechas_iva),
                                    rows=filas_iva,
                                    source=iva_url
                                )
                            )

                            print(
                                'ARCA IVA mensual:',
                                periodo_iva,
                                filas_iva
                            )
                        else:
                            print(
                                'ARCA IVA mensual: patrón no encontrado'
                            )
                    except Exception as e:
                        print(
                            'IVA POST ERROR:',
                            str(e)[:300]
                        )

                print('--- FIN PRUEBA CONSULTA IVA ARCA ---')
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
