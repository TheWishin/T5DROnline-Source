/* screen_watch: what reaches the screen from one game window (DXGI desktop duplication).
 *
 *   screen_watch.exe <pid> <out.txt> <seconds>
 *
 * Every desktop update that came from a present (not only a mouse move) is copied (the window's client
 * area only) and reduced to one line: "<qpc of the present> <mean luma 0..255> <share of near-black
 * pixels in per mille> <accumulated frames>". Nothing of the picture is stored. A frame whose mean is far
 * below both neighbours is a flash that the player saw (tools/screen_watch.py summarises the file).
 * The window must be visible (not minimised) and on one output; the window is looked up again every
 * second, so moving it is fine. Build: clang-cl /O2 screen_watch.c d3d11.lib dxgi.lib user32.lib
 */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <stdio.h>
#include <stdlib.h>

static DWORD g_pid;
static HWND g_found;
static BOOL CALLBACK enum_cb(HWND h, LPARAM lp)
{
    (void)lp;
    DWORD pid = 0;
    GetWindowThreadProcessId(h, &pid);
    if (pid == g_pid && IsWindowVisible(h) && !GetWindow(h, GW_OWNER)) {
        RECT r;
        GetClientRect(h, &r);
        if (r.right - r.left >= 320 && r.bottom - r.top >= 180) { g_found = h; return FALSE; }
    }
    return TRUE;
}

