/* Synthetic COM objects exercise the exact shipped live-capture release helper.
 * No GPU, game, encoder, audio endpoint or host input is opened. */
#define COBJMACROS
#include <windows.h>
#include <d3d12.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
static unsigned shutdowns, released_buffers, released_fences;
static UINT64 completed;
void rsx_clips_shutdown(void);
#include "clips_live_release.h"

void rsx_clips_shutdown(void) {
    ++shutdowns;
    for (unsigned i = 0; i < LD_CLIP_READBACKS; ++i)
        g_ld_clip_readbacks[i].held = 0;
}
static ULONG STDMETHODCALLTYPE release_buffer(ID3D12Resource* self) {
    (void)self;
    assert(shutdowns > 0); /* Join/unmap precedes every resource release. */
    ++released_buffers;
    return 0;
}
static ULONG STDMETHODCALLTYPE release_fence(ID3D12Fence* self) {
    (void)self;
    assert(shutdowns > 0);
    ++released_fences;
    return 0;
}
static UINT64 STDMETHODCALLTYPE get_completed(ID3D12Fence* self) {
    (void)self;
    return completed;
}
int main(void) {
    ID3D12ResourceVtbl resource_methods = {0};
    resource_methods.Release = release_buffer;
    ID3D12Resource pending = {&resource_methods}, ready = {&resource_methods};
    ID3D12FenceVtbl fence_methods = {0};
    fence_methods.Release = release_fence;
    fence_methods.GetCompletedValue = get_completed;
    ID3D12Fence fence = {&fence_methods};

    g_ld_clip_fence = &fence;
    g_ld_clip_readbacks[0].resource = &pending;
    g_ld_clip_readbacks[0].pending = 42;
    g_ld_clip_readbacks[1].resource = &ready;
    g_ld_clip_readbacks[1].held = 1;
    completed = 41;
    ld_clips_release();
    assert(shutdowns == 1 && released_buffers == 1 && released_fences == 0);
    assert(g_ld_clip_readbacks[0].resource == &pending && g_ld_clip_fence == &fence);
    assert(g_ld_clip_readbacks[1].resource == NULL);

    completed = 42;
    ld_clips_release();
    assert(shutdowns == 2 && released_buffers == 2 && released_fences == 1);
    assert(g_ld_clip_readbacks[0].resource == NULL && g_ld_clip_fence == NULL);

    /* D3D12's sentinel proves device removal, so pending refs may be released. */
    g_ld_clip_fence = &fence;
    g_ld_clip_readbacks[0].resource = &pending;
    g_ld_clip_readbacks[0].pending = 100;
    completed = UINT64_MAX;
    ld_clips_release();
    assert(released_buffers == 3 && released_fences == 2 && g_ld_clip_fence == NULL);
    puts("PASS: incomplete GPU copies retain buffers and fence");
    return 0;
}
