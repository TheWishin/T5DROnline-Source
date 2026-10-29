# Tekken 5: Dark Resurrection Online (NPUB30009 v01.00) -- native Windows build.
#
# Builds the game from the player's own copy: the lifted C++ in build/recomp/
# comes from their decrypted EBOOT (tools/build_game.py), the runtime from a
# ps3recomp checkout. Neither is in this repository.
#
#   cmake -S . -B build/cmake -G Ninja -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl
#   cmake --build build/cmake
#   build/cmake/t5dr game/vfs/PS3_GAME/USRDIR/EBOOT.elf
cmake_minimum_required(VERSION 3.20)

# Default to Release: the lifted code is tens of MB of C++ and a Debug build
# runs it several times slower (ps3recomp ports measured 16 vs 49 fps).
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "build type" FORCE)
endif()

project(t5dr C CXX)
if(WIN32)
    enable_language(RC)     # t5dr.exe's version information (src/platform/t5dr.rc.in)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_C_STANDARD 17)

set(PS3RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/deps/ps3recomp" CACHE PATH
    "ps3recomp checkout (NoahBPeterson/ps3recomp, branch infamous/upstream-sync)")
set(RECOMP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/build/recomp" CACHE PATH
    "Lifter output for this game: ppu_recomp.h + ppu_recomp_NNN.cpp")
get_filename_component(PS3RECOMP_DIR "${PS3RECOMP_DIR}" ABSOLUTE)
get_filename_component(RECOMP_DIR "${RECOMP_DIR}" ABSOLUTE)

if(NOT EXISTS "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp")
    message(FATAL_ERROR "No ps3recomp checkout at ${PS3RECOMP_DIR} -- pass -DPS3RECOMP_DIR=")
endif()
# T5DR_GAME_DLL=ON: t5dr.exe is the runtime alone and exports what the lifted code
# calls (tools/gamedll/t5dr_host.def); the lifted PPU/SPU code is built separately
# into t5dr_game.dll by tools/build_game_dll.py, with clang-cl + lld-link and no
# MSVC/Windows SDK headers or libraries -- the part a player's PC would build.
# The host then needs nothing from the game: ppu_loader.cpp and boot_main.cpp only
# use the fixed part of the lifter's header (ppu_lifter.HEADER_PREAMBLE).
option(T5DR_GAME_DLL "Lifted code in t5dr_game.dll (tools/build_game_dll.py) instead of in t5dr.exe" OFF)
if(T5DR_GAME_DLL)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(RECOMP_DIR "${CMAKE_BINARY_DIR}/generic_recomp")
    file(MAKE_DIRECTORY "${RECOMP_DIR}")
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c
                "import sys; sys.path.insert(0, sys.argv[1]); import ppu_lifter; open(sys.argv[2], 'w').write(ppu_lifter.HEADER_PREAMBLE)"
                "${PS3RECOMP_DIR}/tools" "${RECOMP_DIR}/ppu_recomp.h"
        RESULT_VARIABLE HEADER_RC)
    if(HEADER_RC)
        message(FATAL_ERROR "Could not write the generic ppu_recomp.h from ppu_lifter.py")
    endif()
elseif(NOT EXISTS "${RECOMP_DIR}/ppu_recomp.h")
    message(FATAL_ERROR "No lifted code in ${RECOMP_DIR} -- run tools/build_game.py first")
endif()

file(GLOB RECOMP_SOURCES CONFIGURE_DEPENDS "${RECOMP_DIR}/*.cpp")
list(LENGTH RECOMP_SOURCES RECOMP_SOURCE_COUNT)
message(STATUS "ps3recomp:      ${PS3RECOMP_DIR}")
message(STATUS "Lifted sources: ${RECOMP_SOURCE_COUNT} file(s) in ${RECOMP_DIR}")

# The runtime library, built from source so its link requirements come along.
add_subdirectory("${PS3RECOMP_DIR}" "${CMAKE_BINARY_DIR}/ps3recomp" EXCLUDE_FROM_ALL)

