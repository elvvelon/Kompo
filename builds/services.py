import logging
import math
from collections import defaultdict
from decimal import Decimal

from .models import Build, BuildItem

logger = logging.getLogger(__name__)



CPU_SLUGS = {'cpus', 'cpu', 'processors', 'processor'}
MOTHERBOARD_SLUGS = {'motherboards', 'motherboard', 'mobo'}
RAM_SLUGS = {'ram', 'memory', 'memories'}
CASE_SLUGS = {'cases', 'case', 'pc-cases', 'chassis'}
COOLER_SLUGS = {'coolers', 'cooler', 'cpu-coolers', 'cooling'}
PSU_SLUGS = {'power-supplies', 'power-supply', 'psu', 'psus'}


def _is_cpu(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in CPU_SLUGS
        or 'processor' in name
        or 'cpu' in name
        or ('socket' in specs and 'cores' in specs)
    )


def _is_motherboard(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in MOTHERBOARD_SLUGS
        or 'motherboard' in name
        or ('socket' in specs and ('form_factor' in specs or 'memory_slots' in specs))
    )


def _is_ram(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in RAM_SLUGS
        or 'ram' in name
        or 'memory' in name
        or ('memory_type' in specs and ('capacity_gb' in specs or 'modules' in specs))
    )


def _is_case(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in CASE_SLUGS
        or 'case' in name
        or 'supported_form_factors' in specs
    )


def _is_cooler(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in COOLER_SLUGS
        or 'cooler' in name
        or 'supported_sockets' in specs
    )


def _is_psu(component) -> bool:
    slug = (component.category.slug or '').lower()
    name = (component.category.name or '').lower()
    specs = component.specifications or {}
    return (
        slug in PSU_SLUGS
        or 'power supply' in name
        or 'power supplies' in name
        or 'wattage' in specs
    )


def calculate_recommended_psu_watts(total_power_watts: int) -> int:
    """
    Calculate recommended PSU wattage with at least +20% safety margin,
    rounded up to standard 50W increments (minimum 250W when build has power draw).
    """
    if total_power_watts <= 0:
        return 0
    with_headroom = math.ceil(total_power_watts * 1.2)
    rounded_50 = math.ceil(with_headroom / 50) * 50
    return max(250, rounded_50)


