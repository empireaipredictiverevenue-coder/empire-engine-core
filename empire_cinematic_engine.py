"""
EMPIRE V49 · CINEMATIC ENGINE (renamed: ACTIVATOR)
====================================================
Was: stub that printed "3D render".
Now: enrolls a target into the storm_strike email sequence.
Same filename, same function signature — different reality.
"""
import logging
from typing import Dict, Callable, Optional

log = logging.getLogger("empire.cinematic")


async def launch_3d_render(
    details: Dict,
    email_engine=None,
    target_email: Optional[str] = None,
    storm: Optional[str] = None,
) -> bool:
    """
    Legacy entry point. Real action: enroll target into outreach.
    Returns True on successful enrollment.

    If no email_engine provided OR no target_email, logs and returns False.
    """
    warehouse = details.get("warehouse_name", "Unknown")
    target_email = target_email or details.get("email")

    if not email_engine:
        log.info(f"[activator] DRY: would enroll {warehouse}")
        return False

    if not target_email:
        log.info(f"[activator] SKIP: no email for {warehouse}")
        return False

    try:
        result = await email_engine.enroll(
            email=target_email,
            target_addr=details.get("address") or warehouse,
            sequence_type="storm_strike",
            meta={
                "warehouse_name": warehouse,
                "storm": storm,
                "lat": details.get("lat"),
                "lon": details.get("lon"),
            },
        )
        return bool(result and result.get("ok"))
    except Exception as e:
        log.error(f"[activator] enroll failed for {warehouse}: {e}")
        return False
