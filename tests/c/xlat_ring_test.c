/*
 * xlat_ring_test.c -- ps3recomp patch 0067's work ring (libs/video/rsx_record_ring.h, RSX_XLAT_OVERLAP=2):
 * the walker records command-list calls through the recorder object, the renderer thread makes them on the
 * real list. Built against the patched runtime source by tests/test_xlat_overlap.py.
 *
 * One thread records random calls of every method the recorder knows -- arrays of every size the translation
 * passes (barriers, viewports, rects, vertex buffer views, render targets as a list or a range, clears with and
 * without rects, root constants), NULL pointers where the API allows them -- and the frame's present, both into a
 * reference list that logs each call with its arguments by value and through the recorder; a second thread runs
 * the renderer thread's loop (ld_rq_consume) into a list that logs the same way. Every call must arrive exactly
 * once, in order, with the same arguments (the logs byte-identical); the ring is small (16 KB) so it wraps
 * thousands of times and fills (the walker waits for room); ld_xo_sync and ld_xo_sync_present must return only
 * once the calls / the presents before them were made.
 */
#define LD_RQ_BYTES (16u << 10)
#include "rsx_record_ring.h"
#pragma comment(lib, "synchronization.lib")

typedef struct { uint8_t* p; size_t n, cap; } logbuf;
static void lput(logbuf* L, const void* d, size_t n)
{
    if (L->n + n > L->cap) {
        L->cap = (L->cap + n) * 2;
        L->p = (uint8_t*)realloc(L->p, L->cap);
        if (!L->p) { printf("FAIL out of memory\n"); exit(2); }
    }
    memcpy(L->p + L->n, d, n);
    L->n += n;
}
typedef struct { CONST_VTBL ID3D12GraphicsCommandListVtbl* lpVtbl; logbuf* log; } fake_list;
#define FL(l) (((fake_list*)(void*)(l))->log)
static void lid(ID3D12GraphicsCommandList* l, uint32_t id) { lput(FL(l), &id, 4); }
static void lval(ID3D12GraphicsCommandList* l, const void* p, size_t n) { lput(FL(l), p, n); }
static void lptr(ID3D12GraphicsCommandList* l, const void* p, size_t n)
{
    const uint32_t has = p != NULL;
    lval(l, &has, 4);
    if (p) lval(l, p, n);
}

