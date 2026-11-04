/* Host UI only: call once at a LIVE host boundary, never during rollback.
 * No guest memory, fight commands, network calls or simulation input writes. */
#pragma once
namespace df {
void ui_init();
void ui_tick();
void ui_invalidate();
/* Only an OFFLINE caller may use this to keep challenger menu presses out of
 * Practice; live netplay and replay input must never depend on host UI. */
bool ui_blocks_offline_pad();
}
