from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from datetime import datetime
import os

def filter_and_renumber_actors(actors_list):
    """
    Filtra actores sin nombre y reenumera los que sí tienen
    
    Args:
        actors_list: Lista de tuplas (actor_id, actor_name)
        
    Returns:
        Tuple: (filtered_list, stats_dict)
        filtered_list: Lista filtrada y reenumerada
        stats_dict: Diccionario con estadísticas del filtrado
    """
    # Filtrar actores que tienen nombre (no vacío y no solo espacios)
    filtered = [(actor_id, name.strip()) for actor_id, name in actors_list if name and name.strip()]
    
    # Reenumerar del 1 en adelante
    renumbered = []
    for new_id, (old_id, name) in enumerate(filtered, start=1):
        renumbered.append((new_id, name))
    
    # Estadísticas
    stats = {
        'total_detected': len(actors_list),
        'with_names': len(filtered),
        'without_names': len(actors_list) - len(filtered),
        'filtered_list': renumbered
    }
    
    return renumbered, stats

def create_actors_pdf(actors_list, detection_date=None, image_path=None, use_cases_list=None):
    """
    Create a PDF with actors information and optionally use cases
    
    Args:
        actors_list: List of tuples (actor_id, actor_name)
        detection_date: Date of detection (optional)
        image_path: Path to processed image (optional)
        use_cases_list: List of use cases detected (optional)
    
    Returns:
        BytesIO buffer with PDF content
    """
    # Filtrar y reenumerar actores
    filtered_actors, stats = filter_and_renumber_actors(actors_list)
    
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2c3e50')
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#7f8c8d')
    )
    
    stats_style = ParagraphStyle(
        'StatsStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        textColor=colors.HexColor('#34495e')
    )
    
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=15,
        spaceBefore=20,
        textColor=colors.HexColor('#2980b9')
    )
    
    # Story elements
    story = []
    
    # Title
    if use_cases_list:
        story.append(Paragraph("Reporte de Análisis de Diagrama UML", title_style))
    else:
        story.append(Paragraph("Reporte de Actores Detectados", title_style))
    
    # Date
    if detection_date is None:
        detection_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    story.append(Paragraph(f"Fecha de análisis: {detection_date}", subtitle_style))
    story.append(Spacer(1, 20))
    
    # Estadísticas generales
    story.append(Paragraph("<b>Resumen del Análisis:</b>", stats_style))
    
    stats_text = f"""
    • Actores detectados: {stats['with_names']}
    """
    
    if use_cases_list:
        stats_text += f"\n• Casos de uso detectados: {len(use_cases_list)}"
    
    for line in stats_text.strip().split('\n'):
        story.append(Paragraph(line, stats_style))
    
    story.append(Spacer(1, 10))
    
    # Sección de Actores
    story.append(Paragraph("Actores Detectados", section_style))
    
    if filtered_actors:
        # Create table data
        table_data = [["ID", "Nombre del Actor"]]
        
        for actor_id, actor_name in filtered_actors:
            table_data.append([f"Actor {actor_id}", actor_name])
        
        # Create table
        actor_table = Table(table_data, colWidths=[80, 400])
        actor_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        
        story.append(actor_table)
        story.append(Spacer(1, 30))
    
    # Sección de Casos de Uso (si se proporcionan)
    if use_cases_list:
        story.append(Paragraph("Casos de Uso Detectados", section_style))
        
        if use_cases_list:
            # Create table data for use cases
            uc_table_data = [["ID", "Descripción del Caso de Uso"]]
            
            for idx, use_case in enumerate(use_cases_list, 1):
                # Truncar texto muy largo
                display_text = use_case
                if len(display_text) > 120:
                    display_text = display_text[:117] + "..."
                uc_table_data.append([str(idx), display_text])
            
            # Create table
            uc_table = Table(uc_table_data, colWidths=[50, 430])
            uc_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e8f8f5')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
            ]))
            
            story.append(uc_table)
        else:
            story.append(Paragraph("No se detectaron casos de uso.", styles['Normal']))
        
        story.append(Spacer(1, 30))
    
    # Add processed image if available
    if image_path and os.path.exists(image_path):
        try:
            story.append(Paragraph("Diagrama Procesado:", section_style))
            story.append(Spacer(1, 10))
            
            # Add image to PDF (resize if necessary)
            img = Image(image_path, width=400, height=300)
            story.append(img)
            story.append(Spacer(1, 20))
        except Exception as e:
            story.append(Paragraph(f"Error al cargar la imagen: {str(e)}", styles['Normal']))
    
    # Footer information
    story.append(Spacer(1, 30))
    story.append(Paragraph("Smart Task - Análisis de Diagramas UML", 
                          ParagraphStyle('Footer', 
                                        parent=styles['Normal'],
                                        fontSize=10,
                                        alignment=TA_CENTER,
                                        textColor=colors.gray)))
    
    # Build PDF
    doc.build(story)
    
    # Move buffer position to beginning
    buffer.seek(0)
    return buffer

