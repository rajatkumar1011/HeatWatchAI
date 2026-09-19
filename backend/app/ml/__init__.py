"""HeatWatch AI machine-learning components.

Layout
------
- features.py         shared feature engineering (training + inference parity)
- train_severity.py   reproducible training/evaluation script (scikit-learn)
- inference.py        SeverityPredictor: artifact loading + prediction
- artifacts/          serialized model + metadata (joblib + JSON)

Model provenance is documented in docs/model/model_card.md. In short: when
no aligned historical weather+sentiment dataset with heatwave labels exists
in the repository (it does not), the weather-based severity model is trained
on a transparent, reproducible dataset whose labels follow the documented
NWS heat-index risk banding, and sentiment is combined through an explicitly
rule-based, transparent fusion layer — never presented as learned fusion.
"""
