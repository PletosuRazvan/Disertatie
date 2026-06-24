from flask import Blueprint

auth_bp        = None  # imported lazily to avoid circular imports
results_bp     = None
predictions_bp = None
standings_bp   = None
