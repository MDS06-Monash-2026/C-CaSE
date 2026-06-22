import math
from typing import Tuple, List

def calculate_retrieval_entropy(similarities: List[float], temp: float = 0.1) -> float:
    """
    Calculate the Shannon Entropy of the retrieved column similarities.
    
    Args:
        similarities: A list of top-K cosine similarity scores.
        temp: Temperature scaling parameter (e.g., 0.1).
        
    Returns:
        Normalized entropy H(P) between 0 and 1.
    """
    if not similarities:
        return 0.0
        
    K = len(similarities)
    if K <= 1:
        return 0.0
        
    # Apply temperature scaling and exponents
    exp_sims = [math.exp(s / temp) for s in similarities]
    sum_exp = sum(exp_sims)
    
    if sum_exp == 0:
        return 0.0
        
    # Normalize to probability distribution
    probs = [e / sum_exp for e in exp_sims]
    
    # Calculate Shannon Entropy
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)
            
    # Normalize by log(K)
    normalized_entropy = entropy / math.log(K)
    return normalized_entropy


def determine_budget(entropy: float, base_turns: int = 10, threshold: float = 0.4) -> Tuple[bool, int]:
    """
    Determine whether to early exit, and calculate the dynamic turn budget.
    
    Args:
        entropy: The calculated normalized entropy.
        base_turns: The baseline maximum turns T_baseline.
        threshold: The low-entropy threshold tau.
        
    Returns:
        should_early_exit (bool): True if entropy < threshold.
        dynamic_t_max (int): Scaled turn budget if not early exiting.
    """
    if entropy < threshold:
        return True, 0
    else:
        dynamic_t_max = round(base_turns * entropy)
        return False, dynamic_t_max
