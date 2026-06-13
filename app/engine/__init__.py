"""KataGo engine integration.

Two roles, mirroring Chess Studio's play/analysis split:

* :mod:`analysis_client` drives ``katago analysis`` (JSON over stdio) with the
  b28 network — the eval bar, candidate-move overlays and ownership heatmap.
* :mod:`gtp_client` drives ``katago gtp`` with the human-trained network for
  rank-based, human-like opponents.

The pure clients are Qt-agnostic (callback based) so they can be smoke-tested
headlessly; a thin Qt ``EngineManager`` wrapper (added with the GUI) marshals
their callbacks onto the GUI thread via signals.
"""
