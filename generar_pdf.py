import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from datetime import datetime
import base64
import os

W, H = A4  # 595, 842 pts
ML = 25*mm
MR = 25*mm
CW = W - ML - MR

MESES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
         'septiembre','octubre','noviembre','diciembre']

FALTAS_DISC = {
    'Inasistencias injustificadas': {
        'articulo': 'Capítulo III, Artículo 8 (Deberes del aprendiz SENA)',
        'parrafo1': 'del Reglamento del Aprendiz SENA. El mencionado artículo establece, que el aprendiz debe asistir con puntualidad a todas las actividades propias del proceso de formación y justificar debidamente las inasistencias o incumplimientos a las actividades de formación, en los términos establecidos en el reglamento.',
        'es_dias': True,
    },
    'Uso de celular en ambiente': {
        'articulo': 'Capítulo V, Artículo 41, numeral 2',
        'parrafo1': 'del Reglamento del Aprendiz SENA, establece que las faltas disciplinarias se configuran ante conductas que conlleven el incumplimiento de deberes o prohibiciones de carácter comportamental. El uso de dispositivos móviles durante la formación afecta la concentración y el normal desarrollo de las actividades.',
        'es_dias': False,
    },
    'No porta EPP requerido': {
        'articulo': 'Capítulo II – Derechos y Deberes del Aprendiz SENA, Artículo 9 – Deberes del Aprendiz SENA',
        'parrafo1': 'relacionado con el uso adecuado de los Elementos de Protección Personal (EPP). Así mismo, esta conducta se enmarca como una falta conforme al Capítulo IX – Proceso Disciplinario, Artículo 41 – Faltas del Reglamento del Aprendiz SENA.',
        'es_dias': False,
    },
    'Conflicto con compañeros': {
        'articulo': 'Capítulo V, Artículo 41, numeral 2',
        'parrafo1': 'del Reglamento del Aprendiz SENA, establece que las faltas disciplinarias incluyen conductas que alteren la convivencia en el ambiente de formación y afecten la integridad o dignidad de los demás miembros de la comunidad educativa.',
        'es_dias': False,
    },
    'Abandono del ambiente sin permiso': {
        'articulo': 'Capítulo III, Artículo 8 (Deberes del aprendiz SENA)',
        'parrafo1': 'del Reglamento del Aprendiz SENA, el cual establece que el aprendiz debe permanecer en el ambiente de formación durante el horario asignado y solicitar autorización al instructor antes de retirarse.',
        'es_dias': False,
    },
    'Presentación personal inadecuada': {
        'articulo': 'Capítulo II – Derechos y Deberes del Aprendiz SENA, Artículo 9 – Deberes del Aprendiz SENA',
        'parrafo1': ', es deber del aprendiz cumplir con las normas de presentación personal, orden, disciplina y comportamiento dentro de los ambientes de formación.',
        'es_dias': False,
    },
    'Irrespeto al instructor': {
        'articulo': 'Capítulo V, Artículo 41, numeral 2',
        'parrafo1': 'del Reglamento del Aprendiz SENA. Dicho artículo establece que constituye falta disciplinaria el irrespeto hacia los instructores, directivos y demás miembros de la comunidad educativa del SENA.',
        'es_dias': False,
    },
    'Consumo de sustancias': {
        'articulo': 'Capítulo II – Artículo 8 lit. c y Capítulo V – Artículo 20',
        'parrafo1': 'del Reglamento del Aprendiz SENA. El artículo 8 establece que el aprendiz debe presentarse en condiciones físicas y mentales aptas para la formación. El artículo 20 establece que el consumo de sustancias psicoactivas es causal de cancelación inmediata de matrícula.',
        'es_dias': False,
    },
    'Otra falta disciplinaria': {
        'articulo': 'Capítulo V, Artículo 41',
        'parrafo1': 'del Reglamento del Aprendiz SENA, el cual establece las conductas que constituyen faltas disciplinarias en el proceso de formación.',
        'es_dias': False,
    },
}