int main(int argc, char** argv)
{
    if (argc < 4) { fprintf(stderr, "usage: screen_watch <pid> <out> <seconds>\n"); return 2; }
    g_pid = (DWORD)strtoul(argv[1], NULL, 0);
    FILE* out = fopen(argv[2], "w");
    if (!out) return 2;
    const double secs = atof(argv[3]);
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    LARGE_INTEGER f, t0, now;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t0);
    fprintf(out, "# qpc_frequency=%lld\n", f.QuadPart);

    IDXGIFactory1* fac = NULL;
    if (FAILED(CreateDXGIFactory1(&IID_IDXGIFactory1, (void**)&fac))) return 3;
    ID3D11Device* dev = NULL; ID3D11DeviceContext* ctx = NULL;
    IDXGIOutputDuplication* dup = NULL;
    ID3D11Texture2D* staging = NULL;
    int sw = 0, sh = 0;
    RECT orect = {0};
    HWND hwnd = NULL;
    LONGLONG next_find = 0;
    unsigned long long frames = 0, lost = 0;

    for (;;) {
        QueryPerformanceCounter(&now);
        if ((double)(now.QuadPart - t0.QuadPart) / f.QuadPart > secs) break;
        if (!dup || now.QuadPart >= next_find) {
            next_find = now.QuadPart + f.QuadPart;
            g_found = NULL;
            EnumWindows(enum_cb, 0);
            hwnd = g_found;
            if (!hwnd) { if (!dup) { Sleep(200); continue; } }
            if (!dup) {
                HMONITOR mon = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
                IDXGIAdapter1* ad = NULL;
                for (UINT a = 0; !dup && SUCCEEDED(IDXGIFactory1_EnumAdapters1(fac, a, &ad)); a++) {
                    IDXGIOutput* o = NULL;
                    for (UINT k = 0; !dup && SUCCEEDED(IDXGIAdapter1_EnumOutputs(ad, k, &o)); k++) {
                        DXGI_OUTPUT_DESC od;
                        IDXGIOutput_GetDesc(o, &od);
                        if (od.Monitor == mon) {
                            orect = od.DesktopCoordinates;
                            if (SUCCEEDED(D3D11CreateDevice((IDXGIAdapter*)ad, D3D_DRIVER_TYPE_UNKNOWN, NULL, 0,
                                                            NULL, 0, D3D11_SDK_VERSION, &dev, NULL, &ctx))) {
                                IDXGIOutput1* o1 = NULL;
                                if (SUCCEEDED(IDXGIOutput_QueryInterface(o, &IID_IDXGIOutput1, (void**)&o1))) {
                                    if (FAILED(IDXGIOutput1_DuplicateOutput(o1, (IUnknown*)dev, &dup))) dup = NULL;
                                    IDXGIOutput1_Release(o1);
                                }
                            }
                        }
                        IDXGIOutput_Release(o);
                    }
                    IDXGIAdapter1_Release(ad);
                }
                if (!dup) { fprintf(out, "# no duplication\n"); fflush(out); Sleep(1000); continue; }
                fprintf(out, "# output %ld,%ld..%ld,%ld\n", orect.left, orect.top, orect.right, orect.bottom);
            }
        }
        DXGI_OUTDUPL_FRAME_INFO fi;
        IDXGIResource* res = NULL;
        HRESULT hr = IDXGIOutputDuplication_AcquireNextFrame(dup, 100, &fi, &res);
        if (hr == DXGI_ERROR_WAIT_TIMEOUT) continue;
        if (FAILED(hr)) {   /* access lost (mode change, secure desktop): start again */
            fprintf(out, "# lost hr=0x%08lX\n", (unsigned long)hr);
            lost++;
            IDXGIOutputDuplication_Release(dup); dup = NULL;
            if (staging) { ID3D11Texture2D_Release(staging); staging = NULL; }
            ID3D11DeviceContext_Release(ctx); ID3D11Device_Release(dev); ctx = NULL; dev = NULL;
            continue;
        }
        static unsigned long long acq = 0, nopres = 0;
        acq++;
        if (fi.LastPresentTime.QuadPart == 0) nopres++;
        if ((acq & 1023) == 0) { fprintf(out, "# acquired %llu without present %llu\n", acq, nopres); fflush(out); }
        if (fi.LastPresentTime.QuadPart != 0 && hwnd) {
            RECT cr; POINT p0 = {0, 0};
            GetClientRect(hwnd, &cr);
            ClientToScreen(hwnd, &p0);
            int x = p0.x - orect.left, y = p0.y - orect.top, w = cr.right, h = cr.bottom;
            const int ow = orect.right - orect.left, oh = orect.bottom - orect.top;
            if (x < 0) { w += x; x = 0; }
            if (y < 0) { h += y; y = 0; }
            if (x + w > ow) w = ow - x;
            if (y + h > oh) h = oh - y;
            ID3D11Texture2D* tex = NULL;
            if (w > 16 && h > 16 && SUCCEEDED(IDXGIResource_QueryInterface(res, &IID_ID3D11Texture2D, (void**)&tex))) {
                if (!staging || sw != w || sh != h) {
                    if (staging) ID3D11Texture2D_Release(staging);
                    D3D11_TEXTURE2D_DESC td;
                    ID3D11Texture2D_GetDesc(tex, &td);
                    td.Width = (UINT)w; td.Height = (UINT)h; td.MipLevels = 1; td.ArraySize = 1;
                    td.Usage = D3D11_USAGE_STAGING; td.BindFlags = 0;
                    td.CPUAccessFlags = D3D11_CPU_ACCESS_READ; td.MiscFlags = 0;
                    staging = NULL;
                    ID3D11Device_CreateTexture2D(dev, &td, NULL, &staging);
                    sw = w; sh = h;
                }
                if (staging) {
                    D3D11_BOX box = {(UINT)x, (UINT)y, 0, (UINT)(x + w), (UINT)(y + h), 1};
                    ID3D11DeviceContext_CopySubresourceRegion(ctx, (ID3D11Resource*)staging, 0, 0, 0, 0,
                                                              (ID3D11Resource*)tex, 0, &box);
                    D3D11_MAPPED_SUBRESOURCE m;
                    if (SUCCEEDED(ID3D11DeviceContext_Map(ctx, (ID3D11Resource*)staging, 0, D3D11_MAP_READ, 0, &m))) {
                        unsigned long long sum = 0, n = 0, dark = 0;
                        for (int yy = 0; yy < h; yy += 6) {
                            const unsigned char* row = (const unsigned char*)m.pData + (size_t)yy * m.RowPitch;
                            for (int xx = 0; xx < w; xx += 6) {
                                const unsigned char* px = row + xx * 4;   /* BGRA8 */
                                const unsigned l = (px[2] * 77u + px[1] * 150u + px[0] * 29u) >> 8;
                                sum += l; n++; dark += l < 12;
                            }
                        }
                        ID3D11DeviceContext_Unmap(ctx, (ID3D11Resource*)staging, 0);
                        fprintf(out, "%lld %.2f %llu %u\n", fi.LastPresentTime.QuadPart,
                                n ? (double)sum / n : 0.0, n ? dark * 1000 / n : 0, fi.AccumulatedFrames);
                        frames++;
                        if ((frames & 255) == 0) fflush(out);
                    }
                }
                ID3D11Texture2D_Release(tex);
            }
        }
        IDXGIResource_Release(res);
        IDXGIOutputDuplication_ReleaseFrame(dup);
    }
    fprintf(out, "# frames %llu lost %llu\n", frames, lost);
    fclose(out);
    return 0;
}
