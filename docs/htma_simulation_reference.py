"""Reference implementation of the seven methods in HTMA_3rd_Ch6-2.xlsx.

Stdlib only; Python 3.10+. Designed for understanding and porting, not to
recreate Excel's proprietary RAND sequences. Contains explicitly named legacy
compatibility functions where the workbook's implementation is questionable.

Usage: python htma_simulation_reference.py
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import sqrt
import random
from statistics import NormalDist, correlation, mean
from typing import Sequence


_STANDARD_NORMAL = NormalDist()
_MIN_U = 2**-53


@dataclass(frozen=True)
class NormalEstimate:
    lower: float
    expected: float
    upper: float

    def __post_init__(self):
        if not self.lower < self.upper:
            raise ValueError("lower must be < upper")
        if not self.lower <= self.expected <= self.upper:
            raise ValueError("expected must lie inside lower/upper estimates")

    @property
    def sigma(self) -> float:
        # Literal fidelity to the workbook, not a hard-bound normal distribution.
        return (self.upper - self.lower) / 3.29

    def sample(self, rng: random.Random) -> float:
        u = min(1.0 - _MIN_U, max(_MIN_U, rng.random()))
        return self.expected + self.sigma * _STANDARD_NORMAL.inv_cdf(u)


MAINTENANCE = NormalEstimate(10.0, 15.0, 20.0)
LABOR = NormalEstimate(-2.0, 3.0, 8.0)
MATERIALS = NormalEstimate(3.0, 6.0, 9.0)
PRODUCTION = NormalEstimate(15_000.0, 25_000.0, 35_000.0)


def summarize_savings(savings: Sequence[float], annual_lease: float = 400_000.0) -> dict:
    if not savings:
        raise ValueError("Cannot summarize an empty set of scenarios")
    success = sum(value > annual_lease for value in savings)  # Excel strict '>'
    return {
        "iterations": len(savings),
        "success_count": success,
        "success_probability": success / len(savings),
        "loss_probability": 1 - success / len(savings),
        "average_annual_savings": mean(savings),
        "mean_net_annual_savings": mean(savings) - annual_lease,
    }


def first_monte_carlo(n: int = 10_000, seed: int = 42, annual_lease: float = 400_000.0) -> dict:
    """Reimplements FirstMCExample!B16:G15185."""
    if n <= 0:
        raise ValueError("n must be positive")
    rng = random.Random(seed)
    savings = []
    for _ in range(n):
        maintenance = MAINTENANCE.sample(rng)
        labor = LABOR.sample(rng)
        materials = MATERIALS.sample(rng)
        units = PRODUCTION.sample(rng)
        savings.append((maintenance + labor + materials) * units)
    return {**summarize_savings(savings, annual_lease), "savings": savings}


def monte_carlo_with_contract_loss(
    n: int = 10_000,
    seed: int = 42,
    annual_lease: float = 400_000.0,
    contract_size: float = 1000.0,
    contract_loss_probability: float = 0.1,
    months_remaining_upper: float = 12.0,
    months_remaining_lower: float = 0.0,
) -> dict:
    """Equivalent *distribution* to MCExampleWcontractloss; avoids IFERROR/RAND hack.

    Note: one baseline production draw per scenario, and a second random draw
    for months remaining only when the contract was lost.
    """
    if n <= 0 or not 0.0 <= contract_loss_probability <= 1.0:
        raise ValueError("Invalid n or contract_loss_probability")
    if months_remaining_lower > months_remaining_upper:
        raise ValueError("Invalid months remaining interval")
    rng = random.Random(seed)
    savings = []
    lost_contracts = 0
    scenarios = []
    for _ in range(n):
        maintenance = MAINTENANCE.sample(rng)
        labor = LABOR.sample(rng)
        materials = MATERIALS.sample(rng)
        loss = rng.random() < contract_loss_probability
        remaining = rng.uniform(months_remaining_lower, months_remaining_upper) if loss else None
        baseline_units = PRODUCTION.sample(rng)
        lost_units = contract_size * remaining / 12.0 if loss else 0.0
        adjusted_units = baseline_units - lost_units
        annual_savings = (maintenance + labor + materials) * adjusted_units
        savings.append(annual_savings)
        lost_contracts += int(loss)
        scenarios.append({"contract_lost": loss, "months_remaining": remaining,
                          "base_units": baseline_units, "adjusted_units": adjusted_units,
                          "annual_savings": annual_savings})
    return {**summarize_savings(savings, annual_lease),
            "contract_loss_count": lost_contracts,
            "observed_contract_loss_probability": lost_contracts / n,
            "savings": savings, "scenarios": scenarios}


def triangular_sample(minimum: float, mode: float, maximum: float, rng: random.Random) -> float:
    """Exact distribution of TriangularDist!B11/B14 (MAX/MIN of two uniforms)."""
    if not minimum <= mode <= maximum or minimum == maximum:
        raise ValueError("Required: minimum <= mode <= maximum and distinct bounds")
    p_left = (mode - minimum) / (maximum - minimum)
    if rng.random() < p_left:
        return minimum + max(rng.random(), rng.random()) * (mode - minimum)
    return mode + min(rng.random(), rng.random()) * (maximum - mode)


def triangular_true_mean(minimum: float, mode: float, maximum: float) -> float:
    return (minimum + mode + maximum) / 3.0


def triangular_excel_b12(minimum: float, mode: float, maximum: float) -> float:
    """The workbook's incorrectly labeled 'Mean' -- weighted branch medians."""
    p_left = (mode - minimum) / (maximum - minimum)
    return (p_left * (sqrt(0.5) * (mode - minimum) + minimum)
            + (1 - p_left) * (maximum - sqrt(0.5) * (maximum - mode)))


