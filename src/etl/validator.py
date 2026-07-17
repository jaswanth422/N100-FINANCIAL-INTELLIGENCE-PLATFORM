"""Compatibility module exposing the 16-rule validator."""

from nifty100_etl.validation import RULES, main, validate_sources, write_validation_failures

__all__ = ["RULES", "main", "validate_sources", "write_validation_failures"]



if __name__ == "__main__":
    raise SystemExit(main())
