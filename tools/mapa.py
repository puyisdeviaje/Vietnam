import math, io, urllib.request, sys
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor
UA={'User-Agent':'blog-viaje-vietnam/1.0 (personal)'}
ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/'
LAYERS={'sat':[ESRI+'World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        'hibrido':[ESRI+'World_Imagery/MapServer/tile/{z}/{y}/{x}',ESRI+'Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',ESRI+'Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
        'calles':['https://tile.openstreetmap.org/{z}/{x}/{y}.png']}
def px(lon,lat,z):
    n=256*2**z; x=(lon+180)/360*n
    y=(1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n
    return x,y
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=20) as r: return Image.open(io.BytesIO(r.read())).convert('RGBA')
    except Exception as e: print('tile fail',url,e,file=sys.stderr); return None
def render(segs,estilo='hibrido',W=1600,H=1000,pad=140,titulo='',leyenda=(),atrib=''):
    pts=[p for s,_ in segs for p in s]
    for z in range(18,1,-1):
        xs,ys=zip(*[px(lo,la,z) for lo,la in pts])
        if max(xs)-min(xs)<=W-2*pad and max(ys)-min(ys)<=H-2*pad: break
    cx,cy=(max(xs)+min(xs))/2,(max(ys)+min(ys))/2; x0,y0=cx-W/2,cy-H/2
    img=Image.new('RGBA',(W,H),(200,200,200,255))
    tiles=[(tx,ty) for tx in range(int(x0//256),int((x0+W)//256)+1) for ty in range(int(y0//256),int((y0+H)//256)+1)]
    for tpl in LAYERS[estilo]:
        with ThreadPoolExecutor(8) as ex: res=list(ex.map(lambda t:get(tpl.format(z=z,x=t[0],y=t[1])),tiles))
        for (tx,ty),t in zip(tiles,res):
            if t: img.alpha_composite(t,(int(tx*256-x0),int(ty*256-y0)))
    S=2; big=Image.new('RGBA',(W*S,H*S),(0,0,0,0)); d=ImageDraw.Draw(big)
    for seg,col in segs:
        P=[((px(lo,la,z)[0]-x0)*S,(px(lo,la,z)[1]-y0)*S) for lo,la in seg]
        d.line(P,fill='white',width=15*S,joint='curve'); d.line(P,fill=col,width=9*S,joint='curve')
    for (lo,la),col in ((segs[0][0][0],'#2A9D3F'),(segs[-1][0][-1],'#222222')):
        x,y=[(v-o)*S for v,o in zip(px(lo,la,z),(x0,y0))]
        d.ellipse((x-17*S,y-17*S,x+17*S,y+17*S),fill='white'); d.ellipse((x-11*S,y-11*S,x+11*S,y+11*S),fill=col)
    img.alpha_composite(big.resize((W,H),Image.LANCZOS))
    F='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'; FB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    fb,f,s=ImageFont.truetype(FB,44),ImageFont.truetype(F,32),ImageFont.truetype(F,22)
    ov=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(ov)
    bw=max(d.textlength(titulo,font=fb),*[d.textlength(t,font=f)+80 for t,_ in leyenda])+70
    d.rounded_rectangle((40,40,40+bw,40+90+60*len(leyenda)),24,fill=(255,255,255,235))
    d.text((70,62),titulo,font=fb,fill='#222')
    for i,(t,c) in enumerate(leyenda):
        y=150+60*i; d.line((72,y,132,y),fill=c,width=10); d.text((150,y-20),t,font=f,fill='#333')
    w=d.textlength(atrib,font=s); d.rectangle((W-w-24,H-36,W,H),fill=(255,255,255,220)); d.text((W-w-12,H-32),atrib,font=s,fill='#555')
    img.alpha_composite(ov); return img.convert('RGB')
def km(p):
    return sum(math.hypot((c-a)*math.cos(math.radians(b))*111.32,(e-b)*110.57) for (a,b),(c,e) in zip(p,p[1:]))
