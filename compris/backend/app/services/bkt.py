"""Bayesian Knowledge Tracing — fonctions pures, partagées par l'API et par l'entraînement (ml/)."""

DEFAULT_PARAMS = {"p_init": 0.30, "p_learn": 0.15, "p_guess": 0.20, "p_slip": 0.10}


def p_correct(p_known: float, params: dict) -> float:
    """Probabilité de répondre juste, sachant la maîtrise actuelle."""
    return p_known * (1 - params["p_slip"]) + (1 - p_known) * params["p_guess"]


def update(p_known: float, correct: bool, params: dict) -> float:
    """Mise à jour bayésienne de la maîtrise après une réponse, puis étape d'apprentissage."""
    s, g, t = params["p_slip"], params["p_guess"], params["p_learn"]
    if correct:
        num = p_known * (1 - s)
        den = num + (1 - p_known) * g
    else:
        num = p_known * s
        den = num + (1 - p_known) * (1 - g)
    posterior = num / den if den > 0 else p_known
    return posterior + (1 - posterior) * t


def predict_sequence(seq: list[int], params: dict) -> list[float]:
    """Prédit P(correct) à chaque pas d'une séquence (avant d'observer la réponse)."""
    preds, p = [], params["p_init"]
    for c in seq:
        preds.append(p_correct(p, params))
        p = update(p, bool(c), params)
    return preds
