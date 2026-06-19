"""
Region Router — her region tipini dogru isleyiciye yonlendirir.

Yonlendirme mantigi:
    table   -> TableProcessor    (yapi korumali)
    formula -> FormulaProcessor  (LaTeX)
    figure  -> FigureProcessor   (VLM + olcu)
    diger   -> TextProcessor     (hizli OCR)

Config ile ozel isleyiciler kapatilirsa -> TextProcessor'a duser.
"""

from app.core.config import settings
from app.services.ocr.processors import (
    FigureProcessor,
    FormulaProcessor,
    TableProcessor,
    TextProcessor,
)

# DocLayout V3 region tiplerinin isleyicilere eslemesi.
# inference.yml label_list (25 sinif) buna gore gruplandi.
_TABLE_TYPES = {"table", "tablo"}
_FORMULA_TYPES = {
    "formula", "equation", "formul",
    "display_formula", "inline_formula", "formula_number",
}
_FIGURE_TYPES = {
    "figure", "image", "drawing", "picture", "chart", "diagram",
    "header_image", "footer_image", "seal",
}
# Geri kalan tipler (text, paragraph_title, doc_title, abstract, content,
# reference, footnote, header, footer, number, aside_text, vertical_text,
# vision_footnote, algorithm, figure_title, reference_content) -> TextProcessor


class RegionRouter:
    def __init__(self, vlm_describe=None):
        self._text = TextProcessor()
        self._table = TableProcessor()
        self._formula = FormulaProcessor()
        self._figure = FigureProcessor(vlm_describe=vlm_describe)

    def route(self, region_type: str):
        normalized = (region_type or "").strip().lower()

        if normalized in _TABLE_TYPES and settings.enable_table_processor:
            return self._table
        if normalized in _FORMULA_TYPES and settings.enable_formula_processor:
            return self._formula
        if normalized in _FIGURE_TYPES and settings.enable_figure_processor:
            return self._figure
        return self._text
