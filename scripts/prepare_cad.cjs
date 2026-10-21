const fs=require('node:fs'),path=require('node:path');
const source=path.join(__dirname,'../node_modules/occt-import-js/dist'),target=path.join(__dirname,'../public/cad');fs.mkdirSync(target,{recursive:true});
for(const name of ['occt-import-js.js','occt-import-js.wasm','license.occt-import-js.txt','license.occt.txt'])fs.copyFileSync(path.join(source,name),path.join(target,name));
