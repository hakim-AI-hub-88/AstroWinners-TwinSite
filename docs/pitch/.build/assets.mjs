import fs from 'node:fs/promises';import sharp from 'sharp';
const dir='docs/pitch/assets';const files=(await fs.readdir(dir)).filter(x=>/\.jpg$/.test(x)&&!x.includes('full'));
let a=[];for(let i=0;i<files.length;i++){a.push({input:await sharp(dir+'/'+files[i]).resize(400,250,{fit:'contain',background:'#0C0B0A'}).toBuffer(),left:(i%4)*400,top:Math.floor(i/4)*250});}await sharp({create:{width:1600,height:Math.ceil(files.length/4)*250,channels:3,background:'#0C0B0A'}}).composite(a).png().toFile('docs/pitch/.build/screens-montage.png');console.log(files);
