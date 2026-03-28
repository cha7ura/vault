from .msdd.msdd import MSDDDiarizer
from .sortformer.sortformer import SortformerDiarizer


def PyannoteDiarizer(*args, **kwargs):
    from .pyannote.pyannote import PyannoteDiarizer as _Cls
    return _Cls(*args, **kwargs)


__all__ = ["MSDDDiarizer", "PyannoteDiarizer", "SortformerDiarizer"]
