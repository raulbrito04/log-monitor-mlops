# scripts/quality_checks.py

import pandas as pd
import numpy as np

# Carregar dataset
df = pd.read_pickle('data/ml_dataset.pkl')

print("\nQUALITY CHECKS:")
print("="*60)

# 1. Missing values
missing = df.isnull().sum()
if missing.sum() == 0:
    print("✓ No missing values")
else:
    print(f"✗ Missing values found:\n{missing[missing > 0]}")

# 2. Infinitos
inf_count = np.isinf(df.select_dtypes(include=[np.number])).sum().sum()
if inf_count == 0:
    print("✓ No infinite values")
else:
    print(f"✗ {inf_count} infinite values found")

# 3. Features constantes
constant_cols = [col for col in df.columns if df[col].nunique() == 1]
if len(constant_cols) == 0:
    print("✓ No constant features")
else:
    print(f"✗ Constant features: {constant_cols}")

# 4. Label balance
anomaly_rate = df['label'].mean()
if 0.01 < anomaly_rate < 0.5:
    print(f"✓ Label balance OK ({anomaly_rate:.2%} anomalies)")
else:
    print(f"⚠ Label imbalance: {anomaly_rate:.2%} anomalies")

print("="*60)

