# ML Trust Boundary

Week 14 keeps pickle-based model loading only under a controlled trust boundary.

Rules in force:
- only artifacts inside `models/` may be loaded at runtime
- only `.pkl` files are accepted
- artifact paths are resolved and validated before deserialization
- runtime requests do not supply arbitrary model paths

Implication:
- pickle remains a known residual risk if the trusted artifact supply chain is compromised
- this is acceptable for the current academic project scope but should be replaced in a future iteration with a safer artifact strategy