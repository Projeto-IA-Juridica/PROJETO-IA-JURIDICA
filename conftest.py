"""
conftest.py (raiz)
==================
Configurações globais do pytest aplicadas a toda a suite de testes.

audioop foi removido do stdlib no Python 3.13.
pydub depende de audioop; como os testes sempre mocam AudioSegment,
injetamos um stub vazio no sys.modules para evitar ImportError na coleta.
"""

import sys
from unittest.mock import MagicMock

if "audioop" not in sys.modules:
    sys.modules["audioop"] = MagicMock()
