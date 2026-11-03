/* The in-game question after a casual match (docs/REMATCH_1.2.0.md): host state only. A worker owns all UI file
 * traffic; the LIVE frame boundary copies its snapshot, peeks the local player's controller and publishes an
 * rsx_overlay layer. It never changes guest, input or netplay state: the presses it reads are peeked, never
 * consumed, and the question is only shown and answered on this PC (the launcher sends the vote to the lobby). */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include "df.h"
#include "df_ui.h"
#include "ui_logic.h"
#include "rsx_overlay.h"
#include "../netplay/netplay.h"
#include <atomic>
#include <chrono>
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <cstdlib>
#include <cstdio>
#include <mutex>
#include <thread>

extern "C" int32_t t5_local_player_pad_ui(void* out);

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
void prepare(const ui::Prompt& p) {
    /* Installed-font lookup/rasterization belongs to the worker. The live tick only looks in the prepared cache. */
    for(const std::string* s:{&p.title,&p.body,&p.confirm,&p.cancel,&p.next,&p.opponent,&p.status,
                              &p.key_confirm,&p.key_cancel})
        rsx_overlay_text_prepare(s->c_str());
}
bool supported(const ui::Prompt& p) {
    for(const std::string* s:{&p.title,&p.body,&p.confirm,&p.cancel,&p.next,&p.opponent,&p.status,
                              &p.key_confirm,&p.key_cancel})
        if(!s->empty()&&!rsx_overlay_text_supported(s->c_str())) return false;
    return true;
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
    /* live thread owns these */
    ui::Menu menu;
    bool shown=false;
    uint64_t supported_rev=0; bool supported_ok=false;
    uint64_t drawn_sig=~0ull;
    std::string logged_prompt;  /* the question last logged as shown */
    Host() { if(enabled) { rsx_overlay_prepare(); worker=std::thread([this] { work(); }); } }
    ~Host() { stop=true; wake.notify_all(); if(worker.joinable()) worker.join(); }
    void work() {
        uint64_t last_rev=0, last_action=0, last_ready_ms=0;
        std::string last_ready;
        while(!stop.load()) {
            std::string text; ui::Prompt incoming;
            if(read_bounded(dir+T5P_SEP "ui.json",text)&&ui::parse_prompt(text,incoming)&&
                incoming.generation==generation&&incoming.session==session&&incoming.rev>last_rev) {
                incoming.received_ms=now_ms(); last_rev=incoming.rev;
                prepare(incoming);
                std::lock_guard<std::mutex> lock(mutex); snapshot=incoming;
            }
            ui::Action action;
            { std::lock_guard<std::mutex> lock(mutex); action=outgoing; }
            if(action.seq&&action.seq!=last_action) {
                std::string a="{\"v\":1,\"generation\":"+quote(action.generation)+",\"session\":"+quote(action.session)+
                    ",\"prompt\":"+quote(action.prompt)+",\"match\":"+quote(action.match)+",\"seq\":"+std::to_string(action.seq)+
                    ",\"action\":"+quote(action.action)+"}\n";
                if(write_atomic(dir+T5P_SEP "ui_action.json",a)) last_action=action.seq;
            }
            /* The heartbeat: the launcher trusts the in-game question only while this file keeps coming
             * (ingame_ui.HEALTH_SECONDS); written when it changes, else twice a second. */
            const bool r=ready.load();
            const std::string body=std::string(r?"true":"false")+"|"+std::to_string(rendered.load());
            const uint64_t t=now_ms();
            if(body!=last_ready||t-last_ready_ms>=500) {
                const std::string doc="{\"v\":1,\"generation\":"+quote(generation)+",\"session\":"+quote(session)+
                    ",\"cap\":\"ingame_rematch_v1\",\"ready\":"+(r?"true":"false")+
                    ",\"seq\":"+std::to_string(live.load())+",\"rev\":"+std::to_string(rendered.load())+"}\n";
                if(write_atomic(dir+T5P_SEP "ui_ready.json",doc)) { last_ready=body; last_ready_ms=t; }
            }
            std::unique_lock<std::mutex> lock(mutex);
            wake.wait_for(lock,std::chrono::milliseconds(50),[this] { return stop.load(); });
        }
    }
};
Host& host() { static Host h; return h; }

/* ---- drawing (1280 x 720 overlay canvas) ---- */
constexpr float kPanelX=250, kPanelY=232, kPanelW=780, kPanelH=268, kLeft=kPanelX+30, kTextW=kPanelW-60;
uint32_t dim(uint32_t rgba,bool d) { return d?((rgba&0xFFFFFF00u)|((rgba&255u)/3u)):rgba; }
/* Text the overlay's own 5x7 font cannot draw (anything past ASCII but the German letters) comes from a Windows font
 * as 16-pixel glyphs (patch 0089, a 12-pixel em); at the same px those read smaller than the 5x7 letters: 1.7x. */
