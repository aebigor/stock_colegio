"""Generación de etiquetas A4 que incluyen QR y código de barras por activo."""
from io import BytesIO
from urllib.parse import urljoin

import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _qr_buffer(url: str) -> BytesIO:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _barcode_buffer(code: str) -> BytesIO:
    buffer = BytesIO()
    barcode = Code128(code, writer=ImageWriter())
    barcode.write(
        buffer,
        options={
            "write_text": False,
            "module_width": 0.22,
            "module_height": 10,
            "quiet_zone": 1,
            "dpi": 180,
        },
    )
    buffer.seek(0)
    return buffer


def generar_catalogo_pdf(activos: list, base_url: str) -> BytesIO:
    """Crea un PDF tamaño A4 con QR y código de barras de todos los activos."""
    output = BytesIO()
    page_width, page_height = A4
    margin = 7 * mm
    gap = 3 * mm
    columns = 2
    rows = 4
    card_width = (page_width - 2 * margin - gap) / columns
    card_height = (page_height - 2 * margin - (rows - 1) * gap) / rows
    pdf = canvas.Canvas(output, pagesize=A4)

    if not activos:
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawCentredString(page_width / 2, page_height / 2 + 8 * mm, "No hay artículos para generar etiquetas")
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(page_width / 2, page_height / 2 - 2 * mm, "Revisa el área seleccionada y registra activos primero.")
        pdf.save()
        output.seek(0)
        return output

    for index, activo in enumerate(activos):
        position = index % (columns * rows)
        if index and position == 0:
            pdf.showPage()

        column = position % columns
        row = position // columns
        x = margin + column * (card_width + gap)
        y = page_height - margin - (row + 1) * card_height - row * gap

        pdf.setStrokeColor(colors.HexColor("#9CA3AF"))
        pdf.setLineWidth(0.55)
        pdf.roundRect(x, y, card_width, card_height, 2.5 * mm, stroke=1, fill=0)

        name = (activo.nombre or "Activo sin nombre").strip()
        if len(name) > 45:
            name = name[:42] + "..."
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 3 * mm, y + card_height - 6 * mm, name)

        area = getattr(activo, "area", "") or ""
        estado = getattr(activo, "estado", "") or ""
        area_status = f"{area} · {estado}" if area else estado
        pdf.setFont("Helvetica", 7)
        pdf.drawString(x + 3 * mm, y + card_height - 11 * mm, area_status[:55])

        qr_url = urljoin(base_url.rstrip("/") + "/", f"activos/{activo.id}/detalle")
        qr_buffer = _qr_buffer(qr_url)
        qr_size = 27 * mm
        pdf.drawImage(
            ImageReader(qr_buffer),
            x + 3 * mm,
            y + 7 * mm,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )

        bar_buffer = _barcode_buffer(activo.codigo_barras)
        bar_x = x + 33 * mm
        bar_width = card_width - 36 * mm
        bar_height = 15 * mm
        bar_y = y + 19 * mm
        pdf.drawImage(
            ImageReader(bar_buffer),
            bar_x,
            bar_y,
            width=bar_width,
            height=bar_height,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(bar_x + bar_width / 2, y + 14 * mm, str(activo.codigo_barras)[:38])
        pdf.setFont("Helvetica", 7)
        codigo_interno = str(getattr(activo, "codigo", "") or "")
        pdf.drawCentredString(bar_x + bar_width / 2, y + 9 * mm, codigo_interno[:40])

        ubicacion = getattr(activo, "ubicacion", None)
        loc_name = getattr(ubicacion, "nombre", "") if ubicacion else ""
        if loc_name:
            pdf.setFont("Helvetica", 6.5)
            pdf.drawString(x + 33 * mm, y + 3.5 * mm, f"Bodega: {loc_name[:36]}")

    pdf.save()
    output.seek(0)
    return output
