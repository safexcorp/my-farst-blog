from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from django.core.files.base import ContentFile
import os


def generate_pdf_logic(psi_document, user):
    """Генерация PDF протокола ПСИ"""

    context = {
        'psi': psi_document,
        'generated_at': timezone.now(),
    }

    html_string = render_to_string('pdf/document_template.html', context)

    # Генерация PDF
    pdf_file = HTML(string=html_string).write_pdf()

    # Формирование имени файла
    filename = f"PSI_{psi_document.serial_number}_v{psi_document.pdfs.count() + 1}.pdf"

    # Сохранение
    from shared_repository.models import GeneratedDocument
    generated_doc = GeneratedDocument(
        psi_source=psi_document,
        version=psi_document.pdfs.count() + 1,
    )
    generated_doc.file.save(filename, ContentFile(pdf_file), save=True)

    # Запись в историю
    from shared_repository.models import DocumentHistory
    DocumentHistory.objects.create(
        psi_source=psi_document,
        user=user,
        action=f"Сгенерирован PDF версии {generated_doc.version}"
    )

    return generated_doc