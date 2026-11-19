"""
Backward-compatibility shim re-exporting modularized Boss classes from bosses/.
"""

from bosses import BaseBoss, BossState, AttackPhase, Sans, Vergil

__all__ = [
    "BaseBoss",
    "BossState",
    "AttackPhase",
    "Sans",
    "Vergil",
]
