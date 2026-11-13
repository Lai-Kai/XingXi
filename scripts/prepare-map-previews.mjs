import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const tools=process.env.XINGXI_GLTF_TOOLS;
if(!tools)throw new Error('Set XINGXI_GLTF_TOOLS to an isolated directory with the documented pinned dependencies.');
const require=createRequire(path.resolve(tools,'package.json'));
const {NodeIO}=require('@gltf-transform/core');
const {ALL_EXTENSIONS}=require('@gltf-transform/extensions');
const {dedup,prune,quantize,simplify,textureCompress,weld}=require('@gltf-transform/functions');
const {MeshoptSimplifier}=require('meshoptimizer');
const sharp=require('sharp');

const sourceRoot=path.resolve(process.argv[2]??'frontend/public/models');
const base=path.resolve(process.argv[3]??'.cache/map-preview-build');
await fs.mkdir(base,{recursive:true});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS);
sharp.concurrency(4);
await MeshoptSimplifier.ready;
const rows=[];
for(const name of (await fs.readdir(sourceRoot)).sort()) {
 const dir=path.join(sourceRoot,name,'v1');
 const files=await fs.readdir(dir).catch(()=>[]);
 const originalName=files.find(f=>/^model\.[a-f0-9]{12}\.glb$/.test(f));
 if(!originalName)continue;
 const file=path.join(dir,originalName),before=await fs.readFile(file),originalHash=hash(before);
 const started=Date.now(),doc=await io.readBinary(before);
 const triangleCount=()=>doc.getRoot().listMeshes().reduce((sum,m)=>sum+m.listPrimitives().reduce((n,p)=>n+(p.getIndices()?.getCount()??p.getAttribute('POSITION').getCount())/3,0),0);
 const originalTriangles=triangleCount();
 await doc.transform(dedup(),weld(),simplify({simplifier:MeshoptSimplifier,ratio:Math.min(1,40000/originalTriangles),error:0.05}),prune(),textureCompress({encoder:sharp,targetFormat:'webp',resize:[768,768],quality:85,effort:4}),quantize({quantizePosition:14,quantizeNormal:10,quantizeTexcoord:12}));
 const result=Buffer.from(await io.writeBinary(doc)),sha256=hash(result),filename=`preview.${sha256.slice(0,12)}.glb`;
 const destination=path.join(base,'previews',name,'v1');await fs.mkdir(destination,{recursive:true});await fs.writeFile(path.join(destination,filename),result);
 if(hash(await fs.readFile(file))!==originalHash)throw new Error(`Original changed: ${name}`);
 const row={name,src:`/models/${name}/v1/${originalName}`,originalSize:before.length,originalSha256:originalHash,previewSrc:`/models/${name}/v1/${filename}`,previewSize:result.length,previewSha256:sha256,originalTriangles,previewTriangles:triangleCount(),textures:doc.getRoot().listTextures().map(t=>t.getSize()),seconds:(Date.now()-started)/1000};
 rows.push(row);await fs.writeFile(path.join(base,'previews-manifest.json'),JSON.stringify({version:1,models:rows},null,2));console.log(JSON.stringify(row));
}
if(rows.length!==7)throw new Error('Expected the seven supplied map models');
