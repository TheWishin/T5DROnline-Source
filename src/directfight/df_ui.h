/* Host UI only: call once at a LIVE host boundary, never during rollback.
 * No guest memory, fight commands, network calls or simulation input writes. */
#pragma once
namespace df {
void ui_init();
void ui_tick();
void ui_invalidate();
}
