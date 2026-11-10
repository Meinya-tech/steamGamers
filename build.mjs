import fs from 'node:fs';
import path from 'node:path';
const types={'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.txt':'text/plain; charset=utf-8','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'};
const assets={};for(const name of fs.readdirSync('dist')){if(fs.statSync(path.join('dist',name)).isFile()&&types[path.extname(name)])assets['/'+name]={type:types[path.extname(name)],body:fs.readFileSync(path.join('dist',name)).toString('base64')};}
fs.mkdirSync('dist/server',{recursive:true});fs.mkdirSync('dist/.openai',{recursive:true});
fs.writeFileSync('dist/server/index.js','const ASSETS='+JSON.stringify(assets)+';\n'+fs.readFileSync('worker/index.js','utf8'));
fs.copyFileSync('.openai/hosting.json','dist/.openai/hosting.json');
console.log('Built Worker with '+Object.keys(assets).length+' public assets.');
