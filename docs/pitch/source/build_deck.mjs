import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import {fileURLToPath,pathToFileURL} from 'node:url';
const BASE=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const BUILD=path.join(BASE,'.build');const ASSETS=path.join(BASE,'assets');
const SKILL='/Users/macbook/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations';
const PYTHON='/Users/macbook/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
await fs.mkdir(BUILD,{recursive:true});await fs.mkdir(path.join(BASE,'rendered'),{recursive:true});
const C={bg:'#0C0B0A',surface:'#201C19',ivory:'#F3EBDF',orange:'#D8753D',muted:'#A59B90',rule:'#493E35',soft:'#D0C4B4'};
const p=Presentation.create({slideSize:{width:1280,height:720}});p.theme.defaultFont='Arial';
p.theme.colorScheme={name:'TwinSite Copper',themeColors:{accent1:C.orange,accent2:C.ivory,accent3:C.muted,accent4:'#79513A',accent5:'#667064',accent6:'#A77B5D',bg1:C.bg,bg2:C.surface,tx1:C.ivory,tx2:C.muted,dk1:C.bg,dk2:C.surface,lt1:C.ivory,lt2:C.soft,hlink:C.orange,folHlink:C.muted}};
const slides=[];let script=[];
function tx(s,text,x,y,w,h,size=24,color=C.ivory,bold=false,font='Arial',align='left'){
 const q=s.shapes.add({geometry:'textbox',name:text.slice(0,70),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=text;q.text.style={fontSize:size,typeface:font,color,bold,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};return q;
}
function rect(s,x,y,w,h,fill,line='none',lw=0){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:lw,style:'solid'}})}
function rule(s,x,y,w,color=C.rule){rect(s,x,y,w,1,color)}
function line(s,x,y,w,h=0,color=C.orange){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:color,width:1.5,style:'solid'}})}
async function pic(s,name,x,y,w,h,fit='cover'){
 const b=await fs.readFile(path.join(ASSETS,name));return s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:name.endsWith('.png')?'image/png':'image/jpeg',alt:name.replaceAll('-',' '),position:{left:x,top:y,width:w,height:h},fit});
}
function textrow(s,title,body,x,y,w=450){tx(s,title,x,y,w,34,26,C.ivory,true);tx(s,body,x,y+43,w,72,22,C.muted);}
function base(n,title,kicker='TWINSITE',subtitle=''){
 const s=p.slides.add();s.background.fill=C.bg;slides.push(s);
 tx(s,kicker,64,36,1080,24,14,C.orange,true);if(title)tx(s,title,64,78,1150,78,48,C.ivory,false,'Georgia');
 if(subtitle)tx(s,subtitle,64,158,1140,54,23,C.muted);
 rule(s,64,675,1152);tx(s,'TWINSITE   /   NASA SPACE APPS CHALLENGE 2026',64,688,900,18,11,C.muted);tx(s,String(n).padStart(2,'0'),1150,685,66,22,15,C.orange,false,'Arial','right');return s;
}
function notes(s,n,title,words,sources){s.speakerNotes.text=words+'\n\nSOURCES\n'+sources.join('\n');script.push({n,title,words,sources});}
function footer(s,txt,y=638){tx(s,txt,64,y,1150,30,15,C.muted);}
const local='Implementation and live UI snapshot: 15 November 2026. Screenshots captured from the local application on port 5180.';
const marsurl='https://science.nasa.gov/photojournal/curiosity-looks-downslope-from-the-sulfate-unit/';
const earthurl='https://science.nasa.gov/earth/earth-observatory/anti-atlas-mountains-morocco-2178/';
const moonurl='https://science.nasa.gov/moon/image-galleries/moonscapes/';
const srcEvidence='source/missions_run-d7b84f7f350ac24de32b069e_evidence.json';
const srcTrace='source/missions_run-d7b84f7f350ac24de32b069e_agents.json';
// 01: panoramic cover with an orbital inset.
{
 const s=base(1,'','NASA SPACE APPS CHALLENGE 2026');
 await pic(s,'mars-mount-sharp.jpg',0,397,1280,275);rect(s,0,397,1280,275,'#0C0B0A/18');
 await pic(s,'earth-anti-atlas-full.jpg',910,55,306,306);rect(s,910,55,306,306,'#0C0B0A/20');
 tx(s,'TwinSite',62,106,800,145,112,C.ivory,false,'Georgia');
 tx(s,'AI-assisted Earth analog discovery\nfor Moon and Mars missions',68,267,760,92,32,C.soft);
 tx(s,'EARTH / ANTI-ATLAS',928,326,270,23,13,C.ivory,true);
 tx(s,'MARS / GALE CRATER',67,600,600,25,14,C.ivory,true);
 notes(s,1,'TwinSite','Before a mission reaches the Moon or Mars, teams need places on Earth where they can test an idea. TwinSite helps investigate those analog environments using scientific evidence, AI interpretation, and calculations that remain reproducible. This is our working prototype for the NASA Space Apps Challenge.',[local,earthurl+' — NASA/JSC astronaut photograph, Anti-Atlas context, not the Zagora AOI.',marsurl+' — NASA/JPL-Caltech/MSSS. Color adjusted by the source to Earth-like lighting. Context image, not a terrain measurement.']);
}
// 02
{
 const s=base(2,'The analog selection problem','01 / THE PROBLEM');
 await pic(s,'moon-tycho.png',782,182,434,436);rect(s,782,182,434,436,'#0C0B0A/15');
 textrow(s,'Fragmented evidence','Terrain, climate and imagery arrive in different products and formats.',64,205,620);
 rule(s,64,327,620);textrow(s,'Incompatible comparisons','Resolution, study area and physical meaning can change the conclusion.',64,351,620);
 rule(s,64,472,620);textrow(s,'Mission constraints','Scientific resemblance still leaves access, cost and operational suitability unresolved.',64,497,620);
 footer(s,'LRO image of Tycho’s central peak. NASA/GSFC/Arizona State University.');
 notes(s,2,'The analog selection problem','The difficult part is deciding what resemblance means for a mission. A terrain map, a climate product and an image do not measure the same thing. Even two elevation models can use different scales and study areas. Teams also need practical constraints, such as field access and available time, before a scientific comparison can support a decision.',[local,'docs/release/SCIENTIFIC_REVIEW.md',moonurl]);
}
// 03
{
 const s=base(3,'Earth as a planetary laboratory','02 / THE OPPORTUNITY','A useful analog matches a mission-relevant process at a stated scale.');
 await pic(s,'earth-anti-atlas-full.jpg',64,228,550,320);await pic(s,'moon-tycho.png',652,228,264,320);await pic(s,'mars-mount-sharp.jpg',952,228,264,320);
 rect(s,64,467,550,81,'#0C0B0A/78');rect(s,652,467,264,81,'#0C0B0A/78');rect(s,952,467,264,81,'#0C0B0A/78');
 tx(s,'Earth',84,482,460,52,38,C.ivory,false,'Georgia');tx(s,'Moon',672,482,226,52,38,C.ivory,false,'Georgia');tx(s,'Mars',972,482,226,52,38,C.ivory,false,'Georgia');
 tx(s,'Terrain morphology',64,582,350,36,25,C.orange);tx(s,'Environmental context',458,582,350,36,25,C.orange);tx(s,'Operational constraints',852,582,365,36,25,C.orange);
 footer(s,'Earth analogs reproduce selected conditions. Gravity, vacuum and radiation remain physical limits.');
 notes(s,3,'Earth as a planetary laboratory','Earth provides accessible environments for investigating selected planetary processes. The comparison must follow the task: terrain morphology for mobility, environmental context for field operations, and constraints supplied by the mission team. No Earth site recreates lunar vacuum or Martian gravity. TwinSite makes those boundaries part of the investigation.',[earthurl,moonurl,marsurl,'backend/twinsite/science/registry.py','backend/twinsite/science/engine.py']);
}
// 04
{
 const s=base(4,'Introducing TwinSite','03 / THE PLATFORM');
 await pic(s,'workspace-focus.png',433,192,783,452,'contain');
 const items=['Acquire scientific data','Investigate with AI','Evaluate deterministically','Compare candidate sites','Inspect evidence and reports'];
 items.forEach((a,i)=>{tx(s,String(i+1).padStart(2,'0'),64,220+i*78,42,32,20,C.orange);tx(s,a,119,215+i*78,285,62,24);});
 notes(s,4,'Introducing TwinSite','TwinSite brings the investigation into one workspace. Users define a target and their mission priorities, inspect source evidence, and run an analysis. AI helps interpret that evidence. Deterministic software owns the numerical result. The interface connects the resulting assessment with its data, execution history, portfolio outcome and scientific report.',[local,'frontend/src/pages/Workspace.tsx','backend/twinsite/jobs/worker.py']);
}
// 05 editable process diagram
{
 const s=base(5,'How TwinSite works','04 / SYSTEM ARCHITECTURE');
 const xs=[64,357,650,943],ws=[245,245,245,273];
 const names=['Mission objectives','Scientific data gateway','Preparation + QA','Deterministic engine'];
 const desc=['Targets, weights,\nconstraints','Pinned source assets\nand observations','Units, masks, scale\nand quality flags','Features, scores,\neligibility, portfolios'];
 xs.forEach((x,i)=>{rect(s,x,210,ws[i],130,C.surface,C.rule,1);tx(s,names[i],x+18,230,ws[i]-36,52,23,C.ivory,true);tx(s,desc[i],x+18,282,ws[i]-36,51,19,C.muted);if(i<3)line(s,x+ws[i],274,xs[i+1]-x-ws[i]);});
 line(s,1060,340,0,48);line(s,470,388,590);line(s,470,388,0,42);line(s,1060,388,0,42);
 rect(s,64,430,595,130,C.surface,C.orange,1);tx(s,'AI investigation and interpretation',84,450,555,34,25,C.orange,true);tx(s,'Evidence-cited findings, labeled scenarios, synthesis\nand an independent-provider review',84,496,545,56,22);
 rect(s,730,430,486,130,C.surface,C.rule,1);tx(s,'Review, results and reports',750,450,446,34,25,C.ivory,true);tx(s,'Numeric checks and release gate\nNamed scientific review remains required',750,496,446,56,22,C.muted);
 line(s,659,495,71);tx(s,'Simple Analysis fallback preserves the deterministic result when AI is unavailable.',64,598,1152,38,24,C.orange);
 notes(s,5,'How TwinSite works','The pipeline starts with mission objectives and pinned scientific sources. Preparation and quality checks establish whether values are usable. The deterministic engine then calculates features, scores and portfolio eligibility. AI interprets the evidence and proposes explicit scenarios that the engine can re-score. Review checks the claims and the release gate. If AI is unavailable, Simple Analysis preserves the computed result.',['backend/twinsite/ai/agents.py','backend/twinsite/jobs/worker.py','backend/twinsite/science/engine.py','backend/twinsite/jobs/measured.py']);
}
// 06 data source ledger (native table)
{
 const s=base(6,'Scientific data, with explicit roles','05 / CONNECTED SOURCES');
 const rows=[['SOURCE','EVIDENCE IN THIS BUILD','USE'],['SRTMGL1 + MOLA','Earth and Mars terrain','Measured comparison'],['LOLA LDEM_64 + Diviner','Lunar terrain and surface temperature','Published lunar pair*'],['NASA POWER','Earth climatology model products','Environmental context'],['NASA GIBS / Trek','Earth and planetary imagery','Visualization only'],['MODIS MOD11A2 via CMR','Catalog metadata','Discovery only']];
 const t=s.tables.add({rows:rows.length,columns:3,left:64,top:195,width:1152,height:342,columnWidths:[340,468,344],values:rows});
 t.borders.assign({fill:C.rule,width:1,style:'solid'});
 for(let r=0;r<rows.length;r++)for(let c=0;c<3;c++){let q=t.getCell(r,c);q.fill=r===0?C.surface:C.bg;q.text.style={fontSize:r===0?17:23,typeface:'Arial',color:r===0?C.orange:C.ivory,bold:r===0,insets:10};}
 tx(s,'*Lunar evidence is implemented and visible. Independent scientific validation is pending.',64,561,1152,55,22,C.muted);
 footer(s,'Earth air temperature and lunar surface temperature describe different quantities.');
 notes(s,6,'Scientific data','The current build uses SRTM and MOLA for its Earth–Mars terrain comparison. Newer code and the live catalog also expose LOLA terrain and Diviner lunar temperatures. POWER supplies Earth climatology as model products. GIBS and Trek provide visual context. MODIS land-surface temperature is still discovery-only. These sources have different roles, and the deck does not imply complete coverage of every scientific domain.',[local,'source/data_catalog.json','source/moon_feature_pair.json','backend/twinsite/sources/','docs/release/COVERAGE_MATRIX.json']);
}
// 07 all 13 roles
{
 const s=base(7,'Thirteen roles, distinct responsibilities','06 / THE INTELLIGENCE SYSTEM');
 tx(s,'AI INTERPRETATION',64,162,350,30,16,C.orange,true);tx(s,'DETERMINISTIC CONTROL',365,162,420,30,16,C.ivory,true);tx(s,'7 AI roles / 6 deterministic roles',835,162,381,30,17,C.muted,false,'Arial','right');
 const groups=[['Investigate',[['A01','Source Curator',false],['A02','Visual Interpreter',true]]],['Prepare',[['A03','Cleaning Planner',false],['A04','Quality Reviewer',false]]],['Analyze',[['A05','Scenario Estimator',true],['A06','Domain Analyst',true],['A07','Synthesis Analyst',true]]],['Review',[['A08','Process Auditor',false],['A09','Evidence Reviewer',true],['A10','Portfolio Reviewer',false],['A11','Release Judge',false],['A12','Targeted Rechecker',true]]],['Explain',[['A13','Report Writer',true]]]];
 groups.forEach(([g,rs],i)=>{let x=64+i*233;rule(s,x,219,216,C.orange);tx(s,g,x,235,216,42,29,C.ivory,false,'Georgia');rs.forEach(([id,name,ai],j)=>{tx(s,id,x,305+j*54,40,28,15,ai?C.orange:C.muted,true);tx(s,name,x+42,302+j*54,176,45,20,ai?C.orange:C.ivory);});});
 tx(s,'Recorded measured mission: all 7 AI roles executed, including one cached real call.',64,608,1152,35,22,C.soft);
 notes(s,7,'Thirteen roles','The original thirteen roles are implemented as a division of responsibility. Seven use AI to interpret imagery, develop scenarios, analyze domains, synthesize, review, recheck and write. Six perform deterministic curation, preparation, quality checks, auditing and release control. In the recorded measured mission, all seven AI roles executed, including one cached response from an earlier real call. That is execution evidence, not scientific certification.',[srcTrace,'backend/twinsite/ai/agents.py','Recorded run: run-d7b84f7f350ac24de32b069e']);
}
// 08
{
 const s=base(8,'Scientific integrity is inspectable','07 / TRUST AND LIMITS');
 await pic(s,'report-focus.png',64,196,683,410,'contain');
 tx(s,'3',810,191,180,132,110,C.orange,false,'Georgia');tx(s,'numeric claims flagged',811,325,400,35,27,C.ivory,true);
 tx(s,'The deterministic cross-check found issues the AI reviewer had accepted.',811,377,390,103,25,C.soft);
 tx(s,'Sources and hashes travel with values. Missing evidence stays visible. AI cannot override release.',811,499,390,111,23,C.muted);
 footer(s,'Observed in the recorded AI mission. Flagged narrative remains advisory and requires human review.');
 notes(s,8,'Scientific integrity','A real run shows why this separation matters. The AI reviewer accepted claims that a deterministic numeric cross-check flagged. Three claims remained unsupported, including a confusion between analysis-block counts and square kilometers. The report still needs human scrutiny, but the numerical result and blocked release remain protected. Every source asset carries a hash, and missing data remains visible.',[srcTrace,srcEvidence,'backend/twinsite/ai/agents.py','docs/release/SCIENTIFIC_REVIEW.md']);
}
// 09 native scientific charts
{
 const s=base(9,'Zagora and Gale: measured terrain','08 / REAL EARTH–MARS EVIDENCE','Common analysis scale: 1,852.3 m. Reproduced summaries, not mission suitability.');
 const ev=JSON.parse(await fs.readFile(path.join(BASE,srcEvidence),'utf8'));
 const fspec=[['slope_deg','Mean slope','degrees','0.0000',2],['roughness_m','Mean roughness','metres','0.0000',60],['local_relief_m','Local relief','metres','0.000',1200]];
 fspec.forEach(([id,title,unit,fmt,max],i)=>{const x=64+i*390;const vals=['Earth','Mars'].map(b=>ev.observations.find(o=>o.body===b&&o.feature_id===id).value);
  tx(s,title,x,225,365,38,27,C.ivory,true);tx(s,unit,x,265,365,25,17,C.muted);
  const ch=s.charts.add('bar',{position:{left:x,top:302,width:365,height:230},categories:['Zagora','Gale'],series:[{name:title,values:vals,fill:C.orange,points:[{idx:0,fill:C.ivory},{idx:1,fill:C.orange}]}],hasLegend:false,barOptions:{direction:'column',grouping:'clustered',gapWidth:110},chartFill:C.bg,plotAreaFill:C.bg,chartLine:{fill:'none',width:0},xAxis:{visible:true,textStyle:{fontSize:18,typeface:'Arial',fill:C.soft},line:{fill:C.rule,width:1},majorGridlines:null},yAxis:{visible:true,min:0,max,textStyle:{fontSize:15,typeface:'Arial',fill:C.muted},majorGridlines:{fill:C.rule,width:.5},line:{fill:'none',width:0}},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:fmt,textStyle:{typeface:'Arial',fontSize:23,fill:C.ivory}}});
 });
 rule(s,64,560,1152,C.orange);tx(s,'3.33×',64,580,190,58,44,C.orange,false,'Georgia');tx(s,'Study-area mismatch blocks direct equivalence.',270,578,930,35,27,C.ivory,true);tx(s,'Earth ≈ 28.8 × 33.4 km. Mars ≈ 17.7 × 17.8 km. Relief depends on extent.',270,620,930,30,21,C.muted);
 notes(s,9,'Measured terrain','Here are the actual Zagora and Gale terrain summaries, reproduced from cached source bytes at a common 1,852.3-metre analysis scale. The values differ in slope, roughness and relief. But equal analysis scale is not enough: the Earth study area is about 3.33 times larger by analysis-block count. Relief depends on extent, and distributions use different sample sizes. TwinSite therefore blocks a claim of direct equivalence or mission suitability.',[srcEvidence,'source/g2_feature_pair.json','docs/release/SCIENTIFIC_REVIEW.md','.build/provenance-check.json','SRTMGL1 DOI: https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003','MOLA: https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/']);
}
// 10
{
 const s=base(10,'Explore the evidence behind a comparison','09 / DATA EXPLORER');
 await pic(s,'catalog-focus.png',64,199,436,245,'contain');
 tx(s,'Curated datasets',64,472,419,38,29,C.ivory,true);tx(s,'Source, units, time support\nand quality remain visible.',64,523,410,77,25,C.muted);
 await pic(s,'comparison-focus.png',535,193,681,456,'contain');
 notes(s,10,'Explore and compare','Researchers can open the catalog and compare actual records side by side. The interface exposes units, source products, quality flags and distributions. It also explains when study-area differences limit interpretation. The current application includes Earth, Moon and Mars map views, while the data comparison remains grounded in the available observations.',[local,'frontend/src/pages/DataCatalog.tsx','frontend/src/pages/DatasetDetail.tsx','Screenshots: data-catalog.jpg, comparison.jpg']);
}
// 11
{
 const s=base(11,'Mission planning includes infeasible outcomes','10 / PORTFOLIO OPTIMIZATION');
 tx(s,'0',64,190,220,180,150,C.orange,false,'Georgia');tx(s,'feasible portfolios',67,386,390,45,31,C.ivory,true);tx(s,'Recorded Zagora–Gale preset',68,440,386,55,23,C.muted);
 await pic(s,'portfolio-focus.png',494,215,722,231,'contain');
 const stages=[['Candidate eligibility','Evidence coverage and access'],['Combination search','Complementarity and redundancy'],['Hard constraints','Site count, budget and duration']];
 stages.forEach(([a,b],i)=>{let x=64+390*i;rule(s,x,530,358);tx(s,a,x,550,358,38,25,C.ivory,true);tx(s,b,x,597,358,55,22,C.muted);});
 notes(s,11,'Mission planning and portfolios','The optimizer can enumerate combinations, reward complementary evidence and penalize redundancy while applying hard constraints. Its engineering behavior is covered by tests. In this measured preset, unknown access makes the only Earth candidate ineligible, and no feasible portfolio remains. A useful scientific tool must be able to return that outcome. Demonstrating complementary real-world portfolios needs additional measured sites and operational inputs.',['backend/twinsite/portfolios/selection.py','backend/tests/science/test_engine.py',srcEvidence,local]);
}
// 12
{
 const s=base(12,'Two modes, one scientific calculation','11 / RESILIENT ANALYSIS');
 rule(s,64,208,548,C.orange);rule(s,668,208,548,C.ivory);
 tx(s,'AI-Powered Analysis',64,236,550,51,36,C.orange,false,'Georgia');tx(s,'Simple Analysis',668,236,548,51,36,C.ivory,false,'Georgia');
 tx(s,'Investigates and interprets evidence\nProposes labeled scenarios\nSynthesizes and reviews claims\nWrites an advisory narrative',64,315,535,204,27,C.soft);
 tx(s,'Runs without AI access\nPreserves reproducible calculations\nApplies the same eligibility checks\nProduces a deterministic report',668,315,535,204,27,C.soft);
 rect(s,64,563,1152,74,C.surface);tx(s,'Measurements, scores, portfolios and release decisions remain deterministic.',84,584,1112,38,26,C.ivory,true);
 notes(s,12,'AI-Powered and Simple Analysis','AI-Powered Analysis adds interpretation and evidence-cited narrative. Simple Analysis provides the same deterministic scientific calculations without AI access. If a provider is unavailable, the system records the reason and falls back. This makes the core workflow usable under quota or connectivity constraints, while keeping the scientific result separate from the reliability of a language-model response.',['backend/twinsite/ai/agents.py','backend/twinsite/ai/router.py','backend/twinsite/jobs/worker.py']);
}
// 13
{
 const s=base(13,'A foundation for mission-support research','12 / IMPACT AND NEXT STEPS');
 await pic(s,'mars-mount-sharp.jpg',0,430,1280,240);rect(s,0,430,1280,240,'#0C0B0A/55');
 textrow(s,'Research teams','Compare evidence and identify where field measurements are still needed.',64,205,530);
 textrow(s,'Mission and robotics engineers','Explore terrain priorities and inspect the assumptions behind a candidate.',668,205,548);
 tx(s,'NEXT',64,468,130,30,17,C.orange,true);tx(s,'Matched study areas. More measured sites.\nIndependent review. Field validation.',64,514,1090,100,36,C.ivory,false,'Georgia');
 footer(s,'Potential uses also include scientific education. No mission adoption or field validation is claimed.');
 notes(s,13,'Impact and future potential','The potential value is a more inspectable starting point for planetary scientists, analog field teams and mission or robotics engineers. Educators can also use it to show how source evidence becomes an assessment. The next milestones are concrete: matched study areas, more measured Earth sites, operational data, named independent review and field validation. Those steps would strengthen the prototype into a more useful research platform.',['docs/release/SCIENTIFIC_REVIEW.md','backend/twinsite/processing/moon_pair.py',marsurl]);
}
// 14
{
 const s=base(14,'','LIVE DEMO');
 tx(s,'Better analog choices\nbegin with traceable evidence',64,94,1140,144,53,C.ivory,false,'Georgia');
 await pic(s,'landing-focus.png',64,284,664,332,'contain');
 tx(s,'TwinSite',798,313,420,84,57,C.orange,false,'Georgia');tx(s,'Define a mission.\nInspect the measurements.\nFollow the evidence.',798,423,400,139,29,C.ivory);
 tx(s,'Local demonstration available',798,588,408,35,22,C.muted);
 notes(s,14,'Closing and live demo','TwinSite connects planetary analog discovery with evidence that people can inspect. The prototype already links sources, deterministic computation, AI investigation and transparent limitations. We can now show the local application: define a mission, inspect the measured comparison, and follow the evidence into its report. Better analog choices begin with traceable evidence.',[local,'No public deployment is claimed. Local demonstration runs on port 5180.']);
}
// 15 appendix validation
{
 const s=base(15,'Implementation and validation boundaries','APPENDIX A / STATUS SNAPSHOT');
 const ys=[203,309,415,521];const heads=['Observed in the live application','Reproduced from cached source bytes','Implemented, with validation limits','Still required for scientific release'];
 const body=['Workspace, Data Explorer, comparison, reports, real agent records and blocked portfolio outcome.','Six Zagora–Gale terrain summaries. Offline provenance recomputation passes.','Lunar LOLA / Diviner pair and terrain discovery adapters. Seven connector tests pass.','Matched Mars study area, independent reviewer, mission parameters, field access and more candidate sites.'];
 heads.forEach((a,i)=>{rule(s,64,ys[i]-14,1152);tx(s,a,64,ys[i],465,66,27,i===3?C.orange:C.ivory,true);tx(s,body[i],563,ys[i],653,78,24,C.muted);});
 notes(s,15,'Status snapshot','Optional technical discussion. The automated verification summary records seventeen passing automated suites and a separate blocked browser-smoke item, not a blanket all-green result. This presentation adds focused visual inspection and offline provenance recomputation. The lunar connectors pass seven current unit tests, but this does not independently validate their science. Recorded AI claims retain known limitations.',[local,'source/verification_summary.json','.build/provenance-check.json','.build/planetary-tests.log','docs/release/SCIENTIFIC_REVIEW.md']);
}
// 16 appendix method and terrain
{
 const s=base(16,'Terrain methods and uncertainty','APPENDIX B / SCIENTIFIC METHOD');
 await pic(s,'earth-grid-focus.png',64,202,422,385,'contain');
 tx(s,'Slope',545,206,270,36,27,C.orange,true);tx(s,'Mean Horn slope on the block-mean DEM',545,249,650,54,25,C.ivory);
 tx(s,'Roughness',545,325,270,36,27,C.orange,true);tx(s,'Mean 3 × 3 population standard deviation',545,368,650,54,25,C.ivory);
 tx(s,'Local relief',545,444,270,36,27,C.orange,true);tx(s,'Maximum minus minimum block-mean elevation',545,487,650,54,25,C.ivory);
 tx(s,'Spatial p10–p90 describes variability. Instrument error is not propagated.',64,607,1152,38,25,C.soft);
 notes(s,16,'Terrain methods','The terrain screenshot is the real cleaned SRTM display grid, not the analysis grid used for scoring. Slope uses Horn gradients on block means. Roughness is the mean local three-by-three population standard deviation. Relief is the range over the study area. Cross-body absolute elevation is excluded because the vertical datums differ. MOLA retains interpolated cells. About 25.7 percent of native cells have shots, while 74.1 percent of analysis blocks contain at least one shot.',['backend/twinsite/processing/terrain.py','tests/acceptance/terrain_reference.py','source/g2_feature_pair.json',srcEvidence,'docs/release/SCIENTIFIC_REVIEW.md']);
}
// 17 appendix lunar
{
 const s=base(17,'Lunar evidence extends the prototype','APPENDIX C / CURRENT LUNAR WORK','Zagora–Taurus–Littrow pair. Terrain at 1,895.3 m. Scientific review pending.');
 await pic(s,'moon-tycho.png',64,220,420,363);rect(s,64,220,420,363,'#0C0B0A/18');tx(s,'LRO / TYCHO',83,542,350,25,14,C.ivory,true);
 const rows=[['FEATURE','ZAGORA','TAURUS–LITTROW'],['Mean slope (°)','0.5847','6.9852'],['Mean roughness (m)','18.7893','206.5547'],['Local relief (m)','317.463','2255.156']];
 const t=s.tables.add({rows:4,columns:3,left:525,top:232,width:691,height:245,columnWidths:[296,161,234],values:rows});t.borders.assign({fill:C.rule,width:1,style:'solid'});
 for(let r=0;r<4;r++)for(let c=0;c<3;c++){let q=t.getCell(r,c);q.fill=r===0?C.surface:C.bg;q.text.style={fontSize:r===0?16:23,typeface:'Arial',color:r===0?C.orange:C.ivory,bold:r===0,insets:10};}
 tx(s,'Diviner adds lunar thermal context.\nEarth lacks matched surface-temperature evidence,\nso thermal values do not enter this comparison.',525,510,691,111,24,C.muted);
 footer(s,'Lunar photograph provides context only. It depicts Tycho, not the Taurus–Littrow study area.');
 notes(s,17,'Current lunar work','The live catalog and published artifact include a newer lunar pair. These are the published terrain values, at a different analysis scale from the Mars pair, so the Earth values also differ. The implementation describes approximately matched metric areas, within its extent tolerance. Diviner temperatures are lunar context at a coarser scale. Independent numeric and scientific review remains pending. The Tycho photograph is context and does not depict the analyzed site.',['source/moon_feature_pair.json','backend/twinsite/processing/moon_pair.py','backend/twinsite/sources/lola.py','backend/twinsite/sources/diviner.py',moonurl]);
}
// 18 source references
{
 const s=base(18,'Evidence and visual references','APPENDIX D / REFERENCE GUIDE');
 const entries=[['Measured Earth–Mars case','SRTMGL1 v003, N30W006. MOLA MEGDR meg128.\nPublished snapshot c1-g2-c3715a06a69fc4a0.'],['Recorded AI mission','run-d7b84f7f350ac24de32b069e\nSeven AI roles, six deterministic roles. Release BLOCK.'],['Scientific photographs','Earth: NASA/JSC. Moon: NASA/GSFC/Arizona State University.\nMars PIA26551: NASA/JPL-Caltech/MSSS.'],['Reproducible package','Source notes, speaker script, captured assets and generation code\naccompany the editable presentation.']];
 entries.forEach(([h,b],i)=>{let y=204+i*106;rule(s,64,y-14,1152);tx(s,h,64,y,420,56,27,C.ivory,true);tx(s,b,509,y,707,76,22,C.muted);});
 notes(s,18,'References','Full source URLs and attribution details are in SOURCES.md and in individual slide notes. Product screenshots are authentic captures of the local TwinSite application. Scientific photos are context images and are never used as evidence for the numeric comparisons. NASA Space Apps is event context and does not imply NASA endorsement.',[earthurl,moonurl,marsurl,'https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003','https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/','https://pds-geosciences.wustl.edu/missions/lro/']);
}
// Export editable draft and actual slide renders.
await fs.writeFile(path.join(BUILD,'presentation.json'),JSON.stringify(p.toProto()));
await (await PresentationFile.exportPptx(p)).save(path.join(BUILD,'candidate.pptx'));
for(let i=0;i<slides.length;i++){
 const png=await p.export({slide:slides[i],format:'png',scale:1.5});await fs.writeFile(path.join(BASE,'rendered',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log('Rendered slide '+(i+1));
}
await fs.writeFile(path.join(BASE,'speaker_script.md'),'# TwinSite speaker script\n\nMain pitch: approximately 5 minutes at a natural pace. Slides 15–18 are optional and excluded from the pitch timing.\n\n'+script.map(o=>`## ${String(o.n).padStart(2,'0')} — ${o.title}\n\n${o.words}\n`).join('\n'));
await fs.writeFile(path.join(BUILD,'notes-sources.json'),JSON.stringify(script,null,2));
const composites=[];for(let i=0;i<slides.length;i++)composites.push({input:await sharp(path.join(BASE,'rendered',`slide-${String(i+1).padStart(2,'0')}.png`)).resize(480,270).png().toBuffer(),left:(i%3)*496+16,top:Math.floor(i/3)*286+16});
await sharp({create:{width:1504,height:1732,channels:3,background:'#302923'}}).composite(composites).png().toFile(path.join(BASE,'contact_sheet.png'));
try{const pdf=await p.export({format:'pdf'});await fs.writeFile(path.join(BASE,'TwinSite_NASA_Space_Apps_2026.pdf'),new Uint8Array(await pdf.arrayBuffer()));console.log('PDF exported');}catch(e){console.log('PDF export unavailable: '+e.message);}
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const finalPath=path.join(BASE,'TwinSite_NASA_Space_Apps_2026.pptx');
const result=await finalizePresentation({workspaceDir:BASE,candidatePath:path.join(BUILD,'candidate.pptx'),finalPath,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:18,requiredNativeTableOwnerSlides:[6,17],requiredNativeChartOwnerSlides:[9],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial','Georgia']},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
console.log(JSON.stringify(result));
