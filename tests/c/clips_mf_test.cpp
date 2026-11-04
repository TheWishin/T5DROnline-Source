/* Synthetic encoder/remux test; no game content and no default Videos writes. */
#include "rsx_clips.cpp"
#include <cassert>
static int test_laptop;
extern "C" int host_sched_laptop(void) {return test_laptop;}
static void verify(const wchar_t* path) {
    ComPtr<IMFSourceReader> reader;check(MFCreateSourceReaderFromURL(path,nullptr,&reader));
    PROPVARIANT duration;PropVariantInit(&duration);
    check(reader->GetPresentationAttribute(MF_SOURCE_READER_MEDIASOURCE,MF_PD_DURATION,&duration));
    assert(duration.vt==VT_UI8 && duration.uhVal.QuadPart>=39000000 && duration.uhVal.QuadPart<43000000);
    PropVariantClear(&duration);
    auto t=video_type(MFVideoFormat_NV12);check(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM,nullptr,t.Get()));
    unsigned frames=0;long long last=-1;
    for(;;) {
        DWORD stream,flags;LONGLONG time;ComPtr<IMFSample>s;
        check(reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,&stream,&flags,&time,&s));
        if(s){assert(time>last);last=time;frames++;}
        if(flags&MF_SOURCE_READERF_ENDOFSTREAM)break;
    }
    assert(frames==120);
    // A new reader avoids source-reader stream buffering after reading video.
    reader.Reset();check(MFCreateSourceReaderFromURL(path,nullptr,&reader));
    auto a=audio_type(false);check(reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_AUDIO_STREAM,nullptr,a.Get()));
    unsigned audio_samples=0;long long energy=0;last=-1;
    for(;;) {
        DWORD stream,flags;LONGLONG time;ComPtr<IMFSample>s;
        check(reader->ReadSample(MF_SOURCE_READER_FIRST_AUDIO_STREAM,0,&stream,&flags,&time,&s));
        if(s) {
            assert(time>last);last=time;ComPtr<IMFMediaBuffer>b;check(s->ConvertToContiguousBuffer(&b));BYTE* bytes;DWORD size;
            check(b->Lock(&bytes,nullptr,&size));const short* pcm=reinterpret_cast<short*>(bytes);
            for(unsigned i=0;i<size/2;i++)energy+=std::abs(static_cast<int>(pcm[i]));
            audio_samples+=size/4;check(b->Unlock());
        }
        if(flags&MF_SOURCE_READERF_ENDOFSTREAM)break;
    }
    assert(audio_samples>=185000 && audio_samples<=200000 && energy>10000000);
    printf("PASS: remux decoded %u video frames, %u stereo audio frames; timestamps monotonic; tone present\n",frames,audio_samples);
}
int wmain(int argc,wchar_t** argv) {
    if(argc<2)return 2;
    if(argc>2 && (!wcscmp(argv[2],L"disabled") || !wcscmp(argv[2],L"power-saving") || !wcscmp(argv[2],L"missing-mf"))) {
        _putenv_s("PS3_CLIPS",!wcscmp(argv[2],L"disabled")?"0":"1");
        test_laptop=!wcscmp(argv[2],L"power-saving");
        _putenv_s("PS3_TEST_NO_MEDIA_FOUNDATION",!wcscmp(argv[2],L"missing-mf")?"1":"");
        assert(!rsx_clips_enabled());assert(!ready && !worker.joinable() && !wake && pending.pixels==nullptr);
        rsx_clips_request_save();rsx_clips_shutdown();
        printf("PASS: disabled capture policy starts no worker or frame storage\n");return 0;
    }
    // Mapped views transfer ownership exactly once, including rejection/RAII.
    {
        unsigned releases=0;unsigned char pixels[32]={};
        auto release=+[](void* value){++*static_cast<unsigned*>(value);};
        FrameData view;view.pixels=pixels;view.release=release;view.context=&releases;
        {FrameData moved(std::move(view));assert(!view.pixels);moved.reset();moved.reset();}
        assert(releases==1);
        wake=CreateEventW(nullptr,FALSE,FALSE,nullptr);assert(wake);ready=true;
        assert(rsx_clips_video(pixels,2,2,16,100,release,&releases)==1);
        assert(rsx_clips_video(pixels,2,2,16,200,release,&releases)==0);
        assert(pending.pixels==pixels && releases==1); // rejection retains caller ownership
        ready=false;pending.reset();have_frame=false;
        assert(releases==2);
        assert(rsx_clips_video(pixels,2,2,16,300,release,&releases)==0);
        CloseHandle(wake);wake=nullptr;
        // Row padding is ignored; the bottom green row must be brighter than red.
        pixels[0]=pixels[4]=255;pixels[17]=pixels[21]=255;
        std::vector<unsigned char> pitched;
        to_nv12(pixels,2,2,pitched,16);
        assert(pitched[W/2]<pitched[(H-1)*W+W/2]);
    }
    // Bounded stream rejects writes and seeks before allocation can escape its cap.
    {
        MemoryStream bounded;
        LARGE_INTEGER at;at.QuadPart=SEGMENT_CAP-2;
        check(bounded.Seek(at,STREAM_SEEK_SET,nullptr));
        unsigned char bytes[4]={1,2,3,4};ULONG written=99;
        assert(bounded.Write(bytes,4,&written)==STG_E_MEDIUMFULL && written==0);
        check(bounded.Write(bytes,2,&written));assert(written==2);
        assert(bounded.data.size()==SEGMENT_CAP && bounded.data.capacity()==SEGMENT_CAP);
        ULARGE_INTEGER huge;huge.QuadPart=SEGMENT_CAP+1;
        assert(bounded.SetSize(huge)==STG_E_MEDIUMFULL);
        at.QuadPart=-1;assert(bounded.Seek(at,STREAM_SEEK_SET,nullptr)==STG_E_INVALIDFUNCTION);
    }
    HRESULT co=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(co))return 3;
    try {
        check(MFStartup(MF_VERSION));
        bool hardware=argc>2 && !wcscmp(argv[2],L"hardware");
        clips::Ring ring(RING_CAP,5*SECOND);
        std::vector<unsigned char> rgba(W*H*4),nv12;
        for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++) {
            auto* p=rgba.data()+(y*W+x)*4;p[0]=static_cast<unsigned char>(x*255/W);p[1]=static_cast<unsigned char>(y*255/H);p[2]=20;p[3]=255;
        }
        to_nv12(rgba.data(),W,H,nv12);
        // Top red/green ramp has lower luma than its bottom; RGBA swizzle/flip.
        assert(nv12[W/2]<nv12[(H-1)*W+W/2]);
        ready=true;
        for(unsigned segment=0;segment<3;segment++) {
            Encoder enc(100000000+segment*2*SECOND,hardware);
            for(unsigned frame=0;frame<60;frame++) {
                long long at=enc.start+static_cast<long long>(frame)*SECOND/FPS;
                const long long audio_at=at;
                if(frame&1)at+=10000; // 1 ms render jitter, including each segment cut.
                std::array<float,3200> tone;
                for(unsigned i=0;i<1600;i++) {
                    float v=.3f*std::sin(2*3.141592653589793*440*(frame*1600+i)/48000.0);
                    tone[i*2]=v;tone[i*2+1]=v;
                }
                rsx_clips_audio(tone.data(),1600,audio_at);
                sample(enc.writer.Get(),enc.video,nv12.data(),static_cast<DWORD>(nv12.size()),at-enc.start,FRAME);
                enc.end=at+FRAME;
                audio_until(enc,at);
            }
            enc.end=std::min(enc.end,enc.start+2*SECOND);
            audio_until(enc,enc.end);assert(enc.audio_frames==96000);
            assert(ring.push(enc.finish()));
        }
        assert(ring.segments().size()==2);assert(ring.bytes()<=RING_CAP);
        remux(ring,argv[1]);verify(argv[1]);
        ready=false;MFShutdown();CoUninitialize();return 0;
    } catch(const Failure& f) {fprintf(stderr,"FAIL: HRESULT 0x%08lx\n",static_cast<unsigned long>(f.hr));}
    catch(...) {fprintf(stderr,"FAIL: exception\n");}
    CoUninitialize();return 1;
}
