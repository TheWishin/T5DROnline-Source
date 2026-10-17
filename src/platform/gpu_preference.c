/* Laptops with two GPUs: these exports in the .exe ask NVIDIA Optimus and AMD
 * Switchable Graphics (PowerXpress) to run the game on the discrete GPU. The
 * renderer also asks DXGI for the high-performance adapter
 * (IDXGIFactory6::EnumAdapterByGpuPreference, patch 0031); the per-app choice
 * in Windows' Settings > System > Display > Graphics still wins over both. */
#include <windows.h>

__declspec(dllexport) DWORD NvOptimusEnablement = 0x00000001;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
