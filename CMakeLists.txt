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
if(NOT EXISTS "${RECOMP_DIR}/ppu_recomp.h")
    message(FATAL_ERROR "No lifted code in ${RECOMP_DIR} -- run tools/build_game.py first")
endif()

file(GLOB RECOMP_SOURCES CONFIGURE_DEPENDS "${RECOMP_DIR}/*.cpp")
list(LENGTH RECOMP_SOURCES RECOMP_SOURCE_COUNT)
message(STATUS "ps3recomp:      ${PS3RECOMP_DIR}")
message(STATUS "Lifted sources: ${RECOMP_SOURCE_COUNT} file(s) in ${RECOMP_DIR}")

# The runtime library, built from source so its link requirements come along.
add_subdirectory("${PS3RECOMP_DIR}" "${CMAKE_BINARY_DIR}/ps3recomp" EXCLUDE_FROM_ALL)

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
else()
    message(WARNING "No lifted SPU images in ${SPU_DIR} -- the sound core will not run")
endif()

add_executable(t5dr
    "${PS3RECOMP_DIR}/runtime/ppu/tests/boot_main.cpp"   # generic boot harness
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp"        # vm + ELF loader + run
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"           # NID -> handler dispatch
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"        # boot-critical CRT
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp"            # cellFs VFS
    ${HLE_NID_TABLE}
    ${RECOMP_SOURCES}
    ${SPU_SOURCES}
)

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
    target_link_libraries(t5dr PRIVATE ws2_32 bcrypt xinput ole32 winmm d3d12 dxgi dxguid d3dcompiler)
    # Every guest call is a host call, so recompiled call chains nest deeply.
    target_link_options(t5dr PRIVATE /STACK:268435456 /MAP:t5dr.map)
endif()
