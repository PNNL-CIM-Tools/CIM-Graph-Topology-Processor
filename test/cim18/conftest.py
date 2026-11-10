"""cim18v17 fixtures.

IEEE13_CDPSM and tier2_switch_delimited come from a CIMTBL-Models checkout: ``$CIMTBL_MODELS``, else the
sibling ``../CIMTBL-Models`` (like the uv sources); tests that need it skip without it. The node-breaker
substation is in ``test/test_models``.

``cimtables.load_model`` writes the profile and model scope into the process environment; each load
here restores it afterwards, so the cim17 tests (which select ``cimhub_2023``) are not affected.
"""
import os
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
CIMTBL_MODELS = Path(os.environ.get('CIMTBL_MODELS', REPO.parent / 'CIMTBL-Models'))
IEEE13 = CIMTBL_MODELS / 'distribution' / 'IEEE' / 'IEEE13_CDPSM' / 'IEEE13_CDPSM.cimtbl'
TIER2 = CIMTBL_MODELS / 'tiered_tso_dso' / 'IEEE13' / 'tier2_switch_delimited.cimtbl'
NODE_BREAKER = REPO / 'test' / 'test_models' / 'node_breaker_substation.cimtbl'

_ENVIRONMENT = ('CIMG_CIM_PROFILE', 'CIMG_MODEL_AUTHORITY', 'CIMG_MODEL_NAME')


def load(path: Path):
    """``cimtables.load_model(path)``, with the process environment put back afterwards."""
    if not path.exists():
        pytest.skip(f'{path} not found (set CIMTBL_MODELS to a CIMTBL-Models checkout)')
    import cimtables
    from cimgraph.core.env_vars import get_cim_profile
    with pytest.MonkeyPatch.context() as env:
        for name in _ENVIRONMENT:
            if name in os.environ:
                env.setenv(name, os.environ[name])
            else:
                env.delenv(name, raising=False)
        model = cimtables.load_model(path)
    get_cim_profile.cache_clear()
    return model


@pytest.fixture
def ieee13():
    """A fresh IEEE13_CDPSM FeederModel (the builders change the model they are given)."""
    return load(IEEE13)


@pytest.fixture
def node_breaker():
    """A fresh node-breaker substation NodeBreakerModel."""
    return load(NODE_BREAKER)
