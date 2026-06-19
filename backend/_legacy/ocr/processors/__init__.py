from app.services.ocr.processors.base import RegionProcessor, ProcessorResult
from app.services.ocr.processors.figure import FigureProcessor
from app.services.ocr.processors.formula import FormulaProcessor
from app.services.ocr.processors.table import TableProcessor
from app.services.ocr.processors.text import TextProcessor

__all__ = [
    "RegionProcessor",
    "ProcessorResult",
    "TableProcessor",
    "FormulaProcessor",
    "FigureProcessor",
    "TextProcessor",
]