def create_simple_actors_pdf(actors_list, use_cases_list=None):
    """
    Create a simple PDF with just the actors list and optionally use cases
    
    Args:
        actors_list: List of tuples (actor_id, actor_name)
        use_cases_list: List of use cases detected (optional)
    
    Returns:
        BytesIO buffer with PDF content
    """
    # Filtrar y reenumerar actores
    filtered_actors, stats = filter_and_renumber_actors(actors_list)
    
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'SimpleTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=15,
        alignment=TA_CENTER
    )
    
    section_style = ParagraphStyle(
        'SimpleSection',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=10,
        spaceBefore=15
    )
    
    # Story elements
    story = []
    
    # Title
    if use_cases_list:
        story.append(Paragraph("Resultados del Análisis", title_style))
    else:
        story.append(Paragraph("Actores Detectados", title_style))
    
    story.append(Spacer(1, 10))
    
    # Estadísticas
    stats_msg = f"Actores identificados: {stats['with_names']}"
    if use_cases_list:
        stats_msg += f" | Casos de uso: {len(use_cases_list)}"
    
    story.append(Paragraph(stats_msg, styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Sección de Actores
    story.append(Paragraph("Actores:", section_style))
    
    if filtered_actors:
        for actor_id, name in filtered_actors:
            actor_text = f"Actor {actor_id}: {name}"
            story.append(Paragraph(actor_text, styles['Normal']))
            story.append(Spacer(1, 5))
    else:
        story.append(Paragraph("No se detectaron actores", styles['Normal']))
    
    # Sección de Casos de Uso (si se proporcionan)
    if use_cases_list:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Casos de Uso:", section_style))
        
        if use_cases_list:
            for idx, use_case in enumerate(use_cases_list, 1):
                uc_text = f"{idx}. {use_case}"
                story.append(Paragraph(uc_text, styles['Normal']))
                story.append(Spacer(1, 5))
        else:
            story.append(Paragraph("No se detectaron casos de uso", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    # Move buffer position to beginning
    buffer.seek(0)
    return buffer

def create_compact_actors_pdf(actors_list, use_cases_list=None):
    """
    Create a very compact PDF with actors and optionally use cases
    
    Args:
        actors_list: List of tuples (actor_id, actor_name)
        use_cases_list: List of use cases detected (optional)
    
    Returns:
        BytesIO buffer with PDF content
    """
    # Filtrar y reenumerar actores
    filtered_actors, _ = filter_and_renumber_actors(actors_list)
    
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom style for compact list
    compact_style = ParagraphStyle(
        'CompactStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=8,
        leftIndent=20
    )
    
    uc_style = ParagraphStyle(
        'UCStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6,
        leftIndent=30
    )
    
    # Story elements
    story = []
    
    # Title
    title_text = "Análisis de Diagrama" if use_cases_list else "Actores Identificados"
    title_style = ParagraphStyle(
        'CompactTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=TA_CENTER
    )
    story.append(Paragraph(title_text, title_style))
    
    # Summary
    summary_text = f"Actores: {len(filtered_actors)}"
    if use_cases_list:
        summary_text += f" | Casos de uso: {len(use_cases_list)}"
    
    story.append(Paragraph(summary_text, 
                          ParagraphStyle('Summary',
                                        parent=styles['Normal'],
                                        fontSize=11,
                                        alignment=TA_CENTER,
                                        spaceAfter=15)))
    
    # Actors list
    if filtered_actors:
        story.append(Paragraph("<b>Actores:</b>", compact_style))
        for actor_id, name in filtered_actors:
            actor_text = f"  • Actor {actor_id}: {name}"
            story.append(Paragraph(actor_text, compact_style))
    
    # Use Cases list (if provided)
    if use_cases_list:
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Casos de Uso:</b>", compact_style))
        for idx, use_case in enumerate(use_cases_list, 1):
            uc_text = f"  {idx}. {use_case}"
            story.append(Paragraph(uc_text, uc_style))
    
    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER)
    ))
    
    # Build PDF
    doc.build(story)
    
    # Move buffer position to beginning
    buffer.seek(0)
    return buffer