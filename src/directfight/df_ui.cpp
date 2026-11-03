/* In-game result menu: host state only. A worker owns all UI file traffic;
 * the LIVE frame boundary only copies snapshots, peeks the local device and
 * publishes an rsx_overlay layer. It never changes guest/input/net state. */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include "df_ui.h"
#include "ui_logic.h"
#include "rsx_overlay.h"
#include "../netplay/netplay.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstdio>
#include <mutex>
#include <thread>

extern "C" int32_t t5_local_player_pad_ui(void* out);
extern "C" int cellPad_ui_focused(void);

namespace df {
namespace {
uint64_t now_ms() { return GetTickCount64(); }
std::string env(const char* name) { const char* v=getenv(name); return v?v:""; }
std::string quote(const std::string& s) {
    std::string out="\"";
    for(unsigned char c:s) {
        if(c=='"'||c=='\\') { out+='\\'; out+=(char)c; }
        else if(c<32) { char b[8]; snprintf(b,sizeof b,"\\u%04x",c); out+=b; }
        else out+=(char)c;
    }
    return out+'"';
}
bool read_bounded(const std::string& path,std::string& out) {
    intptr_t h=t5p_open_read_shared(path.c_str()); if(h==-1) return false;
    char buf[2048]; long n=0; bool ok=true;
    while((n=t5p_read(h,buf,sizeof buf))>0) {
        if(out.size()+(size_t)n>ui::kMessageMax) { ok=false; break; }
        out.append(buf,(size_t)n);
    }
    t5p_close(h); return ok&&n>=0;
}
bool write_atomic(const std::string& path,const std::string& text) {
    const std::string tmp=path+".tmp";
    FILE* f=fopen(tmp.c_str(),"wb"); if(!f) return false;
    bool ok=fwrite(text.data(),1,text.size(),f)==text.size();
    if(fclose(f)!=0) ok=false;
    return ok&&t5p_replace_file(tmp.c_str(),path.c_str());
}
struct Host {
    const std::string dir=env("T5_UI_DIR"),generation=env("T5_UI_GENERATION"),session=env("T5_UI_SESSION");
    const bool enabled=env("T5_INGAME_REMATCH")=="1"&&!dir.empty()&&!generation.empty()&&!session.empty()&&
        generation.size()<=ui::kIdentityMax&&session.size()<=ui::kIdentityMax;
    std::mutex mutex;
    std::condition_variable wake;
    std::atomic<bool> stop{false},ready{false};
    std::atomic<uint64_t> live{0};
    std::atomic<uint64_t> rendered{0};
    ui::Prompt snapshot;
    ui::Action outgoing;
    std::thread worker;
    ui::Menu menu;  /* live thread owns this */
    bool shown=false;
    Host() { if(enabled) { rsx_overlay_prepare(); worker=std::thread([this] { work(); }); } }
    ~Host() { stop=true; wake.notify_all(); if(worker.joinable()) worker.join(); }
    void work() {
        uint64_t last_rev=0;
        while(!stop.load()) {
            std::string text; ui::Prompt incoming;
            if(read_bounded(dir+T5P_SEP "ui.json",text)&&ui::parse_prompt(text,incoming)&&
                incoming.generation==generation&&incoming.session==session&&incoming.rev>last_rev) {
                incoming.received_ms=now_ms(); last_rev=incoming.rev;
                /* Installed-font lookup/rasterization belongs to this worker.
                 * Live supported()/drawing only inspect the prepared cache. */
                rsx_overlay_text_prepare(incoming.title.c_str());
                rsx_overlay_text_prepare(incoming.body.c_str());
                rsx_overlay_text_prepare(incoming.confirm.c_str());
                rsx_overlay_text_prepare(incoming.cancel.c_str());
                rsx_overlay_text_prepare(incoming.next.c_str());
                std::lock_guard<std::mutex> lock(mutex); snapshot=incoming;
            }
            ui::Action action;
            { std::lock_guard<std::mutex> lock(mutex); action=outgoing; }
            if(action.seq) {
                std::string a="{\"v\":1,\"generation\":"+quote(action.generation)+",\"session\":"+quote(action.session)+
                    ",\"prompt\":"+quote(action.prompt)+",\"match\":"+quote(action.match)+",\"seq\":"+std::to_string(action.seq)+
                    ",\"action\":"+quote(action.action)+"}\n";
                write_atomic(dir+T5P_SEP "ui_action.json",a);
            }
            const std::string r="{\"v\":1,\"generation\":"+quote(generation)+",\"session\":"+quote(session)+
                ",\"cap\":\"ingame_rematch_v1\",\"ready\":"+(ready.load()?"true":"false")+
                ",\"seq\":"+std::to_string(live.load())+",\"rev\":"+std::to_string(rendered.load())+"}\n";
            write_atomic(dir+T5P_SEP "ui_ready.json",r);
            std::unique_lock<std::mutex> lock(mutex);
            wake.wait_for(lock,std::chrono::milliseconds(50),[this] { return stop.load(); });
        }
    }
};
Host& host() { static Host h; return h; }
bool supported(const ui::Prompt& p) {
    return rsx_overlay_text_supported(p.title.c_str())&&rsx_overlay_text_supported(p.body.c_str())&&
        rsx_overlay_text_supported(p.confirm.c_str())&&rsx_overlay_text_supported(p.cancel.c_str())&&
        rsx_overlay_text_supported(p.next.c_str());
}
/* Fit UTF-8 text into the panel, preserving complete codepoints. Renderer clips
 * text vertically; limits also prevent arbitrarily long names covering hints. */
void lines(const std::string& text,float y,unsigned max_lines,float px,uint32_t color) {
    size_t at=0;
    for(unsigned row=0;row<max_lines&&at<text.size();++row) {
        std::string line;
        while(at<text.size()) {
            if(text[at]=='\n') { ++at; break; }
            const unsigned char c=(unsigned char)text[at];
            size_t n=c<0x80?1:c<0xe0?2:c<0xf0?3:4;
            std::string next=line+text.substr(at,n);
            if(!line.empty()&&rsx_overlay_text_width(next.c_str(),px)>920.0f) break;
            line=next; at+=n;
        }
        rsx_overlay_text(180,y+row*30,px,color,RSX_OVL_SHADOW,line.c_str());
    }
}
/* Symbols describe the normalized PS3 buttons the local mapping exposes;
 * launcher-supplied action labels remain localized separately. */
void button_hint(uint16_t button,float y) {
    const uint32_t color=RSX_OVL_RGBA(240,240,240,255);
    const char* glyph=button==ui::kConfirm?"X":button==ui::kCancel?"O":"[]";
    rsx_overlay_text(155,y,1.5f,color,RSX_OVL_CENTER|RSX_OVL_SHADOW,glyph);
}
void draw(Host& h,uint64_t now) {
    const ui::Prompt& p=h.menu.prompt();
    if(!h.menu.visible(now)) {
        if(h.shown) rsx_overlay_clear_layer(1);
        h.shown=false; return;
    }
    rsx_overlay_begin_layer(1);
    rsx_overlay_rect(140,210,1000,330,RSX_OVL_RGBA(8,10,18,232));
    lines(p.title,235,2,2.5f,RSX_OVL_RGBA(255,214,72,255));
    lines(p.body,305,4,2.0f,RSX_OVL_RGBA(240,240,240,255));
    if(*p.mapped(ui::kConfirm)) { button_hint(ui::kConfirm,435); lines(p.confirm,435,1,1.5f,RSX_OVL_RGBA(125,240,150,255)); }
    if(*p.mapped(ui::kCancel)) { button_hint(ui::kCancel,465); lines(p.cancel,465,1,1.5f,RSX_OVL_RGBA(240,180,180,255)); }
    if(*p.mapped(ui::kNext)) { button_hint(ui::kNext,495); lines(p.next,495,1,1.5f,RSX_OVL_RGBA(180,210,255,255)); }
    char timer[24]; snprintf(timer,sizeof timer,"%llu",(unsigned long long)((h.menu.remaining(now)+999)/1000));
    rsx_overlay_text(1095,495,2,RSX_OVL_RGBA(240,240,240,255),RSX_OVL_RIGHT,timer);
    rsx_overlay_end(); h.shown=true;
}
}
void ui_init() { (void)host(); }
void ui_tick() {
    Host& h=host(); if(!h.enabled) return;
    const uint64_t now=now_ms();
    { std::unique_lock<std::mutex> lock(h.mutex,std::try_to_lock);
      if(lock.owns_lock()&&h.snapshot.rev) h.menu.update(h.snapshot,h.snapshot.received_ms,h.generation,h.session); }
    const bool capable=rsx_overlay_ready()!=0&&supported(h.menu.prompt());
    ++h.live;
    if(!capable) {
        h.ready=false; h.menu.tick(0,false,now);
        if(h.shown) rsx_overlay_clear_layer(1); h.shown=false; return;
    }
    HostPadData pad{};
    bool focused=cellPad_ui_focused()!=0;
    if(focused&&h.menu.visible(now)&&t5_local_player_pad_ui(&pad)!=0) focused=false;
    const uint16_t buttons=(uint16_t)((pad.button[2]&255)|((pad.button[3]&255)<<8));
    h.menu.tick(buttons,focused,now);
    { std::unique_lock<std::mutex> lock(h.mutex,std::try_to_lock);
      if(lock.owns_lock()) h.outgoing=h.menu.pending(); }
    draw(h,now);
    h.rendered=h.menu.prompt().rev; h.ready=true;
}
void ui_invalidate() {
    Host& h=host(); if(!h.enabled) return;
    h.menu.invalidate(); h.ready=false;
    if(h.shown) rsx_overlay_clear_layer(1); h.shown=false;
}
}