# macOS (tools/build_game.py passes it): without glslang and spirv-cross the Metal backend has no
# guest shaders and every draw is dropped, so stop here instead of building a black window.
option(T5DR_REQUIRE_SHADERS "Fail the configure step when the guest shaders cannot be translated" OFF)
if(T5DR_REQUIRE_SHADERS AND NOT TARGET ps3recomp_msl_translation)
    message(FATAL_ERROR "T5DR_REQUIRE_SHADERS: glslang and spirv-cross were not found")
endif()

# Firmware NID -> HLE handler table, generated from the runtime's sources.
find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(HLE_NID_TABLE "${CMAKE_BINARY_DIR}/gen/ppu_hle_nids.cpp")
file(GLOB HLE_LIB_SOURCES CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/libs/*/*.c")
add_custom_command(
    OUTPUT "${HLE_NID_TABLE}"
    COMMAND "${Python3_EXECUTABLE}" "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
            --all --out "${HLE_NID_TABLE}"
    DEPENDS "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
            "${PS3RECOMP_DIR}/tools/nid_database.py"
            ${HLE_LIB_SOURCES}
    COMMENT "Generating the HLE NID table")

# Lifted SPU images (tools/build_game.py step "spu"): <SPU_DIR>/lifted/<image>/
# plus spu_workloads.c, which registers each by content fingerprint so the
# runtime runs the lifted code when the game starts that image.
set(SPU_DIR "${CMAKE_CURRENT_SOURCE_DIR}/build/spu" CACHE PATH "Lifted SPU images")
get_filename_component(SPU_DIR "${SPU_DIR}" ABSOLUTE)
file(GLOB SPU_LIFTED CONFIGURE_DEPENDS "${SPU_DIR}/lifted/*/spu_recomp.c")
set(SPU_SOURCES "")
if(SPU_LIFTED AND EXISTS "${SPU_DIR}/spu_workloads.c")
    list(LENGTH SPU_LIFTED SPU_IMAGE_COUNT)
    message(STATUS "Lifted SPU:     ${SPU_IMAGE_COUNT} image(s)")
    # spu_dispatch_mt.c is the musttail indirect-branch path; it must be built
    # by clang, or deep guest loops walk the thread stack off its guard page.
    set(SPU_SOURCES ${SPU_LIFTED} "${SPU_DIR}/spu_workloads.c"
        "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c")
    set_source_files_properties(${SPU_SOURCES} PROPERTIES
        INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/spu"
        COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
    # The lifted images leave out the local-store debug hooks (SPU_LS_NO_HOOKS in
    # spu_context.h, ps3recomp patch 0064): diagnostics a release never arms, but
    # each one made the compiler reload the SPU register file after every
    # local-store access. Same results; the runtime's own accessors keep them.
    set_property(SOURCE ${SPU_LIFTED} APPEND PROPERTY COMPILE_DEFINITIONS SPU_LS_NO_HOOKS)
    # The vertex skinning jobs (skin1x/skin4x) only produce vertices to draw,
    # never game state: they use the host's IEEE float ops instead of the exact
    # SPU float emulation (SPU_FAST_FLOAT in spu_helpers.h, ps3recomp patch
    # 0027) -- a fight frame's skinning costs about a third of the CPU. The sound
    # core and every other image stay exact. OFF restores the exact path.
    option(T5DR_SPU_FAST_SKIN "IEEE float ops for the render-only SPU skinning jobs" ON)
    file(GLOB SPU_RENDER_JOBS CONFIGURE_DEPENDS "${SPU_DIR}/lifted/skin*/spu_recomp.c")
    if(T5DR_SPU_FAST_SKIN AND SPU_RENDER_JOBS)
        set_property(SOURCE ${SPU_RENDER_JOBS} APPEND PROPERTY COMPILE_DEFINITIONS SPU_FAST_FLOAT)
    endif()
    # The sound core (bnuscore) only makes audio samples. With the exact path it
    # needs 4-7 ms of its 5.33 ms audio tick on a fast desktop core, so a slower
    # CPU misses ticks and the sound breaks up. SPU_NEAR_FLOAT (ps3recomp patch
    # 0041, docs/SOAK.md): the SPU's float rules (no denormals, +0, extended
    # range and overflow on the exact path) in IEEE single precision, rounding
    # to nearest instead of toward zero; the same bits on every x86 CPU and
    # for both build targets. OFF restores the exact path.
    option(T5DR_SPU_NEAR_SOUND "near-exact IEEE float ops for the SPU sound core" ON)
    file(GLOB SPU_SOUND_CORE CONFIGURE_DEPENDS "${SPU_DIR}/lifted/bnuscore/spu_recomp.c")
    if(T5DR_SPU_NEAR_SOUND AND SPU_SOUND_CORE)
        set_property(SOURCE ${SPU_SOUND_CORE} APPEND PROPERTY COMPILE_DEFINITIONS SPU_NEAR_FLOAT)
    endif()
elseif(NOT T5DR_GAME_DLL)
    message(WARNING "No lifted SPU images in ${SPU_DIR} -- the sound core will not run")
endif()

if(T5DR_GAME_DLL)
    set(GAME_SOURCES "")
else()
    set(GAME_SOURCES ${RECOMP_SOURCES} ${SPU_SOURCES})
endif()

# Target CPU of the lifted PPU code (tools/build_game_dll.py --march does the same
# for the player's build). auto = x86-64-v3 (AVX2, FMA, BMI2, MOVBE) when this
# PC has AVX2, else the x86-64 baseline. v3 cut the main thread's work per fight
# frame by ~25-30% (byte-swapped loads/stores become movbe; the fused ops become
# vfmadd). -ffp-contract=off always: with FMA available clang would otherwise
# fuse a*b+c written as two operations, which changes results; the PPU's fused
# ops go through ppu_fp_det.h (ps3recomp patch 0032), which gives the same bits
# with or without FMA instructions and never calls the C runtime's math -- so
# builds for different targets play each other in sync (docs/NETPLAY.md, "Same
# game state on every CPU").
set(T5DR_LIFTED_ARCH "auto" CACHE STRING "-march for the lifted PPU code: auto, x86-64-v3, native, none")
set(_lifted_arch "${T5DR_LIFTED_ARCH}")
if(_lifted_arch STREQUAL "auto")
    set(_lifted_arch "none")
    if(WIN32 AND Python3_EXECUTABLE)
        execute_process(COMMAND "${Python3_EXECUTABLE}" -c
                "import ctypes; print(1 if ctypes.windll.kernel32.IsProcessorFeaturePresent(40) else 0)"
            OUTPUT_VARIABLE _avx2 OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        if(_avx2 STREQUAL "1")
            set(_lifted_arch "x86-64-v3")
        endif()
    endif()
endif()
if(MSVC)
    set(_clang_flag_prefix "/clang:")   # clang-cl forwards GCC-style flags with this prefix
else()
    set(_clang_flag_prefix "")
endif()
# -fno-caret-diagnostics: clang names file(line,col) and the message, without quoting the lifted source line (the
# game's own code, translated) -- nothing of it in a build log or a problem report made from one. Diagnostics only:
# the objects are the same (tools/build_game_dll.py does the same for the player's build).
# -fno-finite-loops: a guest `b .` (a deliberate hang) stays a hang -- C++ lets the compiler assume every loop ends
# and remove the way into it (tools/build_game_dll.py PPU_LOOPS).
set(_lifted_opts "${_clang_flag_prefix}-ffp-contract=off" "${_clang_flag_prefix}-fno-caret-diagnostics"
                 "${_clang_flag_prefix}-fno-finite-loops")
if(MSVC)
    # /GS-: no stack cookies in the lifted code (as tools/build_game_dll.py builds it): it keeps the PPU's
    # registers in its context, not in local arrays, so a cookie guards nothing there.
    list(APPEND _lifted_opts /GS-)
endif()
if(NOT _lifted_arch STREQUAL "none")
    list(APPEND _lifted_opts "${_clang_flag_prefix}-march=${_lifted_arch}")
endif()
message(STATUS "Lifted PPU code: -march=${_lifted_arch}")
# Extra compile options for the lifted code: T5DR_LIFTED_COPTS for the lifted PPU
# C++, T5DR_SPU_COPTS for the lifted SPU C. Both are lists, e.g.
#   -DT5DR_LIFTED_COPTS="/clang:-O3"
set(T5DR_LIFTED_COPTS "" CACHE STRING "extra compile options for the lifted PPU sources")
set(T5DR_SPU_COPTS "" CACHE STRING "extra compile options for the lifted SPU sources")
if(RECOMP_SOURCES)
    set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS ${_lifted_opts} ${T5DR_LIFTED_COPTS})
endif()
# The lifted SPU C gets the same target CPU (and -ffp-contract=off, which keeps
# the exact SPU float emulation's separate roundings): the sound core, ~0.85 of
# a core in a fight, took ~7% less CPU with x86-64-v3 than with SSE4.1 alone
# (paired runs on two 8-CPU halves of the development PC, docs/RENDER_PERF.md
# "Weaker PCs").
if(SPU_SOURCES)
    set_property(SOURCE ${SPU_SOURCES} APPEND PROPERTY COMPILE_OPTIONS ${_lifted_opts} ${T5DR_SPU_COPTS})
endif()
# Profile-guided optimisation of the lifted code (clang front-end profiles, docs/BUILD_PERF.md):
# one .profdata per part -- T5DR_PGO for the lifted PPU code,
# T5DR_PGO_SND for the SPU sound core, T5DR_PGO_SKIN for the skinning jobs, T5DR_PGO_SPU for the other
# SPU sources. tools/build_game.py makes them from the shipped tools/gamedll/t5dr_lifted.proftext
# (build_game_dll.prepare_profiles). T5DR_PGO=gen builds an instrumented t5dr.exe (T5_PERF_LOG=...
# T5_PGO_WRITE_AT=<frames> writes default.profraw at that flip; merge with llvm-profdata); the
# supported way to train is the game DLL (tools/pgo_train.py).
set(T5DR_PGO "" CACHE STRING "gen, or a .profdata for the lifted PPU code")
set(T5DR_PGO_SND "" CACHE STRING ".profdata for the lifted SPU sound core")
set(T5DR_PGO_SKIN "" CACHE STRING ".profdata for the lifted SPU skinning jobs")
set(T5DR_PGO_SPU "" CACHE STRING ".profdata for the other lifted SPU sources")
# Every SPU image's source is called spu_recomp.c: each gets its own name for the profile's static
# helpers (<image>_spu_recomp.c:<helper>), as tools/build_game_dll.py compiles them.
foreach(_spu_src ${SPU_LIFTED})
    get_filename_component(_spu_img "${_spu_src}" DIRECTORY)
    get_filename_component(_spu_img "${_spu_img}" NAME)
    # (COMPILE_FLAGS, a plain string: a source's COMPILE_OPTIONS list would take no SHELL: groups)
    set_property(SOURCE "${_spu_src}" APPEND_STRING PROPERTY COMPILE_FLAGS
        " -Xclang -main-file-name -Xclang ${_spu_img}_spu_recomp.c")
endforeach()
if(T5DR_PGO STREQUAL "gen")
    set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS /clang:-fprofile-instr-generate)
    get_filename_component(_llvm_bin "${CMAKE_CXX_COMPILER}" DIRECTORY)
    file(GLOB _prof_rt "${_llvm_bin}/../lib/clang/*/lib/windows/clang_rt.profile-x86_64.lib")
    list(GET _prof_rt 0 _prof_rt)
    set(T5DR_PGO_RT "${_prof_rt}")
elseif(T5DR_PGO)
    set_property(SOURCE ${RECOMP_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
        "/clang:-fprofile-instr-use=${T5DR_PGO}" -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date
        -Wno-profile-instr-missing)
endif()
if(SPU_SOURCES AND NOT T5DR_PGO STREQUAL "gen")
    foreach(_spu_src ${SPU_SOURCES})
        get_filename_component(_spu_img "${_spu_src}" DIRECTORY)
        get_filename_component(_spu_img "${_spu_img}" NAME)
        set(_spu_prof "${T5DR_PGO_SPU}")
        if(_spu_src MATCHES "/lifted/bnuscore/")
            set(_spu_prof "${T5DR_PGO_SND}")
        elseif(_spu_src MATCHES "/lifted/skin[^/]*/")
            set(_spu_prof "${T5DR_PGO_SKIN}")
        endif()
        if(_spu_prof)
            set_property(SOURCE "${_spu_src}" APPEND PROPERTY COMPILE_OPTIONS "/clang:-fprofile-instr-use=${_spu_prof}"
                -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date -Wno-profile-instr-missing)
        endif()
    endforeach()
endif()

add_executable(t5dr
    "${PS3RECOMP_DIR}/runtime/ppu/tests/boot_main.cpp"   # generic boot harness
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp"        # vm + ELF loader + run
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"           # NID -> handler dispatch
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"        # boot-critical CRT
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp"            # cellFs VFS
    ${HLE_NID_TABLE}
    ${GAME_SOURCES}
)
if(T5DR_GAME_DLL)
    target_compile_definitions(t5dr PRIVATE PS3_GAME_DLL "PS3_GAME_DLL_NAME=\"t5dr_game.dll\"")
    target_link_options(t5dr PRIVATE "/DEF:${CMAKE_CURRENT_SOURCE_DIR}/tools/gamedll/t5dr_host.def")
endif()

# Our own modules (src/: rollback, netplay, direct fight, training, perf) reach the host through
# src/platform (t5_win.h, t5_plat.h, t5_sock.h): Win32 on Windows, the runtime's POSIX shim and
# t5_plat_posix.c elsewhere (docs/MACOS.md). On macOS they are built only with
# T5DR_MACOS_ONLINE (tools/build_game.py --macos-online): online play between a Mac and a PC is
# not proven in sync yet (docs/MACOS_ONLINE_TEST.md), so the default Mac build stays the game
# alone, offline, as before.
# 1.1.9 (mac-119): on by default on macOS -- the modules also carry the offline features (practice tools,
# training, stage unlock, direct fight). Online play itself stays off: nothing starts netplay without the
# launcher / T5_NET_MODE, and the lobby client wants a --macos-online build (its stamp). tools/build_game.py
# passes the value explicitly (--macos-offline: OFF).
if(APPLE)
    set(_t5dr_mac_modules_default ON)
else()
    set(_t5dr_mac_modules_default OFF)
endif()
option(T5DR_MACOS_ONLINE "macOS: build the src/ modules (netplay, rollback, direct fight, training, practice)" ${_t5dr_mac_modules_default})
if(T5DR_MACOS_ONLINE AND NOT APPLE)
    message(FATAL_ERROR "T5DR_MACOS_ONLINE is for macOS builds")
endif()
if(WIN32 OR T5DR_MACOS_ONLINE)
# Rollback (our own code, src/rollback/): off unless T5_RB_MODE is set. The
# netplay layer calls its loop (T5_RB_MODE=net), so it is built in both modes;
# rb_hooks.cpp reads the lifted table through ppu_game_table in DLL mode.
file(GLOB ROLLBACK_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/rollback/*.cpp")
target_sources(t5dr PRIVATE ${ROLLBACK_SOURCES})
set_source_files_properties(${ROLLBACK_SOURCES} PROPERTIES COMPILE_DEFINITIONS _CRT_SECURE_NO_WARNINGS
    INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/syscalls")

# Netplay prototype (our own code, src/netplay/): off unless T5_NET_MODE is set.
file(GLOB NETPLAY_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/netplay/*.cpp")
target_sources(t5dr PRIVATE ${NETPLAY_SOURCES})
set_source_files_properties(${NETPLAY_SOURCES} PROPERTIES COMPILE_DEFINITIONS _CRT_SECURE_NO_WARNINGS)
if(NOT T5DR_GAME_DLL)   # the netplay log names the lifted code's target (the game DLL exports its own)
    set_property(SOURCE ${NETPLAY_SOURCES} APPEND PROPERTY COMPILE_DEFINITIONS "T5DR_LIFTED_ARCH_NAME=\"${_lifted_arch}\"")
endif()

# Direct fight (our own code, src/directfight/): boot straight into a VS fight
# with the characters/stage from T5_FIGHT, hold between matches, report the
# result. Off unless T5_FIGHT or a T5_DF_* variable is set (docs/DIRECTFIGHT.md).
file(GLOB DIRECTFIGHT_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/directfight/*.cpp")
target_sources(t5dr PRIVATE ${DIRECTFIGHT_SOURCES})
set_source_files_properties(${DIRECTFIGHT_SOURCES} PROPERTIES COMPILE_DEFINITIONS _CRT_SECURE_NO_WARNINGS
    INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/syscalls")

# Training overlay (our own code, src/training/, docs/TRAINING.md): input display and
# frame data drawn by the runtime's overlay layer (ps3recomp patch 0045). Off unless
# T5_TRAINING is set; reads guest memory only, never writes it. The practice tools
# (practice.cpp) change the game -- in offline Practice only, with T5_PRACTICE=1.
file(GLOB TRAINING_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/training/*.cpp")
target_sources(t5dr PRIVATE ${TRAINING_SOURCES})
set_source_files_properties(${TRAINING_SOURCES} PROPERTIES COMPILE_DEFINITIONS _CRT_SECURE_NO_WARNINGS
    INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/libs/video")

# Frame timing for performance work (src/perf/): off unless T5_PERF_LOG is set.
file(GLOB PERF_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/perf/*.cpp")
target_sources(t5dr PRIVATE ${PERF_SOURCES})
set_source_files_properties(${PERF_SOURCES} PROPERTIES COMPILE_DEFINITIONS _CRT_SECURE_NO_WARNINGS
    INCLUDE_DIRECTORIES "${PS3RECOMP_DIR}/runtime/syscalls")
if(T5DR_PGO STREQUAL "gen")
    set_property(SOURCE ${PERF_SOURCES} APPEND PROPERTY COMPILE_DEFINITIONS T5_PGO_GEN)
    target_link_libraries(t5dr PRIVATE "${T5DR_PGO_RT}")
    # boot_main.cpp defines __imp_getenv (its env cache); the profile runtime
    # brings the UCRT import of it too. Instrumented builds only.
    target_link_options(t5dr PRIVATE /FORCE:MULTIPLE)
    target_sources(t5dr PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/perf/pgo/pgo_crt_shim.c")
endif()
if(APPLE)
    # The POSIX half of src/platform/t5_plat.h, and the runtime's Win32 shim for t5_win.h.
    target_sources(t5dr PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/t5_plat_posix.c")
    target_include_directories(t5dr PRIVATE "${PS3RECOMP_DIR}/runtime/platform")
    # Entry detours without code patching (rb_detour.cpp): the lifted code must have been
    # lifted with the hook slots (ppu_lifter.py --hook-slots src/rollback/hook_slots.txt).
    file(STRINGS "${RECOMP_DIR}/ppu_recomp.h" _hook_slots REGEX "^#define PPU_HOOK_SLOTS ")
    if(NOT _hook_slots)
        message(FATAL_ERROR "T5DR_MACOS_ONLINE: ${RECOMP_DIR} was lifted without hook slots -- "
                            "run tools/build_game.py --macos-online (it lifts again)")
    endif()
    set_property(SOURCE ${ROLLBACK_SOURCES} APPEND PROPERTY COMPILE_DEFINITIONS T5DR_HOOK_SLOTS)
    message(STATUS "macOS online modules: on (${_hook_slots})")
endif()
endif()   # WIN32 OR T5DR_MACOS_ONLINE: our own modules

# macOS: no spontaneous fused multiply-add anywhere in t5dr (Apple clang contracts a*b+c by
# default; the runtime library and the lifted code already say so, this covers the boot harness,
# the loader, the HLE table and src/). Clang on x86-64 Windows has no FMA to contract into
# outside the lifted code, which gets -ffp-contract=off above.
if(APPLE)
    target_compile_options(t5dr PRIVATE -ffp-contract=off)
endif()

# The generated NID table includes every module's header.
file(GLOB LIB_INC_DIRS LIST_DIRECTORIES true "${PS3RECOMP_DIR}/libs/*")
target_include_directories(t5dr PRIVATE
    "${RECOMP_DIR}"
    "${PS3RECOMP_DIR}/runtime/ppu"
    "${PS3RECOMP_DIR}/runtime/spu"
    "${PS3RECOMP_DIR}/runtime/prx"
    "${PS3RECOMP_DIR}/include"
    ${LIB_INC_DIRS}
)

target_link_libraries(t5dr PRIVATE ps3recomp_runtime)
if(WIN32)
    # Any Windows 10/11 PC (src/platform): the manifest gives t5dr.exe the UTF-8
    # code page (folders and user names with any characters), long paths and
    # per-monitor DPI awareness; gpu_preference.c exports the hybrid-laptop
    # hints for the discrete GPU; cpu_check.cpp stops with a message on a CPU
    # without SSE4.1. Both in the developer and the release build.
    # Version information (Explorer's Details tab; scanners and SmartScreen read it; SignPath's artifact
    # configuration checks the product name). package_release.py passes -DT5DR_VERSION=<release>.
    set(T5DR_VERSION "0.0.0-dev" CACHE STRING "Version in t5dr.exe's version information")
    string(REGEX MATCH "^([0-9]+)\\.([0-9]+)\\.([0-9]+)" _t5dr_ver "${T5DR_VERSION}")
    if(_t5dr_ver)
        set(T5DR_VER_MAJOR ${CMAKE_MATCH_1})
        set(T5DR_VER_MINOR ${CMAKE_MATCH_2})
        set(T5DR_VER_PATCH ${CMAKE_MATCH_3})
    else()
        set(T5DR_VER_MAJOR 0)
        set(T5DR_VER_MINOR 0)
        set(T5DR_VER_PATCH 0)
    endif()
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/src/platform/t5dr.rc.in" "${CMAKE_CURRENT_BINARY_DIR}/t5dr_version.rc" @ONLY)
    target_sources(t5dr PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/t5dr_version.rc")
    target_sources(t5dr PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/t5dr.manifest"
                                "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/gpu_preference.c"
                                "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/cpu_check.cpp")
    # Windows "N" editions have no Media Foundation (mfplat.dll) until the Media
    # Feature Pack is installed: loaded on first use, so the exe still starts
    # there and only the movies are skipped (ps3recomp patch 0031, mf_h264.cpp).
    target_link_options(t5dr PRIVATE /DELAYLOAD:mfplat.dll)
    target_link_libraries(t5dr PRIVATE delayimp)
    target_link_libraries(t5dr PRIVATE ws2_32 bcrypt xinput ole32 winmm d3d12 dxgi dxguid d3dcompiler)
    # Every guest call is a host call, so recompiled call chains nest deeply.
    target_link_options(t5dr PRIVATE /STACK:268435456 /MAP:t5dr.map)
endif()

# clang-cl with the MSVC STL: <atomic> gives every one of its functions
# target("cx16") (for _InterlockedCompareExchange128), and clang never inlines a
# function with target features its caller lacks -- so without cx16 every
# std::atomic load, store or compare-exchange in the runtime and in src/ is an
# out-of-line call, also inside hot loops (the HLE dispatcher made one per
# registered handler on every call; docs/RENDER_PERF.md "The game thread's own
# time"). Every x64 CPU that runs Windows 10/11 has CMPXCHG16B (Windows 8.1
# already required it), and no code is generated differently except that these
# calls become the instructions they wrap. The lifted code keeps its options
# (T5DR_LIFTED_ARCH; x86-64-v3 includes cx16).
if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_SIZEOF_VOID_P EQUAL 8 AND MSVC)   # (clang-cl: not a Mac's LLVM clang)
    target_compile_options(ps3recomp_runtime PRIVATE /clang:-mcx16)
    get_target_property(_t5dr_srcs t5dr SOURCES)
    if(GAME_SOURCES)
        list(REMOVE_ITEM _t5dr_srcs ${GAME_SOURCES})
    endif()
    list(FILTER _t5dr_srcs INCLUDE REGEX "[.](c|cpp)$")
    set_property(SOURCE ${_t5dr_srcs} APPEND PROPERTY COMPILE_OPTIONS /clang:-mcx16)
endif()
