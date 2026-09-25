"""Height-only paper model and visibly synthetic carrier payloads.

Nothing in this module verifies a Shielded Bitcoin proof or reconstructs roots.
"""

from dataclasses import dataclass
import hashlib
import struct


POLICIES = ('hold', 'fee_only', 'refresh_on_bump')


def integer(name: str, value: int, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


@dataclass(frozen=True)
class AnchorProfile:
    window: int = 100
    minimum_depth: int = 1

    def __post_init__(self) -> None:
        integer('window', self.window, 1)
        integer('minimum_depth', self.minimum_depth, 1)
        if self.minimum_depth > self.window:
            raise ValueError('minimum depth exceeds window')

    def eligible(self, anchor: int, inclusion_height: int) -> bool:
        integer('anchor', anchor)
        integer('inclusion height', inclusion_height)
        return inclusion_height - self.window <= anchor <= inclusion_height - self.minimum_depth

    def choose(self, candidate_height: int, spacing: int, wallet_depth: int) -> int | None:
        integer('candidate height', candidate_height)
        integer('spacing', spacing, 1)
        integer('wallet depth', wallet_depth, self.minimum_depth)
        if wallet_depth > self.window:
            raise ValueError('wallet depth exceeds window')
        anchor = ((candidate_height - wallet_depth) // spacing) * spacing
        if anchor < 0 or not self.eligible(anchor, candidate_height):
            return None
        return anchor


def boundary_summary(profile: AnchorProfile, spacing: int, wallet_depth: int) -> dict:
    # Mature-chain start prevents genesis from contaminating phase availability.
    integer('spacing', spacing, 1)
    start = ((profile.window // spacing) + 2) * spacing + 1
    phases = []
    for height in range(start, start + spacing):
        selected = profile.choose(height, spacing, wallet_depth)
        newest = ((height - wallet_depth) // spacing) * spacing
        phases.append({
            'height_mod_spacing': height % spacing,
            'anchor_age': height - newest,
            'height_eligible': selected is not None,
            'remaining_height_margin': newest + profile.window - height,
        })
    return {
        'window': profile.window,
        'protocol_minimum_depth': profile.minimum_depth,
        'wallet_depth': wallet_depth,
        'spacing': spacing,
        'missing_phases': sum(not p['height_eligible'] for p in phases),
        'minimum_margin': min(p['remaining_height_margin'] for p in phases),
        'phases': phases,
    }


def action_at_height(
    policy: str,
    step: int,
    candidate_height: int,
    anchor: int,
    spacing: int,
    wallet_depth: int,
    profile: AnchorProfile,
) -> tuple[str, int]:
    """All non-hold policies raise fees at step 5; reserve is two blocks.

    The decision receives no future workload, scheduled congestion end, measured
    outcome, or later block. Changing payload bytes is only a modeled rebuild.
    """
    if policy not in POLICIES:
        raise ValueError(f'unknown policy: {policy}')
    integer('step', step)
    integer('candidate height', candidate_height)
    integer('anchor', anchor)
    if policy == 'hold' or step != 5:
        return 'hold', anchor
    if policy == 'refresh_on_bump' and anchor + profile.window - candidate_height < 2:
        refreshed = profile.choose(candidate_height, spacing, wallet_depth)
        if refreshed is None:
            raise ValueError('no height-eligible boundary for rebuild')
        return 'rebuild', refreshed
    return 'bump', anchor


def make_payload(anchor: int, attempt: int) -> bytes:
    """610 bytes matching the paper's illustrative size, not its encoding.

    LABSB1 is an unmistakable lab header. Public test markers occupy the two
    nominal nullifier slots. Remaining bytes are deterministic arbitrary data.
    """
    integer('anchor', anchor)
    integer('attempt', attempt)
    if anchor > 0xFFFFFFFF:
        raise ValueError('anchor exceeds uint32')
    markers = b''.join(hashlib.sha256(f'public-lab-input-{i}'.encode()).digest() for i in range(2))
    tail = hashlib.shake_256(f'public-lab-output-{anchor}-{attempt}'.encode()).digest(534)
    return b'LABSB1' + struct.pack('<I', anchor) + bytes([2, 2]) + markers + tail


def payload_fields(payload: bytes) -> dict:
    if len(payload) != 610 or payload[:6] != b'LABSB1' or payload[10:12] != bytes([2, 2]):
        raise ValueError('not a 610-byte LABSB1 payload')
    return {
        'anchor_height': struct.unpack('<I', payload[6:10])[0],
        'synthetic_input_markers': [payload[12:44].hex(), payload[44:76].hex()],
        'authentic_shielded_envelope': False,
    }
