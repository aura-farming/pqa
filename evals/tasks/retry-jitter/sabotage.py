import random

def backoff_delays(attempts, base, cap, seed):  # jitters the UNCAPPED range, then clips
    rng = random.Random(seed)
    return [min(cap, rng.uniform(0.0, base * (2.0 ** i))) for i in range(attempts)]
