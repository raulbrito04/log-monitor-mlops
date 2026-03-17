# scripts/explore_features.py

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Carregar dataset
df = pd.read_pickle('data/ml_dataset.pkl')

print("="*60)
print("DATASET SUMMARY")
print("="*60)
print(f"\nShape: {df.shape}")
print(f"\nColumns: {list(df.columns)}")
print(f"\nLabel distribution:")
print(df['label'].value_counts())
print(f"\nAnomaly rate: {100*df['label'].mean():.2f}%")

# Estatísticas
print(f"\n{df.describe()}")

# Correlação com label
correlations = df.corr()['label'].sort_values(ascending=False)
print(f"\nTop 10 features correlacionadas com label:")
print(correlations.head(10))

# Visualização
plt.figure(figsize=(12, 8))
sns.heatmap(df.corr(), cmap='coolwarm', center=0, annot=False)
plt.title('Feature Correlation Matrix')
plt.tight_layout()
plt.savefig('data/correlation_matrix.png', dpi=150)
print(f"\n✓ Saved correlation_matrix.png")
