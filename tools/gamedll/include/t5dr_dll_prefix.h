/* Forced include (/FI) for every source of the game DLL (tools/build_game_dll.py).
 *
 * 1. PPU_FENCE without <atomic>: the lifted header would include the C++ STL
 *    for one fence; the compiler builtin is the same instruction.
 * 2. Data the generated code reads from the runtime lives in t5dr.exe. A DLL
 *    reaches another module's variable through its import slot: the import
 *    library defines __imp_<name>, a pointer to the variable. The macros turn
 *    the header's `extern uint8_t* vm_base;` into `extern uint8_t* (*__imp_vm_base);`
 *    and every use of vm_base into (*__imp_vm_base), so neither ps3recomp's
 *    headers nor the generated code need a dllimport annotation. */
#pragma once

#define PPU_FENCE(o) __atomic_thread_fence(T5_MO_##o)
#define T5_MO_relaxed __ATOMIC_RELAXED
#define T5_MO_consume __ATOMIC_CONSUME
#define T5_MO_acquire __ATOMIC_ACQUIRE
#define T5_MO_release __ATOMIC_RELEASE
#define T5_MO_acq_rel __ATOMIC_ACQ_REL
#define T5_MO_seq_cst __ATOMIC_SEQ_CST

#define vm_base             (*__imp_vm_base)
#define vm_inline_ok        (*__imp_vm_inline_ok)
#define ppu_vm_size         (*__imp_ppu_vm_size)
#define ppu_hle_inject_base (*__imp_ppu_hle_inject_base)
#define g_spu_ls_dbg        (*__imp_g_spu_ls_dbg)
#define g_spu_ls_watch_n    (*__imp_g_spu_ls_watch_n)
#define vm_store_inline_ok  (*__imp_vm_store_inline_ok)
#define vm_coh_bitmap       (*__imp_vm_coh_bitmap)
