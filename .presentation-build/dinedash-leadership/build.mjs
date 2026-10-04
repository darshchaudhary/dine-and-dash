import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
import { resolvePresentationFont, finalizePresentation } from '/Users/darshchaudhary/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations/container_tools/artifact_tool_utils.mjs';

const root = '/Users/darshchaudhary/Documents/dining-hall-plater';
const tmp = path.join(root, '.presentation-build/dinedash-leadership');
const skill = '/Users/darshchaudhary/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations';
const font = resolvePresentationFont();
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const c = { navy:'#051E39', paper:'#F6F4EE', ink:'#102B43', muted:'#506477', gold:'#C6A96B', teal:'#47796F', pale:'#B8C8D5' };
function text(s, content, x, y, w, h, size=30, color=c.ink, bold=false) {
  const t = s.shapes.add({ geometry:'textbox', name:content.slice(0,45), position:{left:x,top:y,width:w,height:h}, fill:'none', line:{fill:'none',width:0} });
  t.text = content;
  t.text.style = { typeface:font, fontSize:size, color, bold, autoFit:'none', insets:{left:0,right:0,top:0,bottom:0} };
  return t;
}
function slide(dark=false) {
  const s = p.slides.add(); s.background.fill = dark?c.navy:c.paper;
  return s;
}
function foot(s,n,dark=false) { text(s,`Dine&Dash     ${String(n).padStart(2,'0')}`,76,663,800,25,18,dark?c.pale:c.muted); }
function notes(s,t) { s.speakerNotes.textFrame.setText(t); }

let s=slide(true);
text(s,'THE STUDENT PROBLEM',76,65,1000,36,22,c.gold,true);
text(s,'Choosing a meal\ntakes more than\nreading a menu',76,149,1110,294,76,c.paper,true);
text(s,'Students must connect changing dining-hall options\nwith their personal goals and what they already ate.',80,480,1080,105,32,c.pale);
foot(s,1,true);
notes(s,'Opening problem framing, not a measured claim about Georgia Tech students. The prototype addresses the effort of translating published menus into portions and keeping a record of consumption. No student survey or adoption study has established the size of this problem. Invite Dining leadership to assess whether this matches student feedback.');

s=slide();
text(s,'THE SOLUTION',76,65,1000,36,22,c.teal,true);
text(s,'Dine&Dash',76,144,1120,106,84,c.navy,true);
text(s,'A personal meal planner\nfor campus dining',78,269,1040,130,48,c.ink);
text(s,'Students choose a hall, get a suggested plate,\nand track the meals they actually eat.',80,448,1040,99,32,c.muted);
text(s,'Current prototype: Brittain, North Ave and West Village',80,590,1110,40,23,c.teal);
foot(s,2);
notes(s,'Dine&Dash is a student-built prototype, not an official Georgia Tech Dining product or approved nutrition service. The code currently supports Brittain, North Ave, and West Village. It uses published Nutrislice menu data. Sources: backend/app/nutrislice.py, frontend/src/App.tsx, backend/app/recommendations.py.');

s=slide();
text(s,'A plate tailored to the current meal',76,65,1120,85,49,c.navy,true);
const rows=[
  ['01','Personal goals','Saved calorie goals, dietary preferences and allergy filters.'],
  ['02','Hall and service','Published menu items for the selected hall and current meal.'],
  ['03','Food and portions','A rule-based search compares combinations against nutrition targets.']
];
rows.forEach((r,i)=>{let y=214+i*126;text(s,r[0],78,y,80,55,42,c.teal);text(s,r[1],191,y,945,45,32,c.ink,true);text(s,r[2],191,y+49,1000,60,27,c.muted);});
foot(s,3);
notes(s,'The app uses a deterministic beam-search optimizer, not a trained AI model. It searches up to four items with several portion sizes and scores calorie fit, protein/fiber shortfalls, fat, sodium, and category variety. Current meal weights and the calorie cap are developer-selected heuristics that need dietitian review. Current diet/allergy filters have limitations and do not establish allergen safety or halal certification. Sources: backend/app/recommendations.py:36-131, backend/app/planning.py:34-40, backend/app/main.py:148-172.');

