#!/usr/bin/env python3
"""RideStrong 2.0: prepare six 30-minute music + natural female coaching previews.
Original MP4s stay untouched. Requires ffmpeg and numpy. Source voice: HeyGen Priti (en-IN).
"""
import json, math, os, subprocess, urllib.request, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "v2_preview"
OUT.mkdir(exist_ok=True)
WORK = ROOT / "_ridestrong2_tmp"
WORK.mkdir(exist_ok=True)
SR, LENGTH = 24000, 1800
VOICE_NAME = "Priti - Composed & Direct (HeyGen public AI voice)"
SOURCES = {
 "count": "https://resource2.heygen.ai/text_to_speech/76687856a0f34a5ebb2b720da6dc4e4a/da9659970e9d4250be76c3f628565bc7/id=e5248eba2e3549578e1f6285050bc99c.wav",
 "a": "https://resource2.heygen.ai/text_to_speech/76687856a0f34a5ebb2b720da6dc4e4a/da9659970e9d4250be76c3f628565bc7/id=75b59d0f788e4fda8c811ceed4f61d47.wav",
 "b": "https://resource2.heygen.ai/text_to_speech/76687856a0f34a5ebb2b720da6dc4e4a/da9659970e9d4250be76c3f628565bc7/id=4f91a6448fe64427b9bda33a6bf9d915.wav",
}
SPAN = {
 "a": [(0.256,6.372),(6.741,14.388),(14.920,20.808),(21.149,25.956),(26.355,30.945),(31.314,35.823),(36.136,41.961)],
 "b": [(0.256,4.537),(4.907,10.183),(10.667,14.838),(15.331,20.238),(20.750,26.623),(26.936,31.712),(32.110,37.045),(37.443,43.367),(43.822,48.914),(49.284,54.027),(54.340,58.180),(58.521,63.264),(63.619,68.198),(68.568,72.735),(73.134,76.504),(76.931,80.335),(80.704,86.028)]
}
DAY = [
 ("01_legs_and_glutes_30min.mp4",("a",0),[("a",1),("a",2),("a",3),("a",4),("a",5)]),
 ("02_upper_body_and_arms_30min.mp4",("b",0),[("b",5),("b",6),("b",7),("b",8),("b",9)]),
 ("03_core_and_back_stability_30min.mp4",("b",1),[("b",10),("b",11),("a",2),("b",12),("a",5)]),
 ("04_legs_and_balance_30min.mp4",("b",2),[("a",1),("a",4),("a",3),("b",13),("a",2)]),
 ("05_full_body_and_posture_30min.mp4",("b",3),[("b",5),("a",1),("b",10),("b",7),("a",5)]),
 ("06_low-impact_cardio_and_mobility_30min.mp4",("b",4),[("b",14),("b",15),("a",3),("b",16),("b",8)]),
]

def ff(*args):
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",*map(str,args)], check=True)

def fetch_stem(key):
    target = WORK / (key + "_raw.wav")
    if not target.exists():
        req=urllib.request.Request(SOURCES[key],headers={"User-Agent":"RideStrong-Audio-Build/2.0"})
        with urllib.request.urlopen(req,timeout=100) as r, open(target,"wb") as f:
            while True:
                b=r.read(1024*1024)
                if not b:break
                f.write(b)
    normalized=WORK/(key+"_24000.wav")
    if not normalized.exists():
        ff("-i",target,"-ac","1","-ar",SR,"-c:a","pcm_s16le",normalized)
    with wave.open(str(normalized),"rb") as wf:
        assert wf.getnchannels()==1 and wf.getframerate()==SR
        return np.frombuffer(wf.readframes(wf.getnframes()),dtype=np.int16).astype(np.float32)/32768.

