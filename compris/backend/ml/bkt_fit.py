"""Ajustement des paramètres BKT par recherche sur grille, vectorisée avec numpy (rapide)."""
import itertools

import numpy as np

GRID = {
    "p_init": [0.1, 0.3, 0.5, 0.7],
    "p_learn": [0.05, 0.1, 0.2, 0.3],
    "p_guess": [0.05, 0.1, 0.2, 0.3],
    "p_slip": [0.05, 0.1, 0.2],
}
_COMBOS = np.array(list(itertools.product(GRID["p_init"], GRID["p_learn"], GRID["p_guess"], GRID["p_slip"])))


def fit_bkt_grid(seqs: list[list[int]], max_len: int = 60) -> dict:
    """seqs : liste de séquences 0/1 (une par étudiant). Retourne les meilleurs paramètres (max de vraisemblance)."""
    S = len(seqs)
    T = min(max_len, max(len(s) for s in seqs))
    obs = np.zeros((S, T))
    mask = np.zeros((S, T))
    for i, s in enumerate(seqs):
        s = s[:T]
        obs[i, : len(s)] = s
        mask[i, : len(s)] = 1

    init = _COMBOS[:, 0:1]
    learn = _COMBOS[:, 1:2]
    guess = _COMBOS[:, 2:3]
    slip = _COMBOS[:, 3:4]
    G = len(_COMBOS)

    p = np.repeat(init, S, axis=1)  # (G, S)
    ll = np.zeros((G, S))
    for t in range(T):
        pc = p * (1 - slip) + (1 - p) * guess
        o = obs[:, t][None, :]
        m = mask[:, t][None, :]
        lik = np.where(o == 1, pc, 1 - pc)
        ll += m * np.log(np.clip(lik, 1e-9, 1.0))
        post = np.where(
            o == 1,
            p * (1 - slip) / np.clip(pc, 1e-9, None),
            p * slip / np.clip(1 - pc, 1e-9, None),
        )
        p = np.where(m == 1, post + (1 - post) * learn, p)

    best = int(ll.sum(axis=1).argmax())
    b = _COMBOS[best]
    return {"p_init": float(b[0]), "p_learn": float(b[1]), "p_guess": float(b[2]), "p_slip": float(b[3])}
