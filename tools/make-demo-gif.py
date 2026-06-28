from PIL import Image, ImageDraw, ImageFont
DEJAVU=('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',0)
NOTO=('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',7)
SZ=22; LH=33; PAD=18
BG=(30,30,30); FG=(212,212,212); DIM=(120,120,120); TEAL=(78,201,176); HINT=(140,140,140)
HLBG=(205,205,205); HLFG=(20,20,20); GREEN=(106,153,85)
SESS=[('api-server',True,'~/projects/api'),('ml-train',True,'~/work/ml'),
      ('notebook',False,'~/notebooks'),('logs',True,'/var/log/app'),
      ('vsct-48109',True,'~/projects/api')]
STR={
 'en':{'font':DEJAVU,
   'hint':' type = new tmux session · ↑↓ pick existing · ←→ move cursor · Enter confirm · Esc = plain shell',
   'auto':'auto name (vsct-48213)  · Enter to use (disposable)','new':'new / attach: ',
   'att':'·attached','pad':'         ','c1':'✓ attaching tmux session: ','cn':'deploy','pr':'deploy ~ $ '},
 'zh':{'font':NOTO,
   'hint':' 输名字新建 tmux 会话 · ↑↓ 选已有 · ←→ 移光标 · Enter 确认 · Esc 退普通 shell',
   'auto':'自动名 (vsct-48213)  · 回车即用 (用完即弃)','new':'新建并接入: ',
   'att':'·已连','pad':'     ','c1':'✓ 接入 tmux 会话: ','cn':'deploy','pr':'deploy ~ $ '},
}
def build(lang):
    S=STR[lang]; fp,idx=S['font']; F=ImageFont.truetype(fp,SZ,index=idx); CW=F.getlength('M')
    NAMECOL,MARKCOL,PATHCOL=3,23,34
    gl=lambda s:F.getlength(s)
    maxpx=PAD+gl(S['hint'])
    for n,a,p in SESS: maxpx=max(maxpx,PAD+PATHCOL*CW+gl(p))
    W=int(maxpx+PAD); H=int(PAD*2+(len(SESS)+2)*LH)
    def img(): im=Image.new('RGB',(W,H),BG); return im,ImageDraw.Draw(im)
    def at(d,col,row,s,fill): d.text((PAD+col*CW,PAD+row*LH),s,font=F,fill=fill)
    def bar(d,row): y=PAD+row*LH; d.rectangle([PAD-6,y-2,W-PAD+6,y+LH-4],fill=HLBG)
    def sess(d,row,n,a,p,sel):
        mark=S['att'] if a else S['pad']
        if sel:
            bar(d,row); at(d,0,row,' ▶ ',HLFG); at(d,NAMECOL,row,n,HLFG); at(d,MARKCOL,row,mark,HLFG); at(d,PATHCOL,row,p,HLFG)
        else:
            at(d,NAMECOL,row,n,FG); at(d,MARKCOL,row,mark,TEAL if a else FG); at(d,PATHCOL,row,p,DIM)
    def auto(d,row,sel,q,cp):
        if not q:
            at(d,0,row,(' ▶ ' if sel else '   ')+S['auto'],HLFG if sel else FG)
            if sel: 
                pass
        else:
            pre=' ▶ '+S['new']; at(d,0,row,pre+q,FG)
            x0=PAD+gl(pre+q[:cp]); ch=q[cp] if cp<len(q) else ' '
            d.rectangle([x0,PAD+row*LH-2,x0+CW,PAD+row*LH+LH-4],fill=HLBG); d.text((x0,PAD+row*LH),ch,font=F,fill=HLFG)
    def auto_full(d,row,sel,q,cp):  # fix: bar must be under text for empty-query selected
        if not q and sel: bar(d,row)
        auto(d,row,sel,q,cp)
    def frame(sel,q='',cp=0):
        im,d=img(); at(d,0,0,S['hint'],HINT); auto_full(d,1,sel==0,q,cp)
        for i,(n,a,p) in enumerate(SESS): sess(d,2+i,n,a,p,sel==i+1)
        return im
    def commit():
        im,d=img(); d.text((PAD,PAD+LH),S['c1'],font=F,fill=FG)
        d.text((PAD+gl(S['c1']),PAD+LH),S['cn'],font=F,fill=TEAL)
        d.text((PAD,PAD+3*LH),S['pr'],font=F,fill=GREEN)
        bx=PAD+gl(S['pr']); d.rectangle([bx,PAD+3*LH-2,bx+CW,PAD+3*LH+LH-4],fill=HLBG)
        return im
    return frame,commit
SEQ=[(0,'',0,1500),(1,'',0,650),(2,'',0,650),(3,'',0,950),(4,'',0,650),(5,'',0,950),
     (0,'d',1,220),(0,'de',2,220),(0,'dep',3,200),(0,'depl',4,200),(0,'deplo',5,200),
     (0,'deploy',6,950),(0,'deploy',5,350),(0,'deploy',4,650),(0,'deploy',5,300),(0,'deploy',6,800)]
for lang in('en','zh'):
    frame,commit=build(lang)
    fr=[frame(s,q,c) for s,q,c,_ in SEQ]+[commit()]; du=[d for *_,d in SEQ]+[1700]
    pal=fr[0].quantize(colors=32,method=Image.MEDIANCUT)
    q=[f.quantize(palette=pal,dither=Image.NONE) for f in fr]
    q[0].save(f'vsct-demo-{lang}.gif',save_all=True,append_images=q[1:],duration=du,loop=0,disposal=2,optimize=True)
    fr[3].save(f'pv-{lang}-browse.png'); fr[10].save(f'pv-{lang}-type.png')
    print(lang,fr[0].size,'frames',len(fr))
