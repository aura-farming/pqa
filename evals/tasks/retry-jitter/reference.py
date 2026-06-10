import random

def backoff_delays(attempts, base, cap, seed):
    rng = random.Random(seed)
    return [rng.uniform(0.0, min(cap, base * (2.0 ** i))) for i in range(attempts)]
