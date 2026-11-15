"""Rebuild the code-native README illustrations. Python 3 + Pillow for the GIF.
Run from repository root: python docs/readme/build_assets.py
No network, application imports, or data mutations.

The cover (assets/twinsite-cover.jpg) is a supplied raster artwork and is not
generated here. This palette is tuned to match it: warm orange and gold on
near-black.
"""
from pathlib import Path
import random
from html import escape
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'assets'
OUT.mkdir(exist_ok=True)
INK, PAPER, ORANGE, GOLD = '#0e0a08', '#f6ead8', '#ff8f4a', '#f0c27a'
ROSE, SAND = '#e7a58c', '#d9c39a'
LINE, LINE2, PANEL, MUTED = '#3b2b21', '#5e4636', '#1a120d', '#cdbba6'

def text(x,y,s,size=20,color=PAPER,weight=400,spacing=0,anchor='start',style='normal'):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" font-style="{style}" letter-spacing="{spacing}" text-anchor="{anchor}">{escape(s)}</text>'

def svg(name,w,h,body,label):
    head=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}"><title>{escape(label)}</title>'
    (OUT / name).write_text(head+body+'</svg>\n')

def stars(w,h,n=130,seed=84):
    rng=random.Random(seed)
    return ''.join(f'<circle cx="{rng.uniform(0,w):.1f}" cy="{rng.uniform(0,h):.1f}" r="{rng.choice([.6,.8,1,1.4])}" fill="#f3e3cc" opacity="{rng.uniform(.12,.6):.2f}"/>' for _ in range(n))

def glow(uid,cx,cy,r,color=ORANGE,op=.22):
    return f'<defs><radialGradient id="{uid}" cx="{cx}" cy="{cy}" r="{r}"><stop stop-color="{color}" stop-opacity="{op}"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient></defs>'

# Navigation cards
cards=[('mission','01','EXPLORE','From a distant target','to an Earth test site.','SELECT / RANK / REFINE',ORANGE),
       ('data','02','ANALYZE','Every layer has','a role and a source.','DATA / APIS / PROVENANCE',GOLD),
       ('intelligence','03','DISCOVER','Computed by science.','Explained with context.','MODELS / TOOLS / LIMITS',ROSE),
       ('reports','04','PREPARE','Carry the analysis','beyond the dashboard.','REPORTS / DIAGRAMS / FILES',SAND)]
for i,(name,num,eyebrow,l1,l2,foot,col) in enumerate(cards):
    s=glow('g',"92%","8%","75%",col,.20)
    s+=f'<rect width="780" height="330" rx="18" fill="{INK}"/><rect width="780" height="330" rx="18" fill="url(#g)"/><rect x="1" y="1" width="778" height="328" rx="18" fill="none" stroke="{LINE2}"/>'+stars(780,330,40,seed=10+i)
    # planetary limb in the corner
    s+=f'<circle cx="760" cy="-40" r="170" fill="none" stroke="{col}" stroke-opacity=".55" stroke-width="1.5"/><circle cx="760" cy="-40" r="200" fill="none" stroke="{col}" stroke-opacity=".18" stroke-dasharray="2 9"/>'
    s+=f'<circle cx="38" cy="45" r="4" fill="{col}"/>'+text(54,51,num+'  ·  '+eyebrow,18,col,700,3)
    s+=text(38,134,l1,38,PAPER,600,-.5)+text(38,184,l2,38,PAPER,600,-.5)
    s+=f'<path d="M38 238 H742" stroke="{LINE}"/>'+text(38,287,foot,15,MUTED,500,2)+text(742,291,'→',30,col,400,0,'end')
    svg('nav-'+name+'.svg',780,330,s,eyebrow+'. '+l1+' '+l2)

# Section dividers
for n,title,subtitle,col in [('01','Flight plan','EXPLORE · THE EXPERIENCE',ORANGE),('02','Evidence, before inference','ANALYZE · THE SCIENCE',GOLD),
                             ('03','A system you can trace','DISCOVER · THE ARCHITECTURE',ROSE),('04','From analysis to field dossier','PREPARE · THE REPORT',SAND),
                             ('05','The next horizon','BEYOND · FUTURE AMBITIONS',ORANGE)]:
    s=glow('h',"100%","100%","60%",col,.28)
    s+=f'<rect width="1600" height="160" rx="16" fill="{INK}"/><rect width="1600" height="160" rx="16" fill="url(#h)"/>'+stars(1600,160,60,seed=int(n))
    s+=f'<path d="M1180 160 Q1420 40 1600 30" stroke="{col}" stroke-opacity=".7" stroke-width="2" fill="none"/><path d="M1150 160 Q1410 20 1600 6" stroke="{col}" stroke-opacity=".18" fill="none"/>'
    s+=f'<path d="M26 35 V125" stroke="{col}" stroke-width="3"/>'
    s+=text(57,104,n,60,col,300,-2)+text(165,53,subtitle,15,col,600,4)+text(163,113,title,44,PAPER,600,-1)
    svg('section-'+n+'.svg',1600,160,s,title)

# Mission telemetry strip: counts taken from the implementation audit (docs/implementation.md, docs/catalog.md).
stats=[('2','EARTH STUDY ZONES','Atacama · Merzouga',ORANGE),('4','PRESET TARGETS','+ custom globe regions',GOLD),
       ('2.3M','PLANETARY CELLS','Mars + Moon grids',ROSE),('11','API ROUTES','five Flask blueprints',SAND),
       ('9','ASSISTANT TOOLS','one Groq assistant',ORANGE),('5','REFERENCE SITES','published analogs',GOLD)]
