from typing import Dict, Optional


# Scoring tables: {raw_score: scaled_score}
SCORING_TABLES: Dict[str, Dict[int, int]] = {
    "ukr_mova": {
        8: 100, 9: 105, 10: 110, 11: 120, 12: 125, 13: 130, 14: 134, 15: 136, 16: 138, 17: 140, 
        18: 142, 19: 143, 20: 144, 21: 145, 22: 146, 23: 148, 24: 149, 25: 150, 26: 152, 27: 154, 
        28: 156, 29: 157, 30: 159, 31: 160, 32: 162, 33: 163, 34: 165, 35: 167, 36: 170, 37: 172, 
        38: 175, 39: 177, 40: 180, 41: 183, 42: 186, 43: 191, 44: 195, 45: 200
    },
    "math": {
        5: 100, 6: 108, 7: 115, 8: 123, 9: 131, 10: 134, 11: 137, 12: 140, 13: 143, 14: 145, 
        15: 147, 16: 148, 17: 149, 18: 150, 19: 151, 20: 152, 21: 155, 22: 159, 23: 163, 24: 167, 
        25: 170, 26: 173, 27: 176, 28: 180, 29: 184, 30: 189, 31: 194, 32: 200
    },
    "ukr_history": {
        9: 100, 10: 105, 11: 110, 12: 115, 13: 120, 14: 125, 15: 130, 16: 132, 17: 134, 18: 136, 
        19: 138, 20: 140, 21: 141, 22: 142, 23: 143, 24: 144, 25: 145, 26: 146, 27: 147, 28: 148, 
        29: 149, 30: 150, 31: 151, 32: 152, 33: 154, 34: 156, 35: 158, 36: 160, 37: 163, 38: 166, 
        39: 168, 40: 169, 41: 170, 42: 172, 43: 173, 44: 175, 45: 177, 46: 179, 47: 181, 48: 183, 
        49: 185, 50: 188, 51: 191, 52: 194, 53: 197, 54: 200
    },
    "inozemna_mova": {
        5: 100, 6: 109, 7: 118, 8: 125, 9: 131, 10: 134, 11: 137, 12: 140, 13: 143, 14: 145, 
        15: 147, 16: 148, 17: 149, 18: 150, 19: 151, 20: 152, 21: 153, 22: 155, 23: 157, 24: 159, 
        25: 162, 26: 166, 27: 169, 28: 173, 29: 179, 30: 185, 31: 191, 32: 200
    },
    "biology": {
        7: 100, 8: 107, 9: 114, 10: 119, 11: 124, 12: 128, 13: 131, 14: 134, 15: 136, 16: 138, 17: 140, 18: 142, 19: 144, 20: 145, 21: 146, 22: 147, 23: 148, 24: 149, 25: 150, 26: 151, 27: 152, 28: 154, 29: 156, 30: 158, 31: 160, 32: 162, 33: 164, 34: 166, 35: 168, 36: 170, 37: 172, 38: 175, 39: 177, 40: 179, 41: 182, 42: 185, 43: 188, 44: 192, 45: 196, 46: 200
    },
    "physics": {
        5: 100, 6: 109, 7: 118, 8: 125, 9: 131, 10: 134, 11: 137, 12: 140, 13: 143, 14: 145, 15: 147, 16: 148, 17: 149, 18: 150, 19: 151, 20: 152, 21: 156, 22: 160, 23: 164, 24: 166, 25: 169, 26: 173, 27: 176, 28: 179, 29: 184, 30: 189, 31: 194, 32: 200
    },
    "chemestry": {
        5: 100, 6: 109, 7: 118, 8: 125, 9: 131, 10: 134, 11: 137, 12: 140, 13: 143, 14: 145, 15: 147, 16: 148, 17: 149, 18: 150, 19: 151, 20: 152, 21: 156, 22: 160, 23: 164, 24: 167, 25: 170, 26: 173, 27: 176, 28: 180, 29: 184, 30: 189, 31: 194, 32: 200
    },
    "georgraphy": {
        7: 100, 8: 107, 9: 114, 10: 119, 11: 124, 12: 128, 13: 131, 14: 134, 15: 136, 16: 138, 17: 140, 18: 142, 19: 144, 20: 145, 21: 146, 22: 147, 23: 148, 24: 149, 25: 150, 26: 151, 27: 152, 28: 154, 29: 156, 30: 158, 31: 160, 32: 162, 33: 164, 34: 166, 35: 168, 36: 170, 37: 172, 38: 175, 39: 177, 40: 179, 41: 182, 42: 185, 43: 188, 44: 192, 45: 196, 46: 200
    },
    "ukr_lit": {
        7: 100, 8: 105, 9: 110, 10: 115, 11: 120, 12: 125, 13: 131, 14: 134, 15: 136, 16: 138, 17: 140, 18: 142, 19: 143, 20: 144, 21: 145, 22: 146, 23: 148, 24: 149, 25: 150, 26: 152, 27: 154, 28: 156, 29: 157, 30: 159, 31: 160, 32: 162, 33: 163, 34: 165, 35: 167, 36: 170, 37: 172, 38: 175, 39: 177, 40: 180, 41: 183, 42: 186, 43: 191, 44: 195, 45: 200
    }
}

