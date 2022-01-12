"""Helper functions used in toolkit"""
from functools import lru_cache
import typing

def lazy_property(property_function:typing.Callable):
    """Alternative for functools.cached_property.

    functools.cached_property is only available since python 3.8.
    Should be replaced with functools.cached_property once no version below
    python 3.8 is supported.

    Args:
        property_function (Callable): property function

    Returns
        Any: Retun value of the property function

    """
    return property(lru_cache()(property_function))