def pert_shape(minimum: float, mode: float, maximum: float, weight: float = 4) -> tuple[float, float]:
    """Validated modified PERT: BETA(alpha,beta), scaled to [minimum,maximum]."""
    if not minimum <= mode <= maximum or minimum == maximum or weight <= 0:
        raise ValueError("Invalid PERT input")
    relative_mode = (mode - minimum) / (maximum - minimum)
    return 1.0 + weight * relative_mode, 1.0 + weight * (1.0 - relative_mode)


def beta_pert_sample(minimum: float, mode: float, maximum: float, rng: random.Random) -> float:
    alpha, beta = pert_shape(minimum, mode, maximum)
    return minimum + (maximum - minimum) * rng.betavariate(alpha, beta)


def beta_excel_legacy_shapes(minimum: float, mode: float, maximum: float) -> tuple[float, float]:
    """Literal BetaDist!B7:B9 and the reciprocals passed into BETAINV.

    Important: this does NOT produce the expected beta-PERT distribution.
    """
    relative_mean = ((mode - minimum) / (maximum - minimum) * 4.0 + 1.0) / 6.0
    A = relative_mean**2 * (1 - relative_mean) * 36.0 - 1.0
    B = (1 - relative_mean) / relative_mean * A
    if A <= 0 or B <= 0:
        raise ValueError("Excel legacy beta shape becomes invalid")
    return 1 / A, 1 / B


def beta_excel_legacy_normalized_sample(
    minimum: float, mode: float, maximum: float, rng: random.Random
) -> float:
    """Matches normalized B10 distribution; does not scale to [min,max]."""
    alpha, beta = beta_excel_legacy_shapes(minimum, mode, maximum)
    return rng.betavariate(alpha, beta)


def power_law_sample(slope_a: float, intercept_b: float, rng: random.Random) -> float:
    """Excel PowerLawDist!B6 / B32: Pareto with xmin=10**b, shape=1/a."""
    if slope_a <= 0:
        raise ValueError("For a valid Pareto law slope_a must be positive")
    u = max(_MIN_U, rng.random())
    return 10.0**intercept_b * u**(-slope_a)


def histogram_by_upper_cutoffs(samples: Sequence[float], boundaries: Sequence[float],
                               inclusive: bool = True) -> list[dict]:
    """Excel-style cumulative COUNTIF and adjacent differences. Last bin isn't overflow.

    FirstMC / Contract histogram: inclusive True (<=). PowerLaw: False (<).
    """
    if any(x >= y for x, y in zip(boundaries, boundaries[1:])):
        raise ValueError("Boundaries must be strictly increasing")
    sorted_samples = sorted(samples)
    result = []
    previous_cumulative = 0
    for boundary in boundaries:
        cumulative = (bisect_right(sorted_samples, boundary) if inclusive
                      else bisect_left(sorted_samples, boundary))
        result.append({"cutoff": boundary, "cumulative": cumulative,
                       "frequency": cumulative - previous_cumulative})
        previous_cumulative = cumulative
    return result


def forced_correlation(n: int = 1000, rho: float = 0.7, seed: int = 42) -> dict:
    """CorrelatedValues!B26:F1025; produces requested Pearson rho in expectation."""
    if not -1.0 <= rho <= 1.0 or n < 2:
        raise ValueError("rho must be in [-1,1], n>=2")
    rng = random.Random(seed)
    cost_a, cost_b = [], []
    for _ in range(n):
        z1, z2 = _STANDARD_NORMAL.inv_cdf(max(_MIN_U, rng.random())), _STANDARD_NORMAL.inv_cdf(max(_MIN_U, rng.random()))
        z_correlated = rho * z1 + sqrt(1.0 - rho*rho) * z2
        cost_a.append(3.1 + 0.5 * z1)
        cost_b.append(1.4 + 0.16 * z_correlated)
    return {"target_correlation": rho,
            "sample_correlation": correlation(cost_a, cost_b),
            "building_a": cost_a, "building_b": cost_b}