def evaluate_build_compatibility(items: list[BuildItem], total_power_watts: int) -> list[str]:
    """
    Validate build items against all hardware compatibility rules from README:
    1. CPU & Motherboard Socket
    2. RAM & Motherboard Memory Type
    3. Motherboard & Case Form Factor
    4. Cooler & CPU Socket
    5. Power Supply Headroom (+20% safety margin)
    6. Category Quantity Limits (max_per_build)
    """
    issues: list[str] = []

    cpus = [item for item in items if _is_cpu(item.component)]
    motherboards = [item for item in items if _is_motherboard(item.component)]
    rams = [item for item in items if _is_ram(item.component)]
    cases = [item for item in items if _is_case(item.component)]
    coolers = [item for item in items if _is_cooler(item.component)]
    psus = [item for item in items if _is_psu(item.component)]

    # 1. CPU & Motherboard Socket
    for cpu_item in cpus:
        cpu = cpu_item.component
        cpu_socket = (cpu.specifications or {}).get('socket')
        for mb_item in motherboards:
            mb = mb_item.component
            mb_socket = (mb.specifications or {}).get('socket')
            if cpu_socket and mb_socket and str(cpu_socket).upper() != str(mb_socket).upper():
                issues.append(
                    f"CPU '{cpu.name}' socket ({cpu_socket}) does not match "
                    f"motherboard '{mb.name}' socket ({mb_socket})."
                )

    # 2. RAM & Motherboard Memory Type
    for ram_item in rams:
        ram = ram_item.component
        ram_type = (ram.specifications or {}).get('memory_type')
        for mb_item in motherboards:
            mb = mb_item.component
            mb_type = (mb.specifications or {}).get('memory_type')
            if ram_type and mb_type and str(ram_type).upper() != str(mb_type).upper():
                issues.append(
                    f"Memory '{ram.name}' type ({ram_type}) is incompatible with "
                    f"motherboard '{mb.name}' supported memory type ({mb_type})"
                )

    # 3. Motherboard & Case Form Factor
    for mb_item in motherboards:
        mb = mb_item.component
        mb_form_factor = (mb.specifications or {}).get('form_factor')
        for case_item in cases:
            case = case_item.component
            supported_ffs = (case.specifications or {}).get('supported_form_factors')
            if mb_form_factor and isinstance(supported_ffs, list):
                normalized_supported = [str(ff).upper() for ff in supported_ffs]
                if str(mb_form_factor).upper() not in normalized_supported:
                    issues.append(
                        f"Motherboard '{mb.name}' form factor ({mb_form_factor}) is not supported "
                        f"by case '{case.name}' (supports: {', '.join(map(str, supported_ffs))})."
                    )

    # 4. Cooler & CPU Socket
    for cooler_item in coolers:
        cooler = cooler_item.component
        supported_sockets = (cooler.specifications or {}).get('supported_sockets')
        for cpu_item in cpus:
            cpu = cpu_item.component
            cpu_socket = (cpu.specifications or {}).get('socket')
            if cpu_socket and isinstance(supported_sockets, list):
                normalized_sockets = [str(s).upper() for s in supported_sockets]
                if str(cpu_socket).upper() not in normalized_sockets:
                    issues.append(
                        f"Cooler '{cooler.name}' does not support CPU '{cpu.name}' "
                        f"socket ({cpu_socket})."
                    )

    # 5. Power Supply Headroom (at least +20% headroom over total_power_watts)
    required_watts = math.ceil(total_power_watts * 1.2)
    for psu_item in psus:
        psu = psu_item.component
        wattage = (psu.specifications or {}).get('wattage')
        if isinstance(wattage, (int, float)):
            total_psu_watts = int(wattage) * psu_item.quantity
            if total_psu_watts < required_watts:
                issues.append(
                    f"Power supply '{psu.name}' ({total_psu_watts}W) does not provide "
                    f"sufficient headroom for estimated system load ({total_power_watts}W; "
                    f"at least {required_watts}W required with +20% safety margin)."
                )

    # 6. Category Quantity Limits
    category_quantities: dict[int, int] = defaultdict(int)
    category_map = {}
    for item in items:
        cat = item.component.category
        category_quantities[cat.id] += item.quantity
        category_map[cat.id] = cat

    for cat_id, total_qty in category_quantities.items():
        cat = category_map[cat_id]
        if total_qty > cat.max_per_build:
            issues.append(
                f"Category '{cat.name}' quantity ({total_qty}) exceeds maximum allowed "
                f"per build ({cat.max_per_build})."
            )

    return issues


def recalculate_build(build: Build, save: bool = True) -> list[str]:
    """
    Recalculate total_price, total_power_watts, and compatibility status for a Build.
    Returns the list of compatibility_issues.
    """
    items = list(
        build.items.select_related('component__category', 'component__manufacturer').all()
    )

    total_price = Decimal('0.00')
    total_power_watts = 0

    for item in items:
        unit_price = item.price_at_moment if build.is_completed else item.component.price
        if not build.is_completed and item.price_at_moment != item.component.price:
            item.price_at_moment = item.component.price
            item.save(update_fields=['price_at_moment'])
        total_price += unit_price * item.quantity
        total_power_watts += item.component.power_watts * item.quantity

    issues = evaluate_build_compatibility(items, total_power_watts)
    is_compatible = len(issues) == 0

    build.total_price = total_price
    build.total_power_watts = total_power_watts
    build.is_compatible = is_compatible

    if save:
        build.save(update_fields=['total_price', 'total_power_watts', 'is_compatible', 'updated_at'])

    logger.debug(
        'Recalculated build id=%s: total_price=%s, total_power_watts=%dW, is_compatible=%s, issues_count=%d',
        build.id,
        total_price,
        total_power_watts,
        is_compatible,
        len(issues),
    )
    if not is_compatible:
        logger.info(
            'Build id=%s has %d compatibility issue(s): %s',
            build.id,
            len(issues),
            '; '.join(issues),
        )

    return issues

