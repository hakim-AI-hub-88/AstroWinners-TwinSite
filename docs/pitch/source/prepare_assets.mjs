import fs from 'node:fs/promises';import path from 'node:path';import sharp from 'sharp';
const base=path.resolve(path.dirname(new URL(import.meta.url).pathname),'..');const a=path.join(base,'assets');
const crops={
'workspace-focus':['workspace.jpg',170,105,1260,810],
'landing-focus':['landing.jpg',170,115,1260,720],
'comparison-focus':['comparison.jpg',170,85,1260,865],
'catalog-focus':['data-catalog.jpg',170,100,1260,650],
'analysis-gate':['analysis.jpg',170,175,1260,405],
'portfolio-focus':['portfolios.jpg',170,185,1260,330],
'report-focus':['report.jpg',170,170,1260,720],
'activity-focus':['activity.jpg',170,175,1260,800],
'provenance-focus':['source-qa.jpg',170,100,1260,800],
'earth-explorer-focus':['explorer-earth.jpg',170,100,1260,800],
'earth-grid-focus':['terrain-earth.jpg',175,365,650,580],
'agents-table':['agents-full.jpg',184,1135,1220,625],
};
for(const [name,[src,left,top,width,height]] of Object.entries(crops)){
 const meta=await sharp(path.join(a,src)).metadata();
 await sharp(path.join(a,src)).extract({left,top,width:Math.min(width,meta.width-left),height:Math.min(height,meta.height-top)}).png().toFile(path.join(a,name+'.png'));
}
console.log('Prepared '+Object.keys(crops).length+' authentic screenshot crops');
