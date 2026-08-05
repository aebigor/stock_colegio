from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


class BarcodeGenerator:

    @staticmethod
    def generar_pdf(codigo: str):

        # -----------------------------
        # Generar imagen del código
        # -----------------------------

        barcode_buffer = BytesIO()

        barcode = Code128(
            codigo,
            writer=ImageWriter()
        )

        barcode.write(
            barcode_buffer,
            {
                "write_text": False,   # NO escribir el texto debajo
                "module_width": 0.25,
                "module_height": 15,
                "quiet_zone": 2
            }
        )

        barcode_buffer.seek(0)

        imagen = ImageReader(barcode_buffer)

        # -----------------------------
        # PDF tamaño etiqueta
        # -----------------------------

        pdf = BytesIO()

        ancho = 60 * mm
        alto = 25 * mm

        c = canvas.Canvas(
            pdf,
            pagesize=(ancho, alto)
        )

        # Solo el código de barras
        c.drawImage(
            imagen,
            3 * mm,
            8 * mm,
            width=54 * mm,
            height=10 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )

        # Únicamente el código debajo
        c.setFont(
            "Helvetica-Bold",
            9
        )

        c.drawCentredString(
            ancho / 2,
            3 * mm,
            codigo
        )

        c.save()

        pdf.seek(0)

        return pdf