FALTAS_ACAD = {
    'No entrega de evidencias': {
        'articulo': 'Capítulo II – Derechos y Deberes del Aprendiz SENA, Artículo 9 – Deberes del Aprendiz SENA',
        'parrafo1': ', es deber del aprendiz participar activamente en las actividades de formación, cumplir con las evidencias de aprendizaje programadas y asumir con responsabilidad los compromisos derivados de su proceso formativo.',
        'es_dias': False,
    },
    'Bajo rendimiento académico': {
        'articulo': 'Capítulo IV – Evaluación, Artículo 22 y 23',
        'parrafo1': 'del Reglamento del Aprendiz SENA. El artículo 22 establece que la nota mínima aprobatoria es 3.0 sobre 5.0, y el artículo 23 establece que cuando el aprendiz no alcanza esta nota está obligado a realizar un Plan de Mejoramiento.',
        'es_dias': False,
    },
    'No presenta pruebas de conocimiento': {
        'articulo': 'Capítulo II – Artículo 9 y Capítulo IV – Artículo 28',
        'parrafo1': 'del Reglamento del Aprendiz SENA. El aprendiz debe entregar mínimo el 60% de evidencias por competencia para ser evaluado satisfactoriamente.',
        'es_dias': False,
    },
    'Incumplimiento de compromisos formativos': {
        'articulo': 'Capítulo II – Derechos y Deberes del Aprendiz SENA, Artículo 9 – Deberes del Aprendiz SENA',
        'parrafo1': ', es deber del aprendiz cumplir con los compromisos adquiridos en el Plan Concertado y las actividades de formación programadas por el equipo ejecutor.',
        'es_dias': False,
    },
    'No realiza actividades asignadas': {
        'articulo': 'Capítulo II – Derechos y Deberes del Aprendiz SENA, Artículo 9 – Deberes del Aprendiz SENA',
        'parrafo1': ', es deber del aprendiz participar activamente en las actividades de formación y cumplir con las tareas y evidencias programadas dentro del proceso formativo.',
        'es_dias': False,
    },
    'Otra falta académica': {
        'articulo': 'Capítulo IV – Evaluación y Seguimiento, Artículo 22 al 30',
        'parrafo1': 'del Reglamento del Aprendiz SENA, los cuales establecen las obligaciones académicas del aprendiz durante el proceso de formación.',
        'es_dias': False,
    },
}

def fecha_letras(fecha_str):
    """Convierte YYYY-MM-DD o datetime a texto 'DD de mes de YYYY'"""
    if not fecha_str:
        return ''
    if isinstance(fecha_str, str):
        parts = fecha_str.split('-')
        if len(parts) == 3:
            return f"{int(parts[2])} de {MESES[int(parts[1])-1]} de {parts[0]}"
    if isinstance(fecha_str, datetime):
        return f"{fecha_str.day} de {MESES[fecha_str.month-1]} de {fecha_str.year}"
    return str(fecha_str)

def wrap_text(c_obj, text, max_width, font_name='Helvetica', font_size=10):
    """Divide texto en líneas que caben en max_width"""
    c_obj.setFont(font_name, font_size)
    words = text.split(' ')
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        if c_obj.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_justified_line(c_obj, words, x_start, y_pos, max_width, font_size=10, is_last=False):
    """Dibuja una línea de palabras justificada"""
    if not words:
        return
    if is_last or len(words) == 1:
        c_obj.drawString(x_start, y_pos, ' '.join(words))
        return
    
    total_text_width = sum(c_obj.stringWidth(w, 'Helvetica', font_size) for w in words)
    space_width = (max_width - total_text_width) / (len(words) - 1)
    
    x = x_start
    for i, word in enumerate(words):
        c_obj.drawString(x, y_pos, word)
        x += c_obj.stringWidth(word, 'Helvetica', font_size) + (space_width if i < len(words)-1 else 0)

def draw_justified_mixed(c_obj, segments, x_start, y_pos, max_width, font_size=10):
    """
    Dibuja párrafo justificado con mezcla de texto normal y negrita.
    segments = lista de {'text': str, 'bold': bool}
    Retorna nueva y_pos
    """
    LINE_H = 5.5 * mm
    
    # Construir lista de palabras con atributo bold
    all_words = []
    for seg in segments:
        words = seg['text'].split()
        for w in words:
            all_words.append({'w': w, 'bold': seg.get('bold', False)})
    
    if not all_words:
        return y_pos
    
    # Partir en líneas
    lines = []
    current_line = []
    current_width = 0
    space_w = c_obj.stringWidth(' ', 'Helvetica', font_size)
    
    for item in all_words:
        font = 'Helvetica-Bold' if item['bold'] else 'Helvetica'
        w_width = c_obj.stringWidth(item['w'], font, font_size)
        
        if current_line:
            needed = space_w + w_width
        else:
            needed = w_width
        
        if current_line and current_width + needed > max_width:
            lines.append(current_line)
            current_line = [{'w': item['w'], 'bold': item['bold'], 'width': w_width}]
            current_width = w_width
        else:
            current_line.append({'w': item['w'], 'bold': item['bold'], 'width': w_width})
            current_width += needed
    
    if current_line:
        lines.append(current_line)
    
    # Renderizar líneas
    for li, line in enumerate(lines):
        is_last = (li == len(lines) - 1)
        total_w = sum(item['width'] for item in line)
        
        if is_last or len(line) == 1:
            extra_space = space_w
        else:
            extra_space = (max_width - total_w) / (len(line) - 1)
        
        x = x_start
        for i, item in enumerate(line):
            font = 'Helvetica-Bold' if item['bold'] else 'Helvetica'
            c_obj.setFont(font, font_size)
            c_obj.drawString(x, y_pos, item['w'])
            x += item['width'] + (extra_space if i < len(line) - 1 else 0)
        
        y_pos -= LINE_H
    
    return y_pos

