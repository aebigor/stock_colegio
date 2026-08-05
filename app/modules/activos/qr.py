from io import BytesIO

import qrcode

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


class QRGenerator:

    @staticmethod
    def generar_pdf(activo):

        # La URL que abrirá el QR
        url = f"http://127.0.0.1:8000/activos/{activo.id}/detalle"

        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2
        )

        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        buffer = BytesIO()

        img.save(buffer, format="PNG")

        buffer.seek(0)

        imagen = ImageReader(buffer)

        pdf = BytesIO()

        ancho = 60 * mm
        alto = 60 * mm

        c = canvas.Canvas(
            pdf,
            pagesize=(ancho, alto)
        )

        c.drawImage(
            imagen,
            10 * mm,
            16 * mm,
            width=40 * mm,
            height=40 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )

        c.setFont(
            "Helvetica-Bold",
            9
        )

        c.drawCentredString(
            ancho / 2,
            10 * mm,
            activo.codigo_barras
        )

        c.save()

        pdf.seek(0)

        return pdf