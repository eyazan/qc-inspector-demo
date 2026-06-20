"""
Birim donusturucu — deterministik compliance katmaninin temeli.

Ayni buyuklugun farkli birimlerde ifade edildigi durumlari cozer:
  Spec: min 380 MPa   Vendor: 55 ksi  -> ayni buyukluge cevirip karsilastir.

Desteklenen: basinc/gerilme (MPa, ksi, psi, N/mm2), sertlik (HB/HV/HRC yaklasik),
yuzde, sicaklik (C/F). Bilinmeyen birim -> donusum yok, ham karsilastirma.
"""

from app.core.logging import get_logger

logger = get_logger(__name__)

# Basinc/gerilme -> MPa taban birimine cevrim katsayilari
_PRESSURE_TO_MPA = {
    "mpa": 1.0,
    "n/mm2": 1.0,
    "n/mm²": 1.0,
    "ksi": 6.894757,
    "psi": 0.00689476,
    "kpa": 0.001,
    "gpa": 1000.0,
    "bar": 0.1,
}

# Birim ailesi tespiti
_PRESSURE_UNITS = set(_PRESSURE_TO_MPA.keys())
_PERCENT_UNITS = {"%", "percent", "pct"}
_HARDNESS_UNITS = {"hb", "hv", "hrc", "hrb", "brinell", "vickers", "rockwell"}


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return ""
    return unit.strip().lower().replace(" ", "")


def unit_family(unit: str | None) -> str:
    u = normalize_unit(unit)
    if u in _PRESSURE_UNITS:
        return "pressure"
    if u in _PERCENT_UNITS:
        return "percent"
    if u in _HARDNESS_UNITS:
        return "hardness"
    if u in {"c", "°c", "celsius", "f", "°f", "fahrenheit"}:
        return "temperature"
    return "unknown"


def to_base(value: float, unit: str | None) -> tuple[float, str] | None:
    """
    Degeri ailesinin taban birimine cevirir.
    pressure -> MPa, temperature -> C, digerleri oldugu gibi.
    Donusum mumkun degilse None.
    """
    u = normalize_unit(unit)
    family = unit_family(unit)

    if family == "pressure":
        return value * _PRESSURE_TO_MPA[u], "MPa"
    if family == "temperature":
        if u in {"f", "°f", "fahrenheit"}:
            return (value - 32) * 5.0 / 9.0, "C"
        return value, "C"
    if family in {"percent", "hardness"}:
        # Sertlik olcekleri arasi cevrim guvenilir degil; ayni olcek varsayilir
        return value, u
    return None


def can_compare(unit_a: str | None, unit_b: str | None) -> bool:
    """Iki birim ayni ailede mi (karsilastirilabilir mi)?"""
    fam_a = unit_family(unit_a)
    fam_b = unit_family(unit_b)
    if fam_a == "unknown" or fam_b == "unknown":
        # Birim yoksa/bilinmiyorsa string esitligine birak
        return normalize_unit(unit_a) == normalize_unit(unit_b)
    return fam_a == fam_b


def convert_for_comparison(
    value: float, from_unit: str | None, to_unit: str | None
) -> float | None:
    """value'yu from_unit'ten to_unit'e cevirir (ayni aile sartiyla)."""
    if not can_compare(from_unit, to_unit):
        return None
    base_from = to_base(value, from_unit)
    if base_from is None:
        return value if normalize_unit(from_unit) == normalize_unit(to_unit) else None

    base_value, _ = base_from
    family = unit_family(to_unit)
    if family == "pressure":
        return base_value / _PRESSURE_TO_MPA[normalize_unit(to_unit)]
    if family == "temperature":
        u = normalize_unit(to_unit)
        if u in {"f", "°f", "fahrenheit"}:
            return base_value * 9.0 / 5.0 + 32
        return base_value
    return base_value