def naturally_correlated_costs(n: int = 1000, seed: int = 42) -> dict:
    """CorrelatedValues!I26:O1025: correlated through SHARED labor rate."""
    if n < 2:
        raise ValueError("n must be >= 2")
    rng = random.Random(seed)
    a_values, b_values = [], []
    for _ in range(n):
        labor_rate = rng.gauss(45.0, 12.0)
        hours_a = rng.gauss(34_000.0, 3_500.0)
        materials_a = rng.gauss(1.6, 0.25)
        hours_b = rng.gauss(28_500.0, 2_600.0)
        materials_b = rng.gauss(1.4, 0.16)
        a_values.append(labor_rate * hours_a / 1_000_000 + materials_a)
        b_values.append(labor_rate * hours_b / 1_000_000 + materials_b)
    return {"sample_correlation": correlation(a_values, b_values),
            "building_a": a_values, "building_b": b_values}


STATES = {1: "A on tail", 2: "B on tail", 3: "Disengaged",
          4: "A victory", 5: "B victory"}
# Row order matches MarkovSimulation!C15:G17; rows 4/5 are absorbing.
DEFAULT_TRANSITIONS = {
    1: (0.60, 0.10, 0.15, 0.15, 0.00),
    2: (0.10, 0.50, 0.30, 0.00, 0.10),
    3: (0.55, 0.45, 0.00, 0.00, 0.00),
    4: (0.00, 0.00, 0.00, 1.00, 0.00),
    5: (0.00, 0.00, 0.00, 0.00, 1.00),
}


def next_markov_state(current: int, uniform: float,
                      transitions: dict[int, tuple[float, ...]] = DEFAULT_TRANSITIONS) -> int:
    if current not in transitions or not 0 <= uniform < 1:
        raise ValueError("Invalid state or uniform probability")
    row = transitions[current]
    if len(row) != 5 or any(p < 0 for p in row) or abs(sum(row) - 1) > 1e-10:
        raise ValueError("Invalid transition matrix row")
    cumulative = 0.0
    for new_state, probability in enumerate(row, 1):
        cumulative += probability
        if uniform < cumulative:
            return new_state
    return 5  # Only possible because of floating-point rounding at the far edge.


def markov_trajectory(initial_state: int = 2, max_rounds: int = 40, seed: int = 42) -> dict:
    """MarkovSimulation!K3:K42; starts in round 1, at most 39 transitions."""
    if initial_state not in STATES or max_rounds < 1:
        raise ValueError("Invalid Markov configuration")
    rng = random.Random(seed)
    states = [initial_state]
    while len(states) < max_rounds and states[-1] not in (4, 5):
        states.append(next_markov_state(states[-1], rng.random()))
    final = states[-1]
    return {"states": states, "labels": [STATES[s] for s in states],
            "last_round": len(states), "is_absorbed": final in (4,5),
            "winner": "A" if final == 4 else "B" if final == 5 else None}


def estimate_markov_outcomes(n: int = 10_000, seed: int = 42,
                             initial_state: int = 2, max_rounds: int = 40) -> dict:
    if n <= 0:
        raise ValueError("n must be positive")
    # Important: use a single persistent RNG stream across trajectories.
    rng = random.Random(seed)
    wins_a = wins_b = unresolved = 0
    rounds = []
    for _ in range(n):
        state = initial_state
        t = 1
        while t < max_rounds and state not in (4, 5):
            state = next_markov_state(state, rng.random())
            t += 1
        rounds.append(t)
        wins_a += state == 4
        wins_b += state == 5
        unresolved += state not in (4, 5)
    return {"n": n, "p_a_victory": wins_a/n, "p_b_victory": wins_b/n,
            "p_unresolved": unresolved/n, "mean_observed_rounds": mean(rounds)}


if __name__ == "__main__":
    for key, output in (
        ("FirstMCExample", first_monte_carlo()),
        ("MCExampleWcontractloss", monte_carlo_with_contract_loss()),
        ("CorrelatedValues forced", forced_correlation()),
        ("CorrelatedValues natural", naturally_correlated_costs()),
        ("MarkovSimulation", estimate_markov_outcomes()),
    ):
        print(key, {k: round(v, 5) if isinstance(v, float) else v
                    for k,v in output.items() if k not in ("savings","scenarios","building_a","building_b")})
    print("Triangular true / workbook mean:", triangular_true_mean(.4,.65,1.4),
          triangular_excel_b12(.4,.65,1.4))
    print("Beta PERT vs workbook shapes:", pert_shape(10,16,28),
          beta_excel_legacy_shapes(10,16,28))
    print("Markov sample first transition:", next_markov_state(2, 0.65484038306679782))
