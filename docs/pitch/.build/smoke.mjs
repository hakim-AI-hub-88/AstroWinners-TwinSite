import fs from 'node:fs/promises';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const p=Presentation.create({slideSize:{width:1280,height:720}});const s=p.slides.add();s.background.fill='#0C0B0A';
let t=s.shapes.add({geometry:'textbox',position:{left:70,top:60,width:1000,height:100},fill:'none',line:{fill:'none',width:0}});t.text='TwinSite';t.text.style={fontSize:80,typeface:'Avenir Next',color:'#F3EBDF',insets:0};
await fs.writeFile('docs/pitch/.build/smoke.png',new Uint8Array(await (await p.export({slide:s,format:'png',scale:1})).arrayBuffer()));await (await PresentationFile.exportPptx(p)).save('docs/pitch/.build/smoke.pptx');
console.log('render/export OK');
