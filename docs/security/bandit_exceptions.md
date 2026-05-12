# Bandit Exceptions and Security Notes

## Rule engine SQL templates
The SQL in `src/detection/rule_engine.py` is static detection logic owned by the application and not assembled from user input at request time.

Decision:
- treat Bandit SQL-expression warnings here as review-required false positives
- do not suppress query-safety expectations for runtime Flask, monitoring, or ingestion paths

## Pickle-based ML artifacts
The ML stack still uses pickle-backed artifacts.

Decision:
- accepted temporarily only for repository-controlled artifacts inside `models/`
- runtime loading is guarded by `_safe_load_pickle()` in `src/ml/hybrid_pipeline.py`
- full artifact format migration is deferred beyond Week 14