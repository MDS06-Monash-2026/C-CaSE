import pandas as pd
import math

def compare_pandas_table(pred: pd.DataFrame, gold: pd.DataFrame, condition_cols=None, ignore_order: bool = False) -> int:
    tolerance = 1e-2
    def normalize(value):
        return 0 if pd.isna(value) else value
    def vectors_match(v1, v2, tol=tolerance, ignore_order_=False):
        v1 = [normalize(x) for x in v1]
        v2 = [normalize(x) for x in v2]
        if ignore_order_:
            v1 = sorted(v1, key=lambda x: (x is None, str(x), isinstance(x, (int, float))))
            v2 = sorted(v2, key=lambda x: (x is None, str(x), isinstance(x, (int, float))))
        if len(v1) != len(v2): return False
        for a, b in zip(v1, v2):
            if pd.isna(a) and pd.isna(b): continue
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if not math.isclose(float(a), float(b), abs_tol=tol): return False
            elif a != b: return False
        return True
    gold_cols = gold.iloc[:, condition_cols] if condition_cols else gold
    t_gold_list = gold_cols.transpose().values.tolist()
    t_pred_list = pred.transpose().values.tolist()
    for gold_vector in t_gold_list:
        if not any(vectors_match(gold_vector, pred_vector, ignore_order_=ignore_order) for pred_vector in t_pred_list):
            return 0
    return 1

gold = pd.read_csv(r"d:\C-CaSE\run\detailed_analysis\bq032\gold.csv")
pred = pd.read_csv(r"d:\C-CaSE\run\detailed_analysis\bq032\slayql.csv")
print("GOLD:", gold.transpose().values.tolist())
print("PRED:", pred.transpose().values.tolist())
print("MATCH:", compare_pandas_table(pred, gold))
