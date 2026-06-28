from PIL import Image, ImageDraw, ImageFont
MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
W,H=1280,640
BG=(24,24,24); PANEL=(37,37,38); PBORDER=(58,58,60)
WHITE=(233,233,233); GREY=(150,156,160); DIM=(110,110,110)
TEAL=(78,201,176); GREEN=(106,153,85); HLBG=(205,205,205); HLFG=(22,22,22)
im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
f_title=ImageFont.truetype(BOLD,62); f_tag=ImageFont.truetype(MONO,28)
f_acc=ImageFont.truetype(MONO,25); f_m=ImageFont.truetype(MONO,27); f_mh=ImageFont.truetype(MONO,22); f_small=ImageFont.truetype(MONO,22)
f_cjk=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',22,index=7)
def seg(x,y,parts,font):
    for s,c in parts:
        d.text((x,y),s,font=font,fill=c); x+=font.getlength(s)
    return x
# left teal accent strip
d.rectangle([0,0,10,H],fill=TEAL)
# title with ▶ cursor motif
seg(70,72,[('▶ ',TEAL),('vscode-tmux-picker',WHITE)],f_title)
# taglines
d.text((78,165),"Pre-attach tmux session picker for the VS Code terminal.",font=f_tag,fill=GREY)
seg(78,210,[('Remote terminals that ',GREY),('survive reconnects',TEAL),('  ·  pure bash  ·  zero deps',GREY)],f_acc)
# mockup panel
px0,py0,px1,py1=70,290,1210,560
d.rounded_rectangle([px0,py0,px1,py1],radius=16,fill=PANEL,outline=PBORDER,width=2)
mx,my,lh=px0+34,py0+26,40
d.text((mx,my),"type = new tmux session · ↑↓ pick existing · ←→ move · Enter confirm",font=f_mh,fill=DIM)
# input row (highlighted feel) with block cursor
ry=my+lh+6
d.rounded_rectangle([px0+14,ry-6,px1-14,ry+34],radius=8,fill=(45,45,46))
x=seg(mx,ry,[(' ▶ ',TEAL),('new tmux session: ',WHITE),('deploy',WHITE)],f_m)
d.rectangle([x+2,ry-2,x+2+f_m.getlength('M'),ry+30],fill=HLBG)  # block cursor
# session rows: name(col) mark(teal) path(dim)
rows=[('api-server',True,'~/code'),('ml-train',True,'~/work'),('notebook',False,'~/notes')]
NAMEW=16
for i,(n,att,p) in enumerate(rows):
    y=ry+lh*(i+1)+4
    d.text((mx,y),'   '+n.ljust(NAMEW),font=f_m,fill=WHITE)
    xm=mx+f_m.getlength('   '+' '*NAMEW)
    d.text((xm,y),('·attached' if att else '         '),font=f_m,fill=TEAL if att else WHITE)
    d.text((xm+f_m.getlength('·attached  ')+8,y),p,font=f_m,fill=DIM)
# bottom strip
seg(78,588,[('VS Code Remote-SSH',DIM),('   ·   ',(70,70,70)),('English / 中文',DIM),('   ·   ',(70,70,70)),('MIT',DIM)],f_cjk)
im.save('social-card.png')
print("saved", im.size)
