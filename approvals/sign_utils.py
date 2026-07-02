import base64

import hashlib

import mimetypes

import re



from django.core.files.base import ContentFile

from django.utils import timezone



from .document_types import get_config_for_document, get_document_from_process



try:

    from asn1crypto import cms, pem as asn1_pem



    _HAS_ASN1CRYPTO = True

except ImportError:

    _HAS_ASN1CRYPTO = False





class SignDocumentError(ValueError):

    pass





def get_main_document(process):

    document = get_document_from_process(process)

    if document is None:

        raise SignDocumentError("Документ согласования не найден.")

    cfg = get_config_for_document(document)

    doc = cfg.get_main_file(document)

    if not doc or not doc.name:

        raise SignDocumentError(cfg.no_file_message.replace(

            "перед отправкой на согласование", "перед подписанием"

        ))

    return document, cfg, doc





def get_rkd_main_document(rkd):

    from .document_types import DOCUMENT_TYPES

    cfg = DOCUMENT_TYPES["rkd"]

    doc = cfg.get_main_file(rkd)

    if not doc or not doc.name:

        raise SignDocumentError(cfg.no_file_message.replace(

            "перед отправкой на согласование", "перед подписанием"

        ))

    return doc





def read_sign_document_bytes(task) -> bytes:

    _, _, doc = get_main_document(task.process)

    with doc.open("rb") as fp:

        return fp.read()





def build_sign_payload_meta(task) -> str:

    _, _, doc = get_main_document(task.process)

    data = read_sign_document_bytes(task)

    filename = doc.name.rsplit("/", 1)[-1]

    digest = hashlib.sha256(data).hexdigest()

    return f"file:{filename}\nsha256:{digest}\nsize:{len(data)}"





def parse_signed_payload_meta(payload: str) -> dict:

    meta = {}

    for line in (payload or "").strip().splitlines():

        if ":" in line:

            key, value = line.split(":", 1)

            meta[key.strip()] = value.strip()

    return meta





def is_file_payload(payload: str) -> bool:

    return (payload or "").startswith("file:")





def get_signed_document_for_download(task):

    _, _, doc = get_main_document(task.process)

    data = read_sign_document_bytes(task)

    meta = parse_signed_payload_meta(task.signed_payload or "")

    expected = meta.get("sha256")

    if expected and hashlib.sha256(data).hexdigest() != expected:

        raise SignDocumentError("Документ изменён после подписания.")

    filename = meta.get("file") or doc.name.rsplit("/", 1)[-1]

    content_type, _ = mimetypes.guess_type(filename)

    return data, filename, content_type or "application/octet-stream"





def _safe_filename_part(value: str, fallback: str = "doc") -> str:

    cleaned = re.sub(r'[\\/:*?"<>|]', "_", (value or "").strip())

    return cleaned or fallback





def save_task_signature(task, sig_b64: str, *, cert_info: dict | None = None) -> None:

    payload_meta = build_sign_payload_meta(task)

    task.signed_payload = payload_meta

    task.signature_b64 = sig_b64



    update_fields = ["signature_b64", "signature_file", "signed_payload"]

    if cert_info:

        task.signer_cn = cert_info.get("cn", "")

        task.signer_cert_serial = cert_info.get("serial_hex", "")

        task.signer_cert_valid_to = cert_info.get("valid_to", "")

        task.signer_cert_issuer = cert_info.get("issuer_cn", "")

        update_fields.extend([

            "signer_cn", "signer_cert_serial",

            "signer_cert_valid_to", "signer_cert_issuer",

        ])



    raw = base64.b64decode(sig_b64)

    document, cfg, _ = get_main_document(task.process)

    name_part = _safe_filename_part(cfg.get_center_line(document), str(document.pk))

    dept = _safe_filename_part(str(task.department) if task.department else "sign", "sign")

    filename = f"ЛУ_{name_part}_{dept}_task{task.pk}.sig"



    if task.signature_file:

        task.signature_file.delete(save=False)

    task.signature_file.save(filename, ContentFile(raw), save=False)

    task.save(update_fields=update_fields)





def parse_cms_signature(sig_b64: str) -> dict:

    if not _HAS_ASN1CRYPTO:

        raise ImportError(

            "Для разбора подписи требуется пакет asn1crypto. "

            "Установите: pip install asn1crypto"

        )



    try:

        raw = base64.b64decode(sig_b64)

    except Exception:

        raise ValueError("Неверная кодировка данных (ожидается base64).")



    if asn1_pem.detect(raw):

        _, _, raw = asn1_pem.unarmor(raw)



    try:

        content_info = cms.ContentInfo.load(raw)

    except Exception as exc:

        raise ValueError(f"Не удалось разобрать CMS-структуру подписи: {exc}")



    if content_info["content_type"].native != "signed_data":

        raise ValueError("Неверный формат: ожидается SignedData (CMS/CAdES).")



    signed_data = content_info["content"]

    cert = _extract_signer_certificate(signed_data)

    if cert is None:

        raise ValueError("Не удалось определить сертификат подписанта в подписи.")



    def _rdn(name_obj, *oid_names):

        for rdn in name_obj.chosen:

            for attr in rdn:

                if attr["type"].native in oid_names:

                    v = attr["value"]

                    return v.native if hasattr(v, "native") else str(v)

        return None



    cn = _rdn(cert.subject, "common_name") or "Неизвестно"

    issuer_cn = _rdn(cert.issuer, "common_name", "organization_name") or "—"



    valid_to_dt = cert["tbs_certificate"]["validity"]["not_after"].native

    try:

        valid_to_str = valid_to_dt.strftime("%d.%m.%Y")

    except Exception:

        valid_to_str = str(valid_to_dt)



    serial = cert.serial_number

    serial_hex = format(serial, "X") if isinstance(serial, int) else str(serial)



    return {

        "cn": cn,

        "issuer_cn": issuer_cn,

        "valid_to": valid_to_str,

        "serial_hex": serial_hex,

    }





def _extract_signer_certificate(signed_data):

    signer_infos = signed_data["signer_infos"]

    if not signer_infos:

        return None



    sid = signer_infos[0]["sid"].chosen

    certs = signed_data["certificates"] or []



    for cert_holder in certs:

        candidate = cert_holder.chosen

        if _certificate_matches_signer_id(candidate, sid):

            return candidate



    for cert_holder in certs:

        candidate = cert_holder.chosen

        if not _looks_like_ca_certificate(candidate):

            return candidate



    return certs[0].chosen if certs else None





def _certificate_matches_signer_id(cert, sid):

    sid_type = sid.__class__.__name__.lower()

    if "issuerandserialnumber" in sid_type:

        return cert.issuer.dump() == sid["issuer"].dump() and cert.serial_number == sid["serial_number"].native

    if "subjectkeyidentifier" in sid_type:

        ski_ext = cert.subject_key_identifier

        return ski_ext is not None and ski_ext.native == sid.native

    return False





def _looks_like_ca_certificate(cert):

    bc = cert.basic_constraints_value

    if bc is not None and bc["ca"].native:

        return True

    issuer_dn = cert.issuer.human_friendly

    subject_dn = cert.subject.human_friendly

    return issuer_dn == subject_dn