def split_countdown(sig):
    """Segment the 31 generated words using quiet gaps, merging syllable boundaries.
    Preserve each spoken word's real speed; place the extracted words at exact
    seconds on the final timeline. Never stretch the narrator's pitch or cadence.
    """
    n=len(sig)
    hop=120
    m=n//hop
    env=np.sqrt(np.mean(sig[:m*hop].reshape(m,hop)**2,axis=1))
    smoothed=np.convolve(env,np.ones(5,dtype=np.float32)/5,mode="same")
    peak=float(np.max(smoothed))
    candidates=[]
    for fraction in (.012,.018,.025,.035,.045,.065,.09,.12,.20):
        for glue in (.01,.018,.025,.035,.045,.060,.08,.10,.13):
            threshold=max(.002,peak*fraction)
            active=np.where(smoothed>threshold)[0]
            if len(active)==0:continue
            groups=[]
            start=last=int(active[0])
            for raw in active[1:]:
                f=int(raw)
                if (f-last)*hop/SR>glue:
                    if (last-start)*hop/SR>.060:groups.append([start,last])
                    start=f
                last=f
            if (last-start)*hop/SR>.060:groups.append([start,last])
            if len(groups)>=31:
                # Smaller silent gaps are more likely pauses *within* a word.
                # Prefer modest over-segmentation to avoid swallowing adjacent words.
                excess=len(groups)-31
                if excess<=20:
                    candidates.append((excess,fraction,glue,groups))
    if not candidates:
        raise RuntimeError("Voice count segmentation yielded fewer than 31 detected word groups; cannot guarantee an aligned countdown.")
    excess,fraction,glue,groups=min(candidates,key=lambda x:(x[0],abs(x[2]-.045),abs(x[1]-.035)))
    while len(groups)>31:
        gaps=[(groups[j+1][0]-groups[j][1],j) for j in range(len(groups)-1)]
        _,j=min(gaps)
        groups[j:j+2]=[[groups[j][0],groups[j+1][1]]]
    # Protect phrase boundaries; <= 25ms fade is added during final placement.
    words=[]
    for a,b in groups:
        left=max(0,int(a*hop-.022*SR))
        right=min(n,int((b+1)*hop+.022*SR))
        words.append(sig[left:right].copy())
    print("Aligned 31 spoken counts", "segments", len(words),
          "longest_sec",round(max(len(w)/SR for w in words),2),flush=True)
    return words

def write_wav(path, signal):
    signal=np.clip(signal,-0.98,0.98)
    with wave.open(str(path),"wb") as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(SR)
        wf.writeframes((signal*32767).astype("<i2").tobytes())

def make_music(path):
    """Original procedural instrumental: bass, chord pads, kick, snare, hats, pluck."""
    rng=np.random.default_rng(20261115)
    roots=[110.0,87.307,130.813,97.999]
    qualities=[(0,3,7),(0,4,7),(0,4,7),(0,4,7)]
    chunks=LENGTH//8
    with wave.open(str(path),"wb") as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(SR)
        n=8*SR
        for c in range(chunks):
            t=np.arange(n,dtype=np.float32)/SR
            chord=c%4
            root=roots[chord]
            music=np.zeros(n,dtype=np.float32)
            # Gentle chord-pad harmonics, slow variation.
            for interval in qualities[chord]:
                f=220.0*(2.0**(interval/12.0))*(root/110.0)
                music+=0.028*(np.sin(2*np.pi*f*t)+.22*np.sin(4*np.pi*f*t))
            # Short bass plucks.
            for k in range(16):
                p=int(k*.5*SR);m=min(n-p,int(.43*SR))
                tt=np.arange(m,dtype=np.float32)/SR
                semitone=(0,0,7,0)[k%4]
                freq=root*(2**(semitone/12))
                music[p:p+m]+=0.11*np.sin(2*np.pi*freq*tt)*np.exp(-7*tt)
                if k%4 in (0,2):
                    d=min(n-p,int(.29*SR));u=np.arange(d,dtype=np.float32)/SR
                    phase=2*np.pi*(49*u+35*(1-np.exp(-23*u))/23)
                    music[p:p+d]+=0.25*np.sin(phase)*np.exp(-19*u)
                if k%4 in (1,3):
                    d=min(n-p,int(.19*SR));u=np.arange(d,dtype=np.float32)/SR
                    no=rng.standard_normal(d).astype(np.float32)
                    music[p:p+d]+=0.070*no*np.exp(-25*u)
            for k in range(32):
                p=int(k*.25*SR);d=min(n-p,int(.065*SR))
                u=np.arange(d,dtype=np.float32)/SR
                no=rng.standard_normal(d).astype(np.float32)
                music[p:p+d]+=.024*no*np.exp(-75*u)
            for k in range(16):
                p=int((k*.5+.25)*SR);d=min(n-p,int(.2*SR))
                if d<=0:continue
                u=np.arange(d,dtype=np.float32)/SR
                note=[0,3,7,12,7,3,0,7][(k+c)%8]
                freq=440*(root/110)*2**(note/12)
                music[p:p+d]+=.031*np.sin(2*np.pi*freq*u)*np.exp(-15*u)
            pos=c*8+t
            energy=np.where(pos<300,.60,np.where(pos>=1500,.48,1.0))
            energy=energy*np.clip(pos/3,0,1)*np.clip((LENGTH-pos)/5,0,1)
            wf.writeframes((np.clip(music*energy,-.85,.85)*32767).astype("<i2").tobytes())