static void STDMETHODCALLTYPE f_ResourceBarrier(ID3D12GraphicsCommandList* l, UINT n, const D3D12_RESOURCE_BARRIER* b)
{ lid(l, 1); lval(l, &n, 4); lval(l, b, n * sizeof *b); }
static void STDMETHODCALLTYPE f_CopyTextureRegion(ID3D12GraphicsCommandList* l, const D3D12_TEXTURE_COPY_LOCATION* d,
                                                  UINT x, UINT y, UINT z, const D3D12_TEXTURE_COPY_LOCATION* s,
                                                  const D3D12_BOX* box)
{ lid(l, 2); lval(l, d, sizeof *d); lval(l, &x, 4); lval(l, &y, 4); lval(l, &z, 4); lval(l, s, sizeof *s); lptr(l, box, sizeof *box); }
static void STDMETHODCALLTYPE f_CopyResource(ID3D12GraphicsCommandList* l, ID3D12Resource* d, ID3D12Resource* s)
{ lid(l, 3); lval(l, &d, sizeof d); lval(l, &s, sizeof s); }
static void STDMETHODCALLTYPE f_CopyBufferRegion(ID3D12GraphicsCommandList* l, ID3D12Resource* d, UINT64 doff,
                                                 ID3D12Resource* s, UINT64 soff, UINT64 n)
{ lid(l, 4); lval(l, &d, sizeof d); lval(l, &doff, 8); lval(l, &s, sizeof s); lval(l, &soff, 8); lval(l, &n, 8); }
static void STDMETHODCALLTYPE f_SetGraphicsRootDescriptorTable(ID3D12GraphicsCommandList* l, UINT i, D3D12_GPU_DESCRIPTOR_HANDLE h)
{ lid(l, 5); lval(l, &i, 4); lval(l, &h, sizeof h); }
static void STDMETHODCALLTYPE f_SetComputeRootDescriptorTable(ID3D12GraphicsCommandList* l, UINT i, D3D12_GPU_DESCRIPTOR_HANDLE h)
{ lid(l, 6); lval(l, &i, 4); lval(l, &h, sizeof h); }
static void STDMETHODCALLTYPE f_SetPipelineState(ID3D12GraphicsCommandList* l, ID3D12PipelineState* p)
{ lid(l, 7); lval(l, &p, sizeof p); }
static void STDMETHODCALLTYPE f_SetDescriptorHeaps(ID3D12GraphicsCommandList* l, UINT n, ID3D12DescriptorHeap* const* h)
{ lid(l, 8); lval(l, &n, 4); lval(l, h, n * sizeof *h); }
static void STDMETHODCALLTYPE f_SetGraphicsRootSignature(ID3D12GraphicsCommandList* l, ID3D12RootSignature* p)
{ lid(l, 9); lval(l, &p, sizeof p); }
static void STDMETHODCALLTYPE f_SetComputeRootSignature(ID3D12GraphicsCommandList* l, ID3D12RootSignature* p)
{ lid(l, 10); lval(l, &p, sizeof p); }
static void STDMETHODCALLTYPE f_ResolveQueryData(ID3D12GraphicsCommandList* l, ID3D12QueryHeap* h, D3D12_QUERY_TYPE t,
                                                 UINT i, UINT n, ID3D12Resource* d, UINT64 off)
{ lid(l, 11); lval(l, &h, sizeof h); lval(l, &t, 4); lval(l, &i, 4); lval(l, &n, 4); lval(l, &d, sizeof d); lval(l, &off, 8); }
static void STDMETHODCALLTYPE f_EndQuery(ID3D12GraphicsCommandList* l, ID3D12QueryHeap* h, D3D12_QUERY_TYPE t, UINT i)
{ lid(l, 12); lval(l, &h, sizeof h); lval(l, &t, 4); lval(l, &i, 4); }
static void STDMETHODCALLTYPE f_BeginQuery(ID3D12GraphicsCommandList* l, ID3D12QueryHeap* h, D3D12_QUERY_TYPE t, UINT i)
{ lid(l, 13); lval(l, &h, sizeof h); lval(l, &t, 4); lval(l, &i, 4); }
static void STDMETHODCALLTYPE f_RSSetViewports(ID3D12GraphicsCommandList* l, UINT n, const D3D12_VIEWPORT* v)
{ lid(l, 14); lval(l, &n, 4); lval(l, v, n * sizeof *v); }
static void STDMETHODCALLTYPE f_RSSetScissorRects(ID3D12GraphicsCommandList* l, UINT n, const D3D12_RECT* r)
{ lid(l, 15); lval(l, &n, 4); lval(l, r, n * sizeof *r); }
static void STDMETHODCALLTYPE f_OMSetRenderTargets(ID3D12GraphicsCommandList* l, UINT n, const D3D12_CPU_DESCRIPTOR_HANDLE* rt,
                                                   BOOL range, const D3D12_CPU_DESCRIPTOR_HANDLE* ds)
{
    lid(l, 16); lval(l, &n, 4); lval(l, &range, sizeof range);
    const UINT k = n ? (range ? 1u : n) : 0u;   /* a range is one handle */
    lptr(l, k ? rt : NULL, k * sizeof *rt);
    lptr(l, ds, sizeof *ds);
}
static void STDMETHODCALLTYPE f_OMSetStencilRef(ID3D12GraphicsCommandList* l, UINT v) { lid(l, 17); lval(l, &v, 4); }
static void STDMETHODCALLTYPE f_OMSetBlendFactor(ID3D12GraphicsCommandList* l, const FLOAT f[4]) { lid(l, 18); lval(l, f, 16); }
static void STDMETHODCALLTYPE f_IASetPrimitiveTopology(ID3D12GraphicsCommandList* l, D3D12_PRIMITIVE_TOPOLOGY t)
{ lid(l, 19); lval(l, &t, 4); }
static void STDMETHODCALLTYPE f_IASetVertexBuffers(ID3D12GraphicsCommandList* l, UINT start, UINT n, const D3D12_VERTEX_BUFFER_VIEW* v)
{ lid(l, 20); lval(l, &start, 4); lval(l, &n, 4); lptr(l, v, n * sizeof *v); }
static void STDMETHODCALLTYPE f_IASetIndexBuffer(ID3D12GraphicsCommandList* l, const D3D12_INDEX_BUFFER_VIEW* v)
{ lid(l, 21); lptr(l, v, sizeof *v); }
static void STDMETHODCALLTYPE f_DrawInstanced(ID3D12GraphicsCommandList* l, UINT a, UINT b, UINT c, UINT d)
{ lid(l, 22); lval(l, &a, 4); lval(l, &b, 4); lval(l, &c, 4); lval(l, &d, 4); }
static void STDMETHODCALLTYPE f_DrawIndexedInstanced(ID3D12GraphicsCommandList* l, UINT a, UINT b, UINT c, INT d, UINT e)
{ lid(l, 23); lval(l, &a, 4); lval(l, &b, 4); lval(l, &c, 4); lval(l, &d, 4); lval(l, &e, 4); }
static void STDMETHODCALLTYPE f_ClearRenderTargetView(ID3D12GraphicsCommandList* l, D3D12_CPU_DESCRIPTOR_HANDLE h,
                                                      const FLOAT c[4], UINT n, const D3D12_RECT* r)
{ lid(l, 24); lval(l, &h, sizeof h); lval(l, c, 16); lval(l, &n, 4); lptr(l, r, n * sizeof *r); }
static void STDMETHODCALLTYPE f_ClearDepthStencilView(ID3D12GraphicsCommandList* l, D3D12_CPU_DESCRIPTOR_HANDLE h,
                                                      D3D12_CLEAR_FLAGS fl, FLOAT d, UINT8 st, UINT n, const D3D12_RECT* r)
{ lid(l, 25); lval(l, &h, sizeof h); lval(l, &fl, 4); lval(l, &d, 4); lval(l, &st, 1); lval(l, &n, 4); lptr(l, r, n * sizeof *r); }
static void STDMETHODCALLTYPE f_SetGraphicsRootConstantBufferView(ID3D12GraphicsCommandList* l, UINT i, D3D12_GPU_VIRTUAL_ADDRESS va)
{ lid(l, 26); lval(l, &i, 4); lval(l, &va, 8); }
static void STDMETHODCALLTYPE f_SetGraphicsRootShaderResourceView(ID3D12GraphicsCommandList* l, UINT i, D3D12_GPU_VIRTUAL_ADDRESS va)
{ lid(l, 27); lval(l, &i, 4); lval(l, &va, 8); }
static void STDMETHODCALLTYPE f_SetGraphicsRoot32BitConstants(ID3D12GraphicsCommandList* l, UINT i, UINT n, const void* src, UINT off)
{ lid(l, 28); lval(l, &i, 4); lval(l, &n, 4); lval(l, src, n * 4u); lval(l, &off, 4); }
static void STDMETHODCALLTYPE f_SetGraphicsRoot32BitConstant(ID3D12GraphicsCommandList* l, UINT i, UINT v, UINT off)
{ lid(l, 29); lval(l, &i, 4); lval(l, &v, 4); lval(l, &off, 4); }
static void STDMETHODCALLTYPE f_Dispatch(ID3D12GraphicsCommandList* l, UINT x, UINT y, UINT z)
{ lid(l, 30); lval(l, &x, 4); lval(l, &y, 4); lval(l, &z, 4); }
static volatile LONG g_unexpected;
static void STDMETHODCALLTYPE f_unexpected(void* self) { (void)self; InterlockedIncrement(&g_unexpected); }

