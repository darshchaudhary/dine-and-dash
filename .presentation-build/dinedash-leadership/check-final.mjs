import fs from 'node:fs/promises';
import { FileBlob, PresentationFile } from '@oai/artifact-tool';
const root='/Users/darshchaudhary/Documents/dining-hall-plater';
const p=await PresentationFile.importPptx(await FileBlob.load(`${root}/presentations/DineDash-Georgia-Tech-Dining.pptx`));
for (let i=0;i<p.slides.items.length;i++) {
  const image=await p.export({slide:p.slides.items[i],format:'png',scale:1});
  await fs.writeFile(`${root}/.presentation-build/dinedash-leadership/final-${i+1}.png`,new Uint8Array(await image.arrayBuffer()));
}
console.log(`Rendered ${p.slides.items.length} final slides`);
