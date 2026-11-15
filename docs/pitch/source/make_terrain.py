"""Render measured DEM arrays copied from the pinned TwinSite evidence snapshot."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
BASE=Path(__file__).resolve().parents[1]
colors=['#151311','#554032','#9d6240','#d88b53','#f3ebdf']
cmap=LinearSegmentedColormap.from_list('copper_terrain',colors)
for body in ['earth','mars']:
 d=json.loads((BASE/'source'/f'{body}_dem.json').read_text());g=d['grid']
 z=np.array(g['values'],dtype=float).reshape(g['nrows'],g['ncols'])
 # All native sample heights remain unchanged. Raster interpolation only affects display.
 fig,ax=plt.subplots(figsize=(7,6.4),dpi=200,facecolor='#0C0B0A');ax.set_facecolor('#0C0B0A')
 ext=[g['lon0'],g['lon0']+g['dlon']*(g['ncols']-1),g['lat0']-g['dlat']*(g['nrows']-1),g['lat0']]
 im=ax.imshow(z,extent=ext,cmap=cmap,interpolation='nearest',aspect='auto')
 ax.set_xlabel('East longitude (°)',color='#A59B90');ax.set_ylabel('Latitude (°)',color='#A59B90');ax.tick_params(colors='#A59B90',labelsize=9)
 for sp in ax.spines.values():sp.set_color('#50453b')
 cb=fig.colorbar(im,ax=ax,pad=.03,shrink=.8);cb.set_label('Elevation (m), '+d['vertical_datum'],color='#A59B90');cb.ax.tick_params(colors='#A59B90',labelsize=9);cb.outline.set_visible(False)
 fig.tight_layout(pad=1.1);fig.savefig(BASE/'assets'/f'terrain-{body}-plot.png',facecolor=fig.get_facecolor());plt.close(fig)