s=glow('t',"50%","0%","80%",ORANGE,.16)+f'<rect width="1600" height="230" rx="18" fill="{INK}"/><rect width="1600" height="230" rx="18" fill="url(#t)"/><rect x="1" y="1" width="1598" height="228" rx="18" fill="none" stroke="{LINE2}"/>'+stars(1600,230,70,seed=7)
s+=text(800,42,'MISSION TELEMETRY  ·  WHAT SHIPS TODAY',14,MUTED,600,5,'middle')
cw=1600/6
for i,(num,label,sub,col) in enumerate(stats):
    cx=cw*i+cw/2
    if i: s+=f'<path d="M{cw*i:.0f} 72 V196" stroke="{LINE}"/>'
    s+=text(cx,128,num,62,col,300,-2,'middle')+text(cx,163,label,14,PAPER,700,2.5,'middle')+text(cx,188,sub,14,MUTED,400,0,'middle')
svg('telemetry.svg',1600,230,s,'What ships today: 2 Earth study zones, 4 preset targets plus custom regions, about 2.3 million Mars and Moon grid cells, 11 API routes, 9 assistant tools, 5 published reference sites.')

# System map
s=glow('a',"50%","45%","60%",ORANGE,.10)+f'<rect width="1600" height="640" rx="20" fill="{INK}"/><rect width="1600" height="640" rx="20" fill="url(#a)"/>'+stars(1600,640,80)
s+=text(55,55,'SYSTEM MAP',17,ORANGE,700,4)+text(55,98,'Three data roles. One shared analysis.',36,PAPER,600,-.8)
boxes=[(55,155,430,100,'01 / NORMALIZED','Harmonized CSV · 0–1 · score & rank',GOLD),(55,275,430,100,'02 / PHYSICAL','Harmonized CSV · K, m, ° · explain',ORANGE),(55,395,430,100,'03 / PROCESSED','Earth grid · ~1 km · filter & refine',ROSE),(610,245,400,170,'ANALYSIS SERVICE','Weights → scores → ranked regions',PAPER),(1130,155,415,100,'MISSION CONTROL','Globes · maps · comparison · charts',GOLD),(1130,275,415,100,'MISSION ASSISTANT','Groq + 9 tools · reads computed facts',ORANGE),(1130,395,415,100,'MISSION REPORT','Facts + PNG maps + print / PDF',ROSE)]
for x,y,w,h,t,sub,col in boxes:
    stroke=ORANGE if t=='ANALYSIS SERVICE' else LINE2
    s+=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{PANEL}" stroke="{stroke}"/>'+text(x+24,y+38,t,19,col,700,1.5)+text(x+24,y+73,sub,18,MUTED)
    if t=='ANALYSIS SERVICE': s+=text(x+24,y+115,'PCA + K-means alongside the score',17,GOLD)+text(x+24,y+143,'Reference sites checked afterward',17,MUTED)
for y in [205,325,445]:
    s+=f'<path d="M485 {y} H550 V330 H610" fill="none" stroke="#8a6a52"/><path d="M1010 330 H1070 V{y} H1130" fill="none" stroke="#8a6a52"/>'
s+=text(55,570,'SCORING IS DETERMINISTIC',16,ORANGE,700,3)+text(55,607,'AI narrates results; it does not set the similarity score. External map tiles are a display layer.',21,MUTED)
svg('architecture.svg',1600,640,s,'Normalized data scores; physical data explains; processed Earth data refines. Shared analysis feeds dashboard, assistant and report.')

# A restrained animated signal diagram; static companion supports reduced motion.
W,H=1280,180
font_path=Path('/System/Library/Fonts/Supplemental/Arial.ttf')
try:
    font=ImageFont.truetype(str(font_path),16); small=ImageFont.truetype(str(font_path),12)
except OSError:
    font=ImageFont.load_default(); small=font
frames=[]
for k in range(48):
    im=Image.new('RGB',(W,H),INK); d=ImageDraw.Draw(im)
    d.line((85,80,1190,80),fill=LINE2,width=1)
    for x,label,sub,col in [(110,'TARGET','MARS / MOON',ORANGE),(465,'ANALYZE','WEIGHTED FEATURES',GOLD),(820,'EARTH ANALOG','ATACAMA / MERZOUGA',ROSE),(1170,'EXPLAIN','FACTS / REPORT',SAND)]:
        d.ellipse((x-23,57,x+23,103),fill=PANEL,outline=col,width=1)
        d.ellipse((x-7,73,x+7,87),fill=col)
        d.text((x,125),label,font=font,fill=PAPER,anchor='mm'); d.text((x,152),sub,font=small,fill=MUTED,anchor='mm')
    for phase in [0,1/3,2/3]:
        x=110+1060*((k/48+phase)%1)
        for trail in range(16,0,-1):
            xx=x-trail*3
            if 110<xx<1170:d.ellipse((xx-2,78,xx+2,82),fill=tuple(int(a*(1-trail/20)) for a in (255,143,74)))
        d.ellipse((x-4,76,x+4,84),fill='#ffd2a8')
    frames.append(im)
frames[0].save(OUT/'signal-static.png',optimize=True)
palette=frames[0].quantize(colors=96)
quant=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
quant[0].save(OUT/'signal.gif',save_all=True,append_images=quant[1:],duration=80,loop=0,optimize=True,disposal=1)
print('Built README SVG illustrations and signal animation in', OUT)