static ID3D12GraphicsCommandListVtbl g_fake_vtbl;
static void fake_init(void)
{
    void** slot = (void**)&g_fake_vtbl;
    for (size_t i = 0; i < sizeof g_fake_vtbl / sizeof(void*); i++) slot[i] = (void*)f_unexpected;
    g_fake_vtbl.ResourceBarrier = f_ResourceBarrier;
    g_fake_vtbl.CopyTextureRegion = f_CopyTextureRegion;
    g_fake_vtbl.CopyResource = f_CopyResource;
    g_fake_vtbl.CopyBufferRegion = f_CopyBufferRegion;
    g_fake_vtbl.SetGraphicsRootDescriptorTable = f_SetGraphicsRootDescriptorTable;
    g_fake_vtbl.SetComputeRootDescriptorTable = f_SetComputeRootDescriptorTable;
    g_fake_vtbl.SetPipelineState = f_SetPipelineState;
    g_fake_vtbl.SetDescriptorHeaps = f_SetDescriptorHeaps;
    g_fake_vtbl.SetGraphicsRootSignature = f_SetGraphicsRootSignature;
    g_fake_vtbl.SetComputeRootSignature = f_SetComputeRootSignature;
    g_fake_vtbl.ResolveQueryData = f_ResolveQueryData;
    g_fake_vtbl.EndQuery = f_EndQuery;
    g_fake_vtbl.BeginQuery = f_BeginQuery;
    g_fake_vtbl.RSSetViewports = f_RSSetViewports;
    g_fake_vtbl.RSSetScissorRects = f_RSSetScissorRects;
    g_fake_vtbl.OMSetRenderTargets = f_OMSetRenderTargets;
    g_fake_vtbl.OMSetStencilRef = f_OMSetStencilRef;
    g_fake_vtbl.OMSetBlendFactor = f_OMSetBlendFactor;
    g_fake_vtbl.IASetPrimitiveTopology = f_IASetPrimitiveTopology;
    g_fake_vtbl.IASetVertexBuffers = f_IASetVertexBuffers;
    g_fake_vtbl.IASetIndexBuffer = f_IASetIndexBuffer;
    g_fake_vtbl.DrawInstanced = f_DrawInstanced;
    g_fake_vtbl.DrawIndexedInstanced = f_DrawIndexedInstanced;
    g_fake_vtbl.ClearRenderTargetView = f_ClearRenderTargetView;
    g_fake_vtbl.ClearDepthStencilView = f_ClearDepthStencilView;
    g_fake_vtbl.SetGraphicsRootConstantBufferView = f_SetGraphicsRootConstantBufferView;
    g_fake_vtbl.SetGraphicsRootShaderResourceView = f_SetGraphicsRootShaderResourceView;
    g_fake_vtbl.SetGraphicsRoot32BitConstants = f_SetGraphicsRoot32BitConstants;
    g_fake_vtbl.SetGraphicsRoot32BitConstant = f_SetGraphicsRoot32BitConstant;
    g_fake_vtbl.Dispatch = f_Dispatch;
}

