from io import BytesIO
from urllib.parse import urljoin

import qrcode
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


class QRGenerator:
    @staticmethod
    def generar_pdf(activo, base_url: str = "http://127.0.0.1:8000"):
        # Permite usar la URL del servidor o PUBLIC_BASE_URL para que el QR
        # no quede atado a localhost al imprimir desde un entorno publicado.
        url = urljoin(base_url.rstrip("/") + "/", f"activos/{activo.id}/historial")
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        imagen = ImageReader(buffer)

        pdf = BytesIO()
        ancho = 60 * mm
        alto = 60 * mm
        c = canvas.Canvas(pdf, pagesize=(ancho, alto))
        c.drawImage(
            imagen,
            10 * mm,
            16 * mm,
            width=40 * mm,
            height=40 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(ancho / 2, 10 * mm, activo.codigo_barras)
        c.save()
        pdf.seek(0)
        return pdf
