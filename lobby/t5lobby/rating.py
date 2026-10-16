"""Glicko-2 (Mark Glickman, "Example of the Glicko-2 system", 2012).

Every finished ranked match is one rating period for both players. A rating
is (r, rd, vol): the displayed rating, its deviation and the volatility.
Ratings deviation also grows while a player is inactive (inflate()).
"""
import math
from dataclasses import dataclass

SCALE = 173.7178
DEFAULT_R = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOL = 0.06
TAU = 0.5          # system constant: how fast volatility may change
EPS = 1e-6
MIN_RD = 30.0
MAX_RD = 350.0


@dataclass
class Rating:
    r: float = DEFAULT_R
    rd: float = DEFAULT_RD
    vol: float = DEFAULT_VOL

    def as_dict(self):
        return {"r": round(self.r, 1), "rd": round(self.rd, 1), "vol": round(self.vol, 6)}


def _g(phi):
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu, mu_j, phi_j):
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def expected(a, b):
    """Probability that a beats b."""
    return _e((a.r - DEFAULT_R) / SCALE, (b.r - DEFAULT_R) / SCALE,
              math.sqrt((a.rd / SCALE) ** 2 + (b.rd / SCALE) ** 2))


def update(player, results, tau=TAU):
    """New Rating for `player` after `results` = [(opponent Rating, score)], score 1 / 0.5 / 0."""
    mu = (player.r - DEFAULT_R) / SCALE
    phi = player.rd / SCALE
    sigma = player.vol
    if not results:
        phi_star = math.sqrt(phi * phi + sigma * sigma)
        return Rating(player.r, min(MAX_RD, phi_star * SCALE), sigma)

    v_inv = 0.0
    dsum = 0.0
    for opp, s in results:
        mu_j = (opp.r - DEFAULT_R) / SCALE
        phi_j = opp.rd / SCALE
        g = _g(phi_j)
        e = _e(mu, mu_j, phi_j)
        v_inv += g * g * e * (1.0 - e)
        dsum += g * (s - e)
    v = 1.0 / v_inv
    delta = v * dsum

    # New volatility: Illinois algorithm on f(x) (step 5 of the paper).
    a = math.log(sigma * sigma)

    def f(x):
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (tau * tau)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau
    fa, fb = f(big_a), f(big_b)
    for _ in range(100):
        if abs(big_b - big_a) <= EPS:
            break
        c = big_a + (big_a - big_b) * fa / (fb - fa)
        fc = f(c)
        if fc * fb <= 0:
            big_a, fa = big_b, fb
        else:
            fa /= 2.0
        big_b, fb = c, fc
    sigma_new = math.exp(big_a / 2.0)

    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * dsum
    return Rating(mu_new * SCALE + DEFAULT_R, max(MIN_RD, min(MAX_RD, phi_new * SCALE)), sigma_new)


def inflate(rating, idle_days, days_per_period=7.0):
    """RD growth over inactivity: one empty rating period per `days_per_period` days."""
    periods = max(0.0, idle_days) / days_per_period
    if periods <= 0:
        return rating
    phi = rating.rd / SCALE
    phi_star = math.sqrt(phi * phi + periods * rating.vol * rating.vol)
    return Rating(rating.r, min(MAX_RD, phi_star * SCALE), rating.vol)


def match(a, b, score_a):
    """Both players' new ratings after one game; score_a = 1 (a won), 0.5 (draw), 0 (b won)."""
    return update(a, [(b, score_a)]), update(b, [(a, 1.0 - score_a)])