bool native_text(const std::string& s) {
    for(size_t i=0;i<s.size();) {
        const unsigned char c=(unsigned char)s[i];
        if(c<0x80) { ++i; continue; }
        unsigned cp=0; size_t n=c<0xe0?2:c<0xf0?3:4;
        if(i+n>s.size()) return true;
        cp=n==2?(c&31u):n==3?(c&15u):(c&7u);
        for(size_t k=1;k<n;++k) cp=(cp<<6)|((unsigned char)s[i+k]&63u);
        if(cp!=0xC4&&cp!=0xD6&&cp!=0xDC&&cp!=0xE4&&cp!=0xF6&&cp!=0xFC&&cp!=0xDF) return true;
        i+=n;
    }
    return false;
}
/* One line of UTF-8 text, cut (at a whole codepoint) to fit `width`. */
void line(const std::string& text,float x,float y,float px,uint32_t color,float width,unsigned flags=RSX_OVL_SHADOW) {
    if(text.empty()) return;
    if(native_text(text)) { y-=px; px*=1.7f; }
    std::string out; size_t at=0;
    while(at<text.size()&&text[at]!='\n') {
        const unsigned char c=(unsigned char)text[at];
        const size_t n=c<0x80?1:c<0xe0?2:c<0xf0?3:4;
        std::string next=out+text.substr(at,n);
        if(!out.empty()&&rsx_overlay_text_width(next.c_str(),px)>width) break;
        out=next; at+=n;
    }
    rsx_overlay_text(x,y,px,color,flags,out.c_str());
}
/* The PlayStation symbols, drawn (no font has them everywhere): Cross and Circle, r = radius in canvas units. */
void cross_symbol(float cx,float cy,float r,uint32_t color) {
    const float t=3.0f;
    for(float i=-r*0.62f;i<=r*0.62f;i+=1.0f) {
        rsx_overlay_rect(cx+i-t*0.5f,cy+i-t*0.5f,t,t,color);
        rsx_overlay_rect(cx+i-t*0.5f,cy-i-t*0.5f,t,t,color);
    }
}
void ring(float cx,float cy,float r,uint32_t color,float t) {
    const int n=(int)(r*6.3f);
    for(int k=0;k<n;++k) {
        const float a=6.2831853f*(float)k/(float)n;
        rsx_overlay_rect(cx+r*std::cos(a)-t*0.5f,cy+r*std::sin(a)-t*0.5f,t,t,color);
    }
}
void circle_symbol(float cx,float cy,float r,uint32_t color) { ring(cx,cy,r*0.55f,color,3.0f); }
/* A button hint: [PlayStation symbol in a dark disc] [Xbox letter] [keyboard key cap] label. Returns the x after it. */
float hint(float x,float y,bool cross,const std::string& key,const std::string& label,bool off) {
    const float cy=y+10;
    rsx_overlay_rect(x,y-2,24,24,dim(RSX_OVL_RGBA(30,32,44,255),off));
    if(cross) cross_symbol(x+12,cy,11,dim(RSX_OVL_RGBA(140,180,255,255),off));
    else circle_symbol(x+12,cy,11,dim(RSX_OVL_RGBA(255,120,140,255),off));
    x+=32;
    rsx_overlay_text(x,y+3,2.0f,dim(cross?RSX_OVL_RGBA(110,210,110,255):RSX_OVL_RGBA(235,95,95,255),off),
                     RSX_OVL_SHADOW,cross?"A":"B");
    x+=18;
    if(!key.empty()) {
        const float w=std::max(22.0f,rsx_overlay_text_width(key.c_str(),2.0f)+12.0f);
        const uint32_t edge=dim(RSX_OVL_RGBA(200,200,210,255),off);
        rsx_overlay_rect(x,y-2,w,24,dim(RSX_OVL_RGBA(45,47,60,255),off));
        rsx_overlay_rect(x,y-2,w,2,edge); rsx_overlay_rect(x,y+20,w,2,edge);
        rsx_overlay_rect(x,y-2,2,24,edge); rsx_overlay_rect(x+w-2,y-2,2,24,edge);
        rsx_overlay_text(x+w*0.5f,y+3,2.0f,dim(RSX_OVL_RGBA(240,240,240,255),off),RSX_OVL_CENTER,key.c_str());
        x+=w;
    }
    x+=12;
    line(label,x,y+3,2.0f,dim(RSX_OVL_RGBA(240,240,240,255),off),kPanelX+kPanelW-30-x);
    return x;
}
uint32_t opp_color(const std::string& state) {
    if(state=="accept") return RSX_OVL_RGBA(125,240,150,255);
    if(state=="decline") return RSX_OVL_RGBA(250,130,130,255);
    return RSX_OVL_RGBA(205,205,215,255);
}
void draw(Host& h,uint64_t now) {
    const ui::Prompt& p=h.menu.prompt();
    if(!h.menu.visible(now)) {
        if(h.shown) rsx_overlay_clear_layer(1);
        h.shown=false; h.drawn_sig=~0ull; return;
    }
    const uint64_t cd=h.menu.countdown(now);
    const unsigned seconds=(unsigned)((cd+999)/1000);
    const float frac=p.total_ms&&cd?std::min(1.0f,(float)cd/(float)p.total_ms):0.0f;
    const unsigned bar_step=(unsigned)(frac*140.0f);         /* the bar moves in 5-unit steps */
    const bool locked=h.menu.locked(now), waiting=h.menu.waiting();
    const uint64_t sig=(p.rev<<20)^((uint64_t)seconds<<10)^((uint64_t)bar_step<<2)^(locked?2u:0u)^(waiting?1u:0u);
    if(h.shown&&sig==h.drawn_sig) return;                    /* nothing on screen changed */
    rsx_overlay_begin_layer(1);
    rsx_overlay_rect(kPanelX,kPanelY,kPanelW,kPanelH,RSX_OVL_RGBA(8,10,18,248));
    rsx_overlay_rect(kPanelX,kPanelY,kPanelW,4,RSX_OVL_RGBA(255,214,72,255));
    line(p.title,kLeft,kPanelY+20,3.0f,RSX_OVL_RGBA(255,214,72,255),kTextW-90);
    if(p.countdown_ms) {
        char timer[16]; snprintf(timer,sizeof timer,"%u",seconds);
        rsx_overlay_text(kPanelX+kPanelW-30,kPanelY+16,4.0f,seconds<=3?RSX_OVL_RGBA(255,110,110,255):
                         RSX_OVL_RGBA(245,245,245,255),RSX_OVL_RIGHT|RSX_OVL_SHADOW,timer);
    }
    line(p.body,kLeft,kPanelY+66,2.0f,RSX_OVL_RGBA(225,225,230,255),kTextW);
    line(p.opponent,kLeft,kPanelY+100,2.0f,opp_color(p.opp_state),kTextW);
    line(p.status,kLeft,kPanelY+134,2.0f,RSX_OVL_RGBA(180,210,255,255),kTextW);
    if(p.countdown_ms&&p.total_ms) {
        rsx_overlay_rect(kLeft,kPanelY+172,kTextW,8,RSX_OVL_RGBA(55,58,72,255));
        rsx_overlay_rect(kLeft,kPanelY+172,kTextW*(float)bar_step/140.0f,8,
                         seconds<=3?RSX_OVL_RGBA(255,110,110,255):RSX_OVL_RGBA(255,214,72,255));
    }
    const float hy=kPanelY+206;
    const bool can_confirm=*p.mapped(ui::kConfirm)!=0, can_cancel=*p.mapped(ui::kCancel)!=0;
    float x=kLeft;
    if(can_confirm) x=hint(x,hy,true,p.key_confirm,p.confirm,locked||waiting)+40.0f;
    if(can_cancel) hint(can_confirm?std::max(x,kLeft+kTextW*0.5f):kLeft,hy,false,p.key_cancel,p.cancel,locked||waiting);
    rsx_overlay_end(); h.shown=true; h.drawn_sig=sig;
}
}
void ui_init() { (void)host(); }
void ui_tick() {
    Host& h=host(); if(!h.enabled) return;
    const uint64_t now=now_ms();
    { std::unique_lock<std::mutex> lock(h.mutex,std::try_to_lock);
      if(lock.owns_lock()&&h.snapshot.rev) h.menu.update(h.snapshot,h.snapshot.received_ms,h.generation,h.session); }
    const ui::Prompt& p=h.menu.prompt();
    if(p.rev!=h.supported_rev) { h.supported_rev=p.rev; h.supported_ok=supported(p); }
    const bool capable=rsx_overlay_ready()!=0&&h.supported_ok;
    ++h.live;
    if(!capable) {
        /* (the launcher sees no fresh "ready" for this revision and asks in its own window instead) */
        h.ready=false; h.menu.tick(0,false,now);
        if(h.shown) rsx_overlay_clear_layer(1);
        h.shown=false; h.drawn_sig=~0ull; return;
    }
    /* Pads count without the window's focus (as in a match); the keyboard needs it (the runtime's rule). A device
     * switch (or none) makes a held button count only after it was let go. */
    HostPadData pad{};
    bool fresh=true;
    if(h.menu.visible(now)) fresh=t5_local_player_pad_ui(&pad)==0;
    const uint16_t buttons=fresh?(uint16_t)((pad.button[2]&255)|((pad.button[3]&255)<<8)):0;
    if(h.menu.visible(now)&&p.prompt!=h.logged_prompt) {
        h.logged_prompt=p.prompt;
        note("in-game question shown: %s for match %s (%llu ms, buttons %s)",p.kind.c_str(),p.match.c_str(),
             (unsigned long long)p.remaining_ms,p.permits("accept")?"Cross/Circle":"Circle");
    }
    if(h.menu.tick(buttons,fresh,now))
        note("in-game question answered: %s (match %s)",h.menu.pending().action.c_str(),p.match.c_str());
    { std::unique_lock<std::mutex> lock(h.mutex,std::try_to_lock);
      if(lock.owns_lock()) h.outgoing=h.menu.pending(); }
    draw(h,now);
    h.rendered=h.menu.prompt().rev; h.ready=true;
}
void ui_invalidate() {
    Host& h=host(); if(!h.enabled) return;
    h.menu.invalidate(); h.ready=false;
    if(h.shown) rsx_overlay_clear_layer(1);
    h.shown=false; h.drawn_sig=~0ull;
}
}