def mix_voice(count_pieces,a,b,intro,exercises):
    voice=np.zeros(LENGTH*SR,dtype=np.float32)
    def put(fragment,when):
        frag=fragment.copy()
        # Very small fades avoid clicks without clipping consonants.
        fade=min(int(.012*SR),len(frag)//4)
        if fade:
            frag[:fade]*=np.linspace(0,1,fade,dtype=np.float32)
            frag[-fade:]*=np.linspace(1,0,fade,dtype=np.float32)
        p=int(when*SR)
        take=min(len(frag),len(voice)-p)
        if take>0: voice[p:p+take]+=frag[:take]
    def cue(k,i,where):
        start,end=SPAN[k][i];source=a if k=="a" else b
        put(source[max(0,int((start-.05)*SR)):min(len(source),int((end+.06)*SR))],where)
    cue(*intro,7.0)
    for j,item in enumerate(exercises):cue(*item,300.8+j*240)
    cue("a",6,1501.2)
    rests=[510,750,990,1230,1470]
    for rest in rests:
        for i,fragment in enumerate(count_pieces):
            put(fragment,rest+i*.977)
    return voice

def build():
    print("Downloading HeyGen voice stems...")
    count=fetch_stem("count");a=fetch_stem("a");b=fetch_stem("b")
    count_pieces=split_countdown(count)
    print("Female countdown words detected:",len(count_pieces))
    music=WORK/"original_workout_music.wav"
    if not music.exists():
        print("Composing 30-minute original music...")
        make_music(music)
    for i,(filename,intro,exercises) in enumerate(DAY,1):
        source=ROOT/"full_videos"/filename
        if not source.exists():raise FileNotFoundError(source)
        print("Mixing",i,filename,flush=True)
        voice=WORK/"voice_timeline.wav"
        write_wav(voice,mix_voice(count_pieces,a,b,intro,exercises))
        target=OUT/filename
        filt="[1:a]volume=1.1,asplit=2[spoken][side];[2:a]volume=.60[bed];[bed][side]sidechaincompress=threshold=.025:ratio=7:attack=15:release=320[duck];[spoken][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=.91:level=disabled[mixed]"
        ff("-i",source,"-i",voice,"-i",music,"-filter_complex",filt,"-map","0:v:0","-map","[mixed]","-c:v","copy","-c:a","aac","-b:a","112k","-ar","24000","-movflags","+faststart",target)
        size=target.stat().st_size
        if size>97*1024*1024:raise RuntimeError("Preview too large for regular GitHub: "+filename)
        result=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(target)],capture_output=True,text=True,check=True)
        duration=float(result.stdout.strip())
        if abs(duration-1800)>.3:raise RuntimeError("Unexpected video duration "+str(duration))
        print("Verified",filename,round(duration,2),"sec",round(size/1048576,1),"MiB",flush=True)
    first=DAY[0][0]
    ff("-ss","505","-i",OUT/first,"-t","52","-map","0:v:0","-map","0:a:0","-c:v","libx264","-preset","fast","-crf","24","-c:a","aac","-b:a","112k","-movflags","+faststart",OUT/"countdown_sample.mp4")
    nav="".join("<li><a href='"+f+"'>"+f.replace("_30min.mp4","").replace("_"," ").title()+"</a></li>" for f,_,_ in DAY)
    html='<!doctype html><html lang="en"><meta charset="utf-8"><title>RideStrong 2.0 Audio Preview</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#102238;color:#eaf6ff;font:18px system-ui;padding:28px;max-width:850px;margin:auto}a{color:#82f7d0}video{width:100%;border-radius:15px}li{margin:12px}h1{color:#87e7cd}</style><h1>RideStrong 2.0 — Audio Preview</h1><p>Female AI instructor: Priti. Original coded workout music. Each 30-minute session includes 5 spoken 30-to-0 rest countdowns. Existing live RideStrong workouts remain unchanged.</p><h2>Rest countdown sample</h2><video controls src="countdown_sample.mp4" preload="metadata"></video><h2>Six full-length workouts</h2><ul>'+nav+'</ul><p>Private preview for review. Do not switch the main app until satisfied with audio.</p></html>'
    (OUT/"index.html").write_text(html,encoding="utf8")
    print("All six previews and listening page generated.")
if __name__=="__main__":build()
