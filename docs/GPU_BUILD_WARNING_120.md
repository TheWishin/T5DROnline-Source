# Graphics warning before building (1.2.0)

The launcher checks the existing local Windows display-adapter registry
collector before BUILD GAME starts. `launcher/gpu_support.py` recognizes
Intel HD 4400-class and older Intel model names and offers a warning with
Continue/Cancel. It needs no prior game launch or game log. A hybrid machine
still gets advice to select its other GPU in Windows Graphics settings.

This is an advisory, not a graphics capability test. The renderer's actual
requirement in patch 0031 is successful `D3D12CreateDevice` with feature level
11_0. Adapter names cannot establish that a particular installed driver
supports this, that the driver is functional, or which adapter Windows will
select. An unrecognized adapter or unavailable registry data is inconclusive
and does not stop a build. No Direct3D device or game is started by the check.

The launcher setting `gpu_build_warning` defaults to true; disabling it only
skips this advisory and does not change renderer requirements or simulation.

`tests/test_gpu_build_warning.py` covers a first build without any game log,
Haswell names, generic historical names, hybrid systems, model-number false
positives, unknown cards, duplicate records, and unavailable detection.
The tests are written but remain unexecuted in this mirror.

Maintainer verification requires a real launcher run: with an HD 4400 fixture
the warning must appear before any build worker starts, Cancel must stop the
build, and Continue must proceed normally. Verify the real installed driver
on an affected PC and hybrid GPU selection separately. No build or game run
was performed for this change. A graphics name does not prove that all cards
in that class categorically cannot run the game.
