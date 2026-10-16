# CI only: build the t5dr target against ps3recomp's synthetic "smoke title"
# instead of a game's lift, so CMakeLists.txt, the patched boot scaffold
# (ppu_loader.cpp, boot_main.cpp, ...) and the runtime library configure,
# compile and LINK on a machine with no game data. See docs/CI.md.
#
#   python <ps3recomp>/tools/make_smoke_elf.py --out <dir>/smoke.elf --header <dir>/ppu_recomp.h
#   cmake -S . -B <build> -G Ninja ... -DPS3RECOMP_DIR=<ps3recomp> -DRECOMP_DIR=<dir> \
#         -DCMAKE_PROJECT_t5dr_INCLUDE=tests/smoke_t5dr.cmake
#   cmake --build <build> --target t5dr
#
# A real lift is .cpp files (CMakeLists.txt globs RECOMP_DIR/*.cpp); the smoke
# title is one hand-written C file in the ps3recomp tree, so it is added here,
# deferred until CMakeLists.txt has defined t5dr. It also wants
# runtime/platform on the include path (win32_compat.h), which real lifts don't.
set(_smoke "${PS3RECOMP_DIR}/runtime/ppu/tests/smoke/smoke_recomp.c")
if(NOT EXISTS "${_smoke}")
    message(FATAL_ERROR "smoke_t5dr.cmake: no ${_smoke} (pass an absolute -DPS3RECOMP_DIR)")
endif()
cmake_language(DEFER CALL target_sources t5dr PRIVATE "${_smoke}")
cmake_language(DEFER CALL target_include_directories t5dr PRIVATE "${PS3RECOMP_DIR}/runtime/platform")
message(STATUS "CI smoke build: t5dr links ps3recomp's smoke title (${_smoke})")
