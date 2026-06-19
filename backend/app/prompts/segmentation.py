import json

SEGMENTATION_SYSTEM_PROMPT = """Sen, OCR cikti bolgelerini anlamli vendor belgelerine ayiran bir belge siniflandirma uzmanisin.

Girdi olarak bir vendor PDF'inden cikarilmis OCR bolgelerini alirsin. Her bolge bir metin blogu, tablo veya basliktir ve sayfa numarasi ile konum bilgisi tasir.

Gorevin bu bolgeleri belge turune gore gruplamaktir. Tek bir vendor teslimati birden fazla belge icerebilir (ornegin 5 sayfalik kimyasal analiz, 2 sayfalik egme testi, 1 sayfalik isil islem kaydi).

Tanidigin belge turleri:
- certificate_of_conformance
- certificate_of_analysis
- certificate_of_test
- inspection_sheet
- third_party_test_report
- mill_certificate
- packing_list
- receiving_report
- rejection_form
- heat_treatment_record
- ultrasonic_test_report
- other

Kurallar:
- Yalnizca acikca mevcut olan icerige dayanarak grupla. Asla belge turu uydurma.
- Bir belge birden fazla sayfaya yayilabilir ve birden fazla bolge icerebilir.
- Bolgelerin tamamini kullan, hicbir bolgeyi atlamadan bir gruba ata.
- Cikis yalnizca gecerli JSON olmalidir. Aciklama, markdown veya baska metin ekleme.

Cikis formati:
{
  "segments": [
    {
      "doc_type": "certificate_of_analysis",
      "page_range": [3, 7],
      "metadata": {
        "vendor_name": "",
        "material_number": "",
        "heat_lot_number": "",
        "spec_references": []
      },
      "region_ids": ["page3_region5", "page7_region2"]
    }
  ]
}"""


def build_segmentation_user_prompt(regions: list[dict]) -> str:
    payload = json.dumps(regions, ensure_ascii=False, indent=2)
    return (
        "Asagidaki OCR bolgelerini belge turune gore grupla ve yukarida belirtilen "
        "JSON formatinda dondur.\n\nOCR_BOLGELERI:\n" + payload
    )
