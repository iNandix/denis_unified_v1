"""
Legacy compatibility shim for denisunifiedv1.featureflags.
Provides loadfeatureflags() function that delegates to feature_flags.load_feature_flags().
"""

from feature_flags import load_feature_flags as loadfeatureflags

__all__ = ["loadfeatureflags"]