# Aliases mapping bot subject slugs to scoring table keys
_SUBJECT_ALIASES: Dict[str, str] = {
    "mova": "ukr_mova",
    "hist": "ukr_history",
    "eng":  "inozemna_mova",
}


def get_scaled_score(subject: str, raw_score: float, max_possible: int = 0) -> float:
    """
    Returns the scaled (100-200) score for a subject based on raw score.

    If max_possible is given and is less than the table's maximum raw score,
    the table is incomplete for this test — use the proportional formula instead:
        scaled = (raw_score / max_possible) * 100 + 100
    This keeps the result in the 100-200 range regardless of how many questions
    the simulation contains.
    """
    if raw_score <= 0:
        return 0

    resolved = _SUBJECT_ALIASES.get(subject, subject)
    table = SCORING_TABLES.get(resolved)
    if not table:
        return raw_score  # subject has no lookup table — return raw directly

    table_max = max(table.keys())

    # Incomplete test: proportional formula
    if max_possible > 0 and max_possible < table_max:
        return (raw_score / max_possible) * 100 + 100

    # Full test: direct table lookup
    int_score = int(raw_score)
    if int_score in table:
        return float(table[int_score])

    min_tb = min(table.keys())
    if int_score < min_tb:
        return 0.0
    if int_score > table_max:
        return 200.0

    return float(table.get(int_score, 100.0))

def get_nmt_score(subject: str, raw_score: float, max_possible: int = 0) -> Optional[int]:
    """Alias for get_scaled_score to maintain compatibility with simulation.py"""
    score = get_scaled_score(subject, raw_score, max_possible)
    return int(score) if score >= 100 else None

def calculate_kb_2026(
    p1: float, k1: float, # Mova
    p2: float, k2: float, # Hist
    p3: float, k3: float, # Math
    p4: float, k4: float, # 4th
    k4max: float,
    tk: float = 0, kt: float = 0, # Tvorch
    ou: float = 0, # Courses bonus
    rk: float = 1.0, # Region
    gk: float = 1.0  # Galuzevy
) -> float:
    """
    Formula:
    KB = ((K1*P1 + K2*P2 + K3*P3 + K4*P4 + KT*TK) / (K1 + K2 + K3 + (K4max + K4)/2 + KT) + OU) * RK * GK
    """
    numerator = (k1 * p1) + (k2 * p2) + (k3 * p3) + (k4 * p4) + (kt * tk)
    denominator = k1 + k2 + k3 + ((k4max + k4) / 2) + kt
    
    if denominator == 0:
        return 0.0
    
    kb = (numerator / denominator + ou) * rk * gk
    
    # Precision: Round to 0.001. Max 200.000.
    kb = round(kb, 3)
    return min(200.0, kb)

def get_raw_score_equivalent(subject: str, nmt_score: int) -> int:
    """
    Returns the raw score (TB) equivalent for a given subject and NMT score.
    Uses a reverse lookup in SCORING_TABLES.
    """
    resolved = _SUBJECT_ALIASES.get(subject, subject)
    table = SCORING_TABLES.get(resolved)
    if not table:
        return nmt_score # Direct mapping for subjects without tables
    
    # Reverse lookup: find all raw scores that yield >= nmt_score
    raw_scores = [raw for raw, scaled in table.items() if scaled >= nmt_score]
    
    if not raw_scores:
        # If nmt_score is too high, return max possible
        return max(table.keys())
    
    # Return the minimum raw score that achieves at least this nmt_score
    return min(raw_scores)