static logbuf g_ref_log, g_rep_log;
static fake_list g_ref = { &g_fake_vtbl, &g_ref_log }, g_rep = { &g_fake_vtbl, &g_rep_log };
static volatile LONG g_presents_made;
static ID3D12GraphicsCommandList* rep_list(void) { return (ID3D12GraphicsCommandList*)(void*)&g_rep; }
static void on_present(uint32_t id)
{
    lid(rep_list(), 100); lval(rep_list(), &id, 4);
    /* a present that takes its time (DXGI's queue full): the walker fills the ring meanwhile */
    if ((id & 3) == 0) Sleep(2);
    InterlockedIncrement(&g_presents_made);
}
static DWORD WINAPI consumer(LPVOID unused) { (void)unused; ld_rq_consume(rep_list); return 0; }

static uint64_t g_rng = 0x9E3779B97F4A7C15ull;
static uint32_t rnd(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 7; g_rng ^= g_rng << 17; return (uint32_t)g_rng; }
static void fill(void* p, size_t n) { uint8_t* b = (uint8_t*)p; for (size_t i = 0; i < n; i++) b[i] = (uint8_t)rnd(); }

/* one random call into list `l` (the reference, or the recorder); the arguments are drawn before, so both get
 * the same */
typedef struct {
    uint32_t m, n, a, b, c, d, e, f, has_box, has_ds, range, null_ptr;
    UINT64 q0, q1, q2;
    D3D12_RESOURCE_BARRIER bar[24]; D3D12_TEXTURE_COPY_LOCATION tl[2]; D3D12_BOX box; D3D12_VIEWPORT vp[16];
    D3D12_RECT rc[16]; D3D12_CPU_DESCRIPTOR_HANDLE rt[8], ds; D3D12_VERTEX_BUFFER_VIEW vb[16]; D3D12_INDEX_BUFFER_VIEW ib;
    FLOAT f4[4]; UINT k[64]; void* ptr[3]; D3D12_GPU_DESCRIPTOR_HANDLE gh;
} call_t;
static void draw_call(call_t* c)
{
    memset(c, 0, sizeof *c);
    c->m = 1 + rnd() % 30; c->a = rnd(); c->b = rnd(); c->c = rnd(); c->d = rnd(); c->e = rnd(); c->f = rnd();
    c->q0 = (uint64_t)rnd() << 32 | rnd(); c->q1 = (uint64_t)rnd() << 32 | rnd(); c->q2 = (uint64_t)rnd() << 32 | rnd();
    c->has_box = rnd() & 1; c->has_ds = rnd() & 1; c->range = rnd() & 1; c->null_ptr = (rnd() & 3) == 0;
    fill(c->bar, sizeof c->bar); fill(c->tl, sizeof c->tl); fill(&c->box, sizeof c->box); fill(c->vp, sizeof c->vp);
    fill(c->rc, sizeof c->rc); fill(c->rt, sizeof c->rt); fill(&c->ds, sizeof c->ds); fill(c->vb, sizeof c->vb);
    fill(&c->ib, sizeof c->ib); fill(c->f4, sizeof c->f4); fill(c->k, sizeof c->k); fill(c->ptr, sizeof c->ptr);
    fill(&c->gh, sizeof c->gh);
    switch (c->m) {
    case 1: c->n = rnd() % 25; break;                 /* barriers 0..24 */
    case 8: c->n = 1 + rnd() % 2; break;              /* 1 or 2 heaps */
    case 14: case 15: c->n = 1 + rnd() % 16; break;   /* viewports / scissors */
    case 16: c->n = rnd() % 9; break;                 /* 0..8 render targets */
    case 20: c->n = rnd() % 17; break;                /* 0..16 vertex buffers */
    case 24: case 25: c->n = rnd() % 5; break;        /* clear rects */
    case 28: c->n = 1 + rnd() % 64; break;            /* root constants */
    default: break;
    }
}
static void make_call(ID3D12GraphicsCommandList* l, const call_t* c)
{
    ID3D12GraphicsCommandListVtbl* v = l->lpVtbl;
    ID3D12DescriptorHeap* heaps[2] = { (ID3D12DescriptorHeap*)c->ptr[0], (ID3D12DescriptorHeap*)c->ptr[1] };
    switch (c->m) {
    case 1: v->ResourceBarrier(l, c->n, c->bar); break;
    case 2: v->CopyTextureRegion(l, &c->tl[0], c->a, c->b, c->c, &c->tl[1], c->has_box ? &c->box : NULL); break;
    case 3: v->CopyResource(l, (ID3D12Resource*)c->ptr[0], (ID3D12Resource*)c->ptr[1]); break;
    case 4: v->CopyBufferRegion(l, (ID3D12Resource*)c->ptr[0], c->q0, (ID3D12Resource*)c->ptr[1], c->q1, c->q2); break;
    case 5: v->SetGraphicsRootDescriptorTable(l, c->a, c->gh); break;
    case 6: v->SetComputeRootDescriptorTable(l, c->a, c->gh); break;
    case 7: v->SetPipelineState(l, (ID3D12PipelineState*)c->ptr[0]); break;
    case 8: v->SetDescriptorHeaps(l, c->n, heaps); break;
    case 9: v->SetGraphicsRootSignature(l, (ID3D12RootSignature*)c->ptr[0]); break;
    case 10: v->SetComputeRootSignature(l, (ID3D12RootSignature*)c->ptr[0]); break;
    case 11: v->ResolveQueryData(l, (ID3D12QueryHeap*)c->ptr[0], (D3D12_QUERY_TYPE)(c->a & 7), c->b, c->c,
                                 (ID3D12Resource*)c->ptr[1], c->q0); break;
    case 12: v->EndQuery(l, (ID3D12QueryHeap*)c->ptr[0], (D3D12_QUERY_TYPE)(c->a & 7), c->b); break;
    case 13: v->BeginQuery(l, (ID3D12QueryHeap*)c->ptr[0], (D3D12_QUERY_TYPE)(c->a & 7), c->b); break;
    case 14: v->RSSetViewports(l, c->n, c->vp); break;
    case 15: v->RSSetScissorRects(l, c->n, c->rc); break;
    case 16: v->OMSetRenderTargets(l, c->n, c->n ? c->rt : NULL, c->range ? TRUE : FALSE, c->has_ds ? &c->ds : NULL); break;
    case 17: v->OMSetStencilRef(l, c->a); break;
    case 18: v->OMSetBlendFactor(l, c->f4); break;
    case 19: v->IASetPrimitiveTopology(l, (D3D12_PRIMITIVE_TOPOLOGY)(c->a & 63)); break;
    case 20: v->IASetVertexBuffers(l, c->a & 15, c->n, c->null_ptr ? NULL : c->vb); break;
    case 21: v->IASetIndexBuffer(l, c->null_ptr ? NULL : &c->ib); break;
    case 22: v->DrawInstanced(l, c->a, c->b, c->c, c->d); break;
    case 23: v->DrawIndexedInstanced(l, c->a, c->b, c->c, (INT)c->d, c->e); break;
    case 24: v->ClearRenderTargetView(l, c->rt[0], c->f4, c->n, c->n ? c->rc : NULL); break;
    case 25: v->ClearDepthStencilView(l, c->ds, (D3D12_CLEAR_FLAGS)(c->a & 3), c->f4[0], (UINT8)c->b, c->n,
                                      c->n ? c->rc : NULL); break;
    case 26: v->SetGraphicsRootConstantBufferView(l, c->a, c->q0); break;
    case 27: v->SetGraphicsRootShaderResourceView(l, c->a, c->q0); break;
    case 28: v->SetGraphicsRoot32BitConstants(l, c->a, c->n, c->k, c->b); break;
    case 29: v->SetGraphicsRoot32BitConstant(l, c->a, c->b, c->c); break;
    case 30: v->Dispatch(l, c->a, c->b, c->c); break;
    default: break;
    }
}

