import csv
import math

# Use standard library to avoid pandas issues
def t_dist_ppf(p, df):
    # Approximation for 95% CI t-value
    # For df=11 (N=12), t(0.975) is 2.201
    # For df=5 (N=6), t(0.975) is 2.571
    if df == 11: return 2.201
    if df == 5: return 2.571
    return 2.0  # generic fallback

data = []
with open('./user_study_analysis/output/combined_cleaned_data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        data.append(row)

metrics = ['mental_demand', 'physical_demand', 'temporal_demand', 'frustration', 'effort', 'performance', 'nasa_workload_5d']

user_data = {}
for row in data:
    uid = row['user_id']
    cond = row['condition']
    if uid not in user_data:
        user_data[uid] = {}
    user_data[uid][cond] = row

def print_stats(name, pairs):
    if not pairs:
        return
    n = len(pairs)
    a_vals = [p[0] for p in pairs]
    b_vals = [p[1] for p in pairs]
    diffs = [a - b for a, b in pairs]
    
    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n
    mean_diff = sum(diffs) / n
    
    var_a = sum((x - mean_a)**2 for x in a_vals) / (n - 1) if n > 1 else 0
    var_b = sum((x - mean_b)**2 for x in b_vals) / (n - 1) if n > 1 else 0
    var_diff = sum((x - mean_diff)**2 for x in diffs) / (n - 1) if n > 1 else 0
    
    std_a = math.sqrt(var_a)
    std_b = math.sqrt(var_b)
    std_diff = math.sqrt(var_diff)
    
    t_stat = mean_diff / (std_diff / math.sqrt(n)) if std_diff > 0 else float('inf')
    d = mean_diff / std_diff if std_diff > 0 else float('inf')
    
    t_crit = t_dist_ppf(0.975, n - 1)
    margin = t_crit * (std_diff / math.sqrt(n))
    ci_lower = mean_diff - margin
    ci_upper = mean_diff + margin
    
    # Wilcoxon signed-rank (approximate)
    abs_diffs = [(abs(x), x) for x in diffs if x != 0]
    abs_diffs.sort(key=lambda x: x[0])
    ranks = {}
    for i, (abs_val, orig) in enumerate(abs_diffs):
        ranks[i] = (abs_val, orig, i + 1)
    
    w_plus = sum(i+1 for abs_val, orig, idx in ranks.values() if orig > 0)
    w_minus = sum(i+1 for abs_val, orig, idx in ranks.values() if orig < 0)
    w_stat = min(w_plus, w_minus)
    
    print(f"[{name}] N={n}")
    print(f"Cond 1 (A) Mean = {mean_a:.2f} (SD={std_a:.2f})")
    print(f"Cond 2 (Other) Mean = {mean_b:.2f} (SD={std_b:.2f})")
    print(f"Paired t-test: t = {t_stat:.2f}")
    print(f"Cohen's d: {d:.2f}")
    print(f"95% CI of diff: [{ci_lower:.2f}, {ci_upper:.2f}]")
    print(f"Wilcoxon W: {w_stat}")
    print()

for metric in metrics:
    print(f"===== Metric: {metric} =====")
    
    pairs_ab = []
    pairs_ac = []
    pairs_a_other = []
    
    for uid, conds in user_data.items():
        if 'Condition A' in conds:
            a_val = float(conds['Condition A'][metric])
            if 'Condition B' in conds:
                b_val = float(conds['Condition B'][metric])
                pairs_ab.append((a_val, b_val))
                pairs_a_other.append((a_val, b_val))
            elif 'Condition C' in conds:
                c_val = float(conds['Condition C'][metric])
                pairs_ac.append((a_val, c_val))
                pairs_a_other.append((a_val, c_val))
                
    print_stats("A vs B", pairs_ab)
    print_stats("A vs C", pairs_ac)
    print_stats("A vs (B or C)", pairs_a_other)

