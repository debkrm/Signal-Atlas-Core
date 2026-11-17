"""Fill policy for instrument-sessions that carry no attested price band.

Audit §74.10 Ruling D: NSE publishes the band *code* in a single rolling `sec_list.csv` that is
overwritten in place, and the bhavcopy carries no band column, so no daily band history exists for
2022-2023 from the exchange whose bands H-83 requires. Requiring a band therefore refuses 176 of 179
instruments and returns a criterion (`CRIT-EXEC-03/04`) that has never been computed.

`LOCKED_BAR_REFUSAL_ONLY` narrows the requirement instead of the window: an unbanded order is filled
unless the session bar is locked (`high == low`, zero depth on one side), which is the failure mode
§5.3 actually names. `CRIT-EXEC-03/04` stay NOT RUN on those sessions — the policy never claims to
know whether a non-locked open sat at a limit.
"""

from enum import Enum


class PriceBandPolicy(str, Enum):
    """How the execution engine treats a session with no attested price band."""

    # H-83 as written: no verified band -> no entry, and no stop evaluation.
    STRICT_BAND_REQUIRED = "STRICT_BAND_REQUIRED"
    # Audit §74.10 Ruling D: fill unless the bar is locked; circuit criteria stay NOT RUN.
    LOCKED_BAR_REFUSAL_ONLY = "LOCKED_BAR_REFUSAL_ONLY"

    @classmethod
    def parse(cls, value: "str | PriceBandPolicy") -> "PriceBandPolicy":
        """Parses a policy name, failing closed on anything unrecognised."""
        if isinstance(value, PriceBandPolicy):
            return value
        try:
            return cls(str(value))
        except ValueError:
            raise ValueError(
                f"Unsupported price band policy {value!r}; expected one of "
                f"{[p.value for p in cls]} (Audit §74.10 Ruling D)."
            ) from None
