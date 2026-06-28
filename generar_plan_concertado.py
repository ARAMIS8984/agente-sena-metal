"""
Generador de PDF Plan Concertado SENA
Replica el formato exacto de app.py usando ReportLab
"""
import io
import os
import re
import zipfile
from datetime import date, datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

SENA_GREEN  = colors.HexColor('#006633')
LIGHT_GREEN = colors.HexColor('#E8F5E9')
GRAY_BORDER = colors.HexColor('#AAAAAA')
BLACK       = colors.black

def get_logo_image():
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_sena.png"),
        "logo_sena.png",
    ]:
        if os.path.exists(path):
            return Image(path, width=1.8*cm, height=1.8*cm)
    return None

def get_styles():
    return {
        'label':  ParagraphStyle('label',  fontName='Helvetica-Bold', fontSize=8, alignment=TA_LEFT, leading=10),
        'value':  ParagraphStyle('value',  fontName='Helvetica',      fontSize=8, alignment=TA_LEFT, leading=10),
        'cell':   ParagraphStyle('cell',   fontName='Helvetica',      fontSize=8, alignment=TA_LEFT, leading=10),
        'cell_c': ParagraphStyle('cell_c', fontName='Helvetica',      fontSize=8, alignment=TA_CENTER, leading=10),
        'header': ParagraphStyle('header', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER, leading=10),
    }