def generar_pdf_llamado_oficial(estado):
    """Genera PDF con formato oficial igual al repositorio GitHub"""
    buffer = io.BytesIO()
    
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle('Llamado de Atencion SENA')
    
    LINE_H = 5.5 * mm
    PAGE_BOTTOM = 30 * mm
    
    # Datos del estado
    aprendiz = estado.get('aprendiz', '').upper()
    programa = estado.get('programa_nombre', '')
    ficha = estado.get('ficha', '')
    instructor = estado.get('instructor', '')
    tipo = estado.get('tipo_llamado', 'disciplinario')
    numero = estado.get('numero_llamado', 'primero')
    falta_key = estado.get('falta', '')
    descripcion = estado.get('descripcion', '')
    mes = estado.get('mes_falta', '')
    dias_lista = estado.get('dias_falta', '')
    fecha_doc = datetime.now()
    
    # Buscar datos de la falta
    pool = FALTAS_DISC if tipo == 'disciplinario' else FALTAS_ACAD
    falta_data = pool.get(falta_key, {
        'articulo': 'Artículo 8 del Acuerdo 0009 de 2024',
        'parrafo1': 'del Reglamento del Aprendiz SENA.',
        'es_dias': False
    })
    
    numero_texto = 'PRIMER' if numero == 'primero' else 'SEGUNDO'
    tipo_texto = 'DISCIPLINARIO' if tipo == 'disciplinario' else 'ACADÉMICO'
    
    AREA_FIJA = 'Instructor – Metalmecánica'
    CENTRO_FIJO = 'CENTRO NACIONAL COLOMBO ALEMÁN'
    
    def nueva_pagina():
        c.showPage()
        return H - 20*mm
    
    # ── PÁGINA 1 ──
    y = H - 15*mm
    
    # Logo placeholder (rectángulo verde)
    logo_w = 25*mm
    logo_h = 25*mm
    logo_x = W/2 - logo_w/2
    logo_y = y - logo_h
    c.setFillColorRGB(0.05, 0.33, 0.07)
    c.rect(logo_x, logo_y, logo_w, logo_h, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(W/2, logo_y + logo_h/2 - 4, 'SENA')
    y = logo_y - 8*mm
    
    # Encabezado
    c.setFillColorRGB(0, 0, 0)
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(W/2, y, 'REGIMEN DE MEDIDAS FORMATIVAS')
    y -= 6*mm
    c.drawCentredString(W/2, y, f'{numero_texto} LLAMADO DE ATENCIÓN {tipo_texto} EQUIPO EJECUTOR DE')
    y -= 6*mm
    
    prog_upper = programa.upper()
    c.setFont('Helvetica-Bold', 9)
    prog_lines = wrap_text(c, prog_upper, CW, 'Helvetica-Bold', 9)
    for line in prog_lines:
        c.drawCentredString(W/2, y, line)
        y -= 5*mm
    
    y -= 6*mm
    
    # Fecha y datos
    c.setFillColorRGB(0, 0, 0)
    c.setFont('Helvetica-Bold', 10)
    fecha_txt = f"Barranquilla – {fecha_letras(fecha_doc)}"
    c.drawString(ML, y, fecha_txt)
    y -= 8*mm
    
    def draw_dato(label, valor):
        nonlocal y
        c.setFont('Helvetica-Bold', 10)
        c.drawString(ML, y, label)
        lw = c.stringWidth(label, 'Helvetica-Bold', 10)
        c.setFont('Helvetica', 10)
        val_lines = wrap_text(c, valor, CW - lw, 'Helvetica', 10)
        c.drawString(ML + lw, y, val_lines[0] if val_lines else '')
        if len(val_lines) > 1:
            y -= LINE_H
            c.drawString(ML, y, val_lines[1])
        y -= 6*mm
    
    draw_dato('Aprendiz:  ', aprendiz)
    draw_dato('Programa de Formación:  ', programa)
    draw_dato('Ficha:  ', ficha)
    draw_dato('Centro de Formación:  ', CENTRO_FIJO)
    
    y -= 6*mm
    
    c.setFont('Helvetica-Bold', 10)
    c.drawString(ML, y, 'Estimado Aprendiz,')
    y -= 7*mm
    c.setFont('Helvetica', 10)
    c.drawString(ML, y, 'Reciba un cordial saludo.')
    y -= 7*mm
    
    # Párrafo 1 — según tipo de falta
    if falta_key == 'Inasistencias injustificadas':
        segs = [
            {'text': 'A través de la presente comunicación, nos permitimos informarle que, de acuerdo con el seguimiento realizado a su proceso formativo, se ha identificado una falta disciplinaria, relacionada con el '},
            {'text': falta_data['articulo'], 'bold': True},
            {'text': ', ' + falta_data['parrafo1']}
        ]
    elif falta_key in ['No porta EPP requerido', 'Presentación personal inadecuada']:
        segs = [
            {'text': 'A través de la presente, nos permitimos informarle que, de acuerdo con el seguimiento realizado a su proceso formativo, usted incumplió lo establecido en el '},
            {'text': falta_data['articulo'], 'bold': True},
            {'text': falta_data['parrafo1']}
        ]
    elif tipo == 'academico':
        segs = [
            {'text': 'De conformidad con lo establecido en el '},
            {'text': falta_data['articulo'], 'bold': True},
            {'text': falta_data['parrafo1']}
        ]
    else:
        segs = [
            {'text': 'A través de la presente comunicación, nos permitimos informarle que, de acuerdo con el seguimiento realizado a su proceso formativo, se ha identificado una falta disciplinaria, relacionada con el '},
            {'text': falta_data['articulo'], 'bold': True},
            {'text': ', ' + falta_data['parrafo1']}
        ]
    
    y = draw_justified_mixed(c, segs, ML, y, CW, 10)
    y -= 4*mm
    
    # Párrafo 2 — hechos específicos
    if falta_key == 'Inasistencias injustificadas':
        dias_str = dias_lista if dias_lista else '[días]'
        mes_str = mes if mes else '[mes]'
        segs2 = [
            {'text': 'Nuestros registros indican que usted presenta '},
            {'text': f'inasistencia injustificada en el proceso formativo, específicamente los días {dias_str} del mes de {mes_str} del presente año. Estas inasistencias, correspondientes al mes de {mes_str} fueron registradas por el instructor {instructor} y se encuentran registradas en el aplicativo SOFIA Plus.', 'bold': True}
        ]
    else:
        desc_txt = descripcion if descripcion else '[descripción de la situación]'
        segs2 = [
            {'text': 'Nuestros registros indican que usted '},
            {'text': desc_txt, 'bold': True}
        ]
    
    y = draw_justified_mixed(c, segs2, ML, y, CW, 10)
    y -= 4*mm
    
    # Cierre 1
    cierre1 = 'Por lo tanto, este llamado tiene un carácter preventivo y formativo. Esperamos contar con su compromiso para superar esta situación. Su participación activa y constante es fundamental para el desarrollo de su proceso formativo y el logro de las competencias establecidas en el programa de formación.'
    y = draw_justified_mixed(c, [{'text': cierre1}], ML, y, CW, 10)
    y -= 4*mm
    
    # Cierre 2
    segs3 = [
        {'text': 'Le informamos que, de persistir esta situación, se procederá a realizar el segundo llamado de atención, de acuerdo con las medidas formativas establecidas en el '},
        {'text': 'Acuerdo 0009 de 2024 del Reglamento del Aprendiz SENA.', 'bold': True}
    ]
    y = draw_justified_mixed(c, segs3, ML, y, CW, 10)
    y -= 12*mm
    
    # Firma
    c.setFont('Helvetica', 10)
    c.drawString(ML, y, 'Atentamente,')
    y -= 18*mm
    
    c.setFont('Helvetica-Bold', 10)
    c.drawString(ML, y, instructor.upper())
    y -= 6*mm
    c.drawString(ML, y, AREA_FIJA)
    y -= 6*mm
    c.drawString(ML, y, CENTRO_FIJO)
    
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


PROGRAMAS_NOMBRES = {
    "CNC": "Producción de Componentes Mecánicos con Máquinas de Control Numérico Computarizado",
    "MEI": "Mantenimiento Electromecánico Industrial",
    "MMI": "Mecánica de Maquinaria Industrial",
    "GPI": "Gestión de la Producción Industrial"
}