int main(int argc, char** argv)
{
    const int calls = argc > 1 ? atoi(argv[1]) : 300000;
    fake_init();
    ld_rq_init_vtbl();
    g_rq_on_present = on_present;
    if (!ld_rq_alloc()) { printf("FAIL no ring\n"); return 2; }
    HANDLE th = CreateThread(NULL, 0, consumer, NULL, 0, NULL);
    ID3D12GraphicsCommandList* rec = (ID3D12GraphicsCommandList*)(void*)&g_rq_proxy;
    ID3D12GraphicsCommandList* ref = (ID3D12GraphicsCommandList*)(void*)&g_ref;
    static call_t c;
    unsigned presents = 0, syncs = 0, psyncs = 0, bad = 0;
    for (int i = 0; i < calls; i++) {
        const uint32_t r = rnd() % 1000;
        if (r < 4) {                                           /* the frame's present */
            const uint32_t id = rnd();
            lid(ref, 100); lval(ref, &id, 4);
            ((rq_u32*)ld_rq_put(RQ_PRESENT, sizeof(rq_u32)))->v = id;
            g_xo_present_end = g_rq_wl;
            ld_rq_publish();
            if (__atomic_load_n(&g_rq_sleep, __ATOMIC_SEQ_CST)) ld_rq_wake();
            presents++;
        } else if (r < 6) {                                    /* the next walk: the present done */
            ld_xo_sync_present();
            if ((unsigned)g_presents_made != presents) bad++;
            psyncs++;
        } else if (r < 7) {                                    /* a flush: every call made */
            ld_xo_sync();
            if (g_rep_log.n != g_ref_log.n) bad++;
            syncs++;
        } else {
            draw_call(&c);
            make_call(ref, &c);
            make_call(rec, &c);
        }
        if ((rnd() & 0x3FFF) == 0) Sleep(1 + rnd() % 3);       /* gaps: the renderer thread goes to sleep */
    }
    ld_xo_sync();
    g_rq_stop = 1;
    ld_rq_wake();
    WaitForSingleObject(th, 10000);
    const int same = g_rep_log.n == g_ref_log.n && memcmp(g_rep_log.p, g_ref_log.p, g_ref_log.n) == 0;
    printf("%d calls, %u presents, %u full syncs, %u present syncs; %llu packets, ring full %llu times; "
           "log %zu / %zu bytes, %s, %u sync failures, %ld unexpected calls\n",
           calls, presents, syncs, psyncs, (unsigned long long)g_rq_packets, (unsigned long long)g_rq_full_waits,
           g_ref_log.n, g_rep_log.n, same ? "identical" : "DIFFERENT", bad, (long)g_unexpected);
    if (!same || bad || g_unexpected || !g_rq_full_waits) { printf("FAIL\n"); return 1; }
    printf("PASS\n");
    return 0;
}