def build_page(aprendiz, resultados_sel, datos, styles):
    ra_partes = []
    for i, r in enumerate(resultados_sel):
        ra_partes.append(f"<b>{i+1}.</b> {r['ra']}")
    ra_texto = "<br/><br/>".join(ra_partes)

    actividades_todas = []
    for r in resultados_sel:
        actividades_todas.extend(r['actividades'])

    fecha_plan = datos.get('fecha_plan', date.today().strftime("%d/%m/%Y"))
    W  = 19.1*cm
    BX = 0.5

    estilo_base = [
        ('BOX',   (0,0),(-1,-1), BX, BLACK),
        ('GRID',  (0,0),(-1,-1), BX, GRAY_BORDER),
        ('VALIGN',(0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1), 4),
        ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ('LEFTPADDING',   (0,0),(-1,-1), 4),
    ]

    logo_img  = get_logo_image()
    logo_cell = logo_img if logo_img else Paragraph(
        "<b>SENA</b>",
        ParagraphStyle('lg', fontName='Helvetica-Bold', fontSize=16,
                       alignment=TA_CENTER, textColor=SENA_GREEN))

    header = Table([[
        logo_cell,
        Paragraph("<b>SERVICIO NACIONAL DE APRENDIZAJE SENA</b><br/>"
                  "<b>CENTRO NACIONAL COLOMBO ALEMAN</b><br/>PLAN CONCERTADO",
                  ParagraphStyle('hd', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER, leading=10)),
        Paragraph("V2.0", ParagraphStyle('v2', fontName='Helvetica', fontSize=8, alignment=TA_LEFT, textColor=colors.gray)),
    ]], colWidths=[2.3*cm, 15.3*cm, 1.5*cm])
    header.setStyle(TableStyle(estilo_base + [
        ('TOPPADDING',   (0,0),(-1,-1), 6),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
    ]))

    sv = ParagraphStyle('sv', fontName='Helvetica',      fontSize=8, alignment=TA_LEFT, leading=10)
    sl = ParagraphStyle('sl', fontName='Helvetica-Bold', fontSize=8, alignment=TA_LEFT, leading=10)

    f1 = Table([[
        Paragraph("<b>Programa de\nFormación:</b>", sl),
        Paragraph(datos['programa'], sv),
        Paragraph("<b>Instructor:</b>", sl),
        Paragraph(datos['instructor'], sv),
    ]], colWidths=[2.8*cm, 9.5*cm, 2.3*cm, 4.5*cm])
    f1.setStyle(TableStyle(estilo_base + [
        ('BACKGROUND',(0,0),(0,0), LIGHT_GREEN),
        ('BACKGROUND',(2,0),(2,0), LIGHT_GREEN),
    ]))

    f2 = Table([[
        Paragraph("<b>Número de\nFicha:</b>", sl),
        Paragraph(datos['ficha'], sv),
        Paragraph("<b>Proyecto\nFormativo:</b>", sl),
        Paragraph(datos['proyecto'], sv),
        Paragraph("<b>Fase del\nProyecto:</b>", sl),
        Paragraph(datos['fase'], sv),
    ]], colWidths=[2.0*cm, 2.3*cm, 2.3*cm, 7.5*cm, 2.0*cm, 3.0*cm])
    f2.setStyle(TableStyle(estilo_base + [
        ('BACKGROUND',(0,0),(0,0), LIGHT_GREEN),
        ('BACKGROUND',(2,0),(2,0), LIGHT_GREEN),
        ('BACKGROUND',(4,0),(4,0), LIGHT_GREEN),
    ]))

    f3 = Table([
        [Paragraph("<b>Nombre del\nAprendiz:</b>", sl),
         Paragraph(aprendiz['nombre'], sv),
         Paragraph("<b>Observaciones:</b>", sl),
         Paragraph(datos.get('observaciones',''), sv)],
        [Paragraph("<b>Documento\nde Identidad:</b>", sl),
         Paragraph(aprendiz['doc'], sv), '', ''],
    ], colWidths=[2.8*cm, 6.8*cm, 2.8*cm, 6.7*cm])
    f3.setStyle(TableStyle(estilo_base + [
        ('BACKGROUND',(0,0),(0,1), LIGHT_GREEN),
        ('BACKGROUND',(2,0),(2,0), LIGHT_GREEN),
        ('SPAN',(2,0),(3,1)),
    ]))

    col_w = [4.4*cm, 1.1*cm, 4.8*cm, 1.4*cm, 1.4*cm, 1.9*cm, 1.9*cm, 1.1*cm, 1.1*cm]
    NCOLS = len(col_w)
    h = styles['header']
    num_rows = len(actividades_todas)

    title_style = ParagraphStyle('dt', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER)
    fila_titulo = [Paragraph("<b>DESCRIPTORES PARA EL DESARROLLO DE LA RUTA DE APRENDIZAJE</b>", title_style)] + ['']*(NCOLS-1)
    fila_hdr1 = [
        Paragraph("<b>Resultados de\nAprendizaje</b>",h),
        Paragraph("<b>N°\nActiv.</b>",h),
        Paragraph("<b>Actividades a desarrollar</b>",h),
        Paragraph("<b>Forma de\nEntrega</b>",h), '',
        Paragraph("<b>Fecha de entrega</b>",h), '',
        Paragraph("<b>¿Entregó?</b>",h), '',
    ]
    fila_hdr2 = ['','','',
        Paragraph("<b>Física</b>",h), Paragraph("<b>Digital</b>",h),
        Paragraph("<b>Concertada</b>",h), Paragraph("<b>Final</b>",h),
        Paragraph("<b>SI</b>",h), Paragraph("<b>NO</b>",h),
    ]

    table_data = [fila_titulo, fila_hdr1, fila_hdr2]
    DATA_START = 3

    for i in range(num_rows):
        act = actividades_todas[i] if i < len(actividades_todas) else ""
        cel_si = Paragraph("", styles['cell_c'])
        cel_no = Paragraph("", styles['cell_c'])
        fecha_fin = Paragraph("", styles['cell_c'])
        table_data.append([
            Paragraph(ra_texto, styles['cell']) if i == 0 else '',
            Paragraph(str(i+1), styles['cell_c']),
            Paragraph(act, styles['cell']),
            Paragraph("X", styles['cell_c']),
            '',
            Paragraph(fecha_plan, styles['cell_c']),
            fecha_fin,
            cel_si,
            cel_no,
        ])

    desc_table = Table(table_data, colWidths=col_w, rowHeights=None)
    desc_table.setStyle(TableStyle([
        ('BOX',  (0,0),(-1,-1), BX, BLACK),
        ('GRID', (0,0),(-1,-1), BX, GRAY_BORDER),
        ('VALIGN',(0,0),(-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('ALIGN', (0,DATA_START),(0,-1), 'LEFT'),
        ('ALIGN', (2,DATA_START),(2,-1), 'LEFT'),
        ('VALIGN',(0,DATA_START),(0,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0),(-1,-1), 3),
        ('TOPPADDING',  (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1), 3),
        ('SPAN',(0,0),(-1,0)),
        ('SPAN',(3,1),(4,1)),('SPAN',(5,1),(6,1)),('SPAN',(7,1),(8,1)),
        ('SPAN',(0,DATA_START),(0,DATA_START+num_rows-1)),
        ('BACKGROUND',(0,0),(-1,0), LIGHT_GREEN),
        ('BACKGROUND',(0,1),(-1,2), LIGHT_GREEN),
        ('FONTNAME',(0,0),(-1,2),'Helvetica-Bold'),
        ('TEXTCOLOR',(3,DATA_START),(3,-1), SENA_GREEN),
        ('FONTNAME', (3,DATA_START),(3,-1),'Helvetica-Bold'),
        ('FONTSIZE', (3,DATA_START),(3,-1), 10),
        ('FONTSIZE', (5,DATA_START),(5,-1), 8),
        ('FONTSIZE', (6,DATA_START),(6,-1), 8),
        ('TEXTCOLOR',(7,DATA_START),(7,-1), SENA_GREEN),
        ('FONTNAME', (7,DATA_START),(7,-1),'Helvetica-Bold'),
        ('FONTSIZE', (7,DATA_START),(7,-1), 10),
        ('TEXTCOLOR',(8,DATA_START),(8,-1), colors.HexColor('#CC0000')),
        ('FONTNAME', (8,DATA_START),(8,-1),'Helvetica-Bold'),
        ('FONTSIZE', (8,DATA_START),(8,-1), 10),
    ]))

    return [header, Spacer(1,3), f1, f2, f3, Spacer(1,4), desc_table]

def generar_pdf_plan_concertado(aprendices, resultados_sel, datos):
    """Genera PDF único con todos los aprendices (una página por aprendiz)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            rightMargin=1.2*cm, leftMargin=1.2*cm,
                            topMargin=1.2*cm,   bottomMargin=1.2*cm)
    styles = get_styles()
    story = []
    for i, ap in enumerate(aprendices):
        story.extend(build_page(ap, resultados_sel, datos, styles))
        if i < len(aprendices)-1:
            story.append(PageBreak())
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

def generar_zip_plan_concertado(aprendices, resultados_sel, datos):
    """Genera ZIP con un PDF individual por cada aprendiz."""
    zip_buf = io.BytesIO()
    styles = get_styles()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for ap in aprendices:
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter,
                                    rightMargin=1.2*cm, leftMargin=1.2*cm,
                                    topMargin=1.2*cm,  bottomMargin=1.2*cm)
            doc.build(build_page(ap, resultados_sel, datos, styles))
            nombre_limpio = re.sub(r'[^\w\s-]', '', ap['nombre']).strip().replace(' ', '_')
            filename = f"Plan_Concertado_{nombre_limpio}.pdf"
            zf.writestr(filename, buf.getvalue())
    zip_buf.seek(0)
    return zip_buf.getvalue()