s=slide(true);
text(s,'Flexibility when plans change',76,65,1120,85,51,c.paper,true);
text(s,'Food unavailable?',78,224,505,61,38,c.gold,true);
text(s,'Mark an item unavailable.\nThe app rebuilds the plate\nwithout that food.',78,307,505,165,31,c.paper);
text(s,'Ate something else?',685,224,510,61,38,c.gold,true);
text(s,'Search the hall’s current menu,\nchoose portions and add\nwhat you actually ate.',685,307,510,165,31,c.paper);
text(s,'The app disables plate building when configured hall hours show it is closed.',78,560,1100,65,25,c.pale);
foot(s,4,true);
notes(s,'Alternatives retain saved diet/allergy filters and recalculate portions around the meal target. The app does not know real-time station inventory. Current-menu search uses the current hall/date/service and published nutrition. Configured regular opening hours may differ on holidays or exceptional closures. Sources: frontend/src/ExtraFoods.tsx, frontend/src/App.tsx, backend/app/planning.py:14-21, backend/app/meals.py, backend/app/recommendations.py:153-186.');

s=slide();
text(s,'A food journal that stays connected',76,65,1130,85,49,c.navy,true);
text(s,'Daily and weekly progress',78,215,1060,49,36,c.teal,true);
text(s,'The profile page shows logged meals and estimated calories.\nToday’s entries adjust the calorie budget for the next suggestion.',78,281,1120,104,30,c.ink);
text(s,'Forgotten meals',78,430,1060,49,36,c.teal,true);
text(s,'Choose breakfast, lunch or dinner, then a hall, date and time.\nSearch that service’s historical menu and update the original day.',78,496,1120,104,30,c.ink);
foot(s,5);
notes(s,'Registration/login associates goals and meal history with individual accounts. The user icon opens My progress. Logging remains explicit, not automatic. Historical menus may be unavailable; the backend rejects missing/demo historical data instead of substituting current foods. All journal date/time boundaries use America/New_York. Older meals change their original day/week, not today’s budget. Sources: frontend/src/MealHistory.tsx, frontend/src/PastMeal.tsx, backend/app/meals.py, backend/app/planning.py:24-40, AUTHENTICATION.md.');

s=slide(true);
text(s,'A pilot with Georgia Tech Dining',76,65,1120,90,50,c.paper,true);
text(s,'Proposed next step: a small, opt-in student pilot',78,174,1120,61,32,c.gold);
text(s,'Dining input',78,297,335,55,32,c.paper,true);
text(s,'Confirm menu and hours data. Review nutrition rules\nand allergy messaging with Dining’s nutrition team.',444,291,752,96,28,c.pale);
text(s,'Pilot evaluation',78,426,335,55,32,c.paper,true);
text(s,'Test ease of use, menu accuracy and whether students\nfind the suggestions useful before expanding.',444,420,752,96,28,c.pale);
text(s,'Nutrition values are estimates. Published menus cannot guarantee station stock or allergen safety.',78,580,1115,64,23,c.pale);
foot(s,6,true);
notes(s,'This slide proposes collaboration; it does not imply an existing partnership, committed pilot, or measured student outcomes. Ask whether Dining would be interested in a product demonstration and review of data accuracy and nutrition assumptions. Before wider deployment, address account recovery, email verification, privacy/consent, and operational support. Sources for current limitations: AUTHENTICATION.md and backend/app/recommendations.py.');

await fs.mkdir(tmp,{recursive:true});
const draft=path.join(tmp,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(draft);
for (let i=0;i<p.slides.items.length;i++) {
  const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(tmp,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
await finalizePresentation({
  workspaceDir:root,candidatePath:draft,finalPath:path.join(root,'presentations/DineDash-Georgia-Tech-Dining.pptx'),
  pythonExecutable:'/Users/darshchaudhary/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
  fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(tmp,'validation.json')
});
console.log(`Created 6 slides in ${font}`);
