from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from django.core.files.base import ContentFile
import os


def generate_pdf_logic(psi_document, user):
    """Генерация PDF протокола ПСИ"""

    try:
        #заводской номер
        serial_number = psi_document.shipment.serial_number if psi_document.shipment else "—"

        # Номер протокола: берем символы с индекса 1 по индекс 5 (всего 5 символов)
        # Пример: "2000012026" -> "00001"
        if psi_document.shipment and psi_document.shipment.serial_number:
            sn = psi_document.shipment.serial_number
            # Берем подстроку с индекса 1 (второй символ) длиной 5 символов
            if len(sn) >= 6:
                protocol_number = sn[1:6]  # индексы 1,2,3,4,5 -> символы 2-6
            else:
                # Если строка короче, дополняем нулями
                protocol_number = sn.zfill(5)
        else:
            protocol_number = "—"

        #название модели
        model_name = psi_document.post.name if psi_document.post else "ИБП_СПМ"

        #определяем версию
        version = psi_document.pdfs.count() + 1

        # Номер протокола берётся из изделия к отгрузке (поле «Заводской номер» shipment),
        # например "2000012026". То, что введено в shipment.serial_number, и попадёт в PDF.
        #protocol_number = psi_document.shipment.serial_number if psi_document.shipment else "—"

        # Подготавливаем контекст для шаблона
        context = {
            'psi': psi_document,
            'generated_at': timezone.now(),
            'serial_number': serial_number,
            'protocol_number': protocol_number,
            'model_name': model_name,
            'version': version,
        }

        # Рендерим HTML-шаблон
        html_string = render_to_string('pdf/document_template.html', context)

        # Генерация PDF
        pdf_file = HTML(string=html_string).write_pdf()

        #имя файла
        filename = f"Протокол_ПСИ_ИБП_СПМ_{serial_number}_v{version}.pdf"

        # Сохранение
        from blog.models import GeneratedDocument
        generated_doc = GeneratedDocument(
            psi_source=psi_document,
            version=version,
        )
        generated_doc.file.save(filename, ContentFile(pdf_file), save=True)

        # Запись в историю
        from blog.models import DocumentHistory
        DocumentHistory.objects.create(
            psi_source=psi_document,
            user=user,
            action=f"Сгенерирован PDF версии {generated_doc.version}"
        )

        return generated_doc

    except Exception as e:
        # Логируем ошибку
        print(f"Ошибка генерации PDF: {e}")
        raise