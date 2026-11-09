"""Static PRD consistency checks; does not test production business execution."""
from pathlib import Path
import json,re,hashlib,sys
from urllib.parse import unquote
p=Path(__file__).resolve().parent.parent
checks=[]
def check(name,condition,detail=None):
 checks.append({'name':name,'status':'PASS' if condition else 'FAIL','detail':detail})
def read(path):return json.loads(path.read_text())
for f in p.rglob('*.json'):
 if f.name=='result.json':continue
 try:read(f)
 except Exception as e:check('json:'+str(f.relative_to(p)),False,str(e))
base=read(p/'validation/audit/fields.json');active=read(p/'contracts/fields.json');ext=read(p/'contracts/fields-extension.json')
check('基础字段保留且逐对象一致',active==[x for x in base if x['module'] not in {'客户','产品','马甲包','户商','户商账户','申请'}],len(active))
check('扩展字段保留且逐对象一致',ext==[x for x in read(p/'validation/audit/fields-extension.json') if x['module'] not in {'户商','审批'}],len(ext))
check('字段索引无遗漏',all('### '+f['module']+'.'+f['key'] in (p/'FIELDS.md').read_text() for f in active+ext))
old=read(p/'contracts/openapi.json');api=read(p/'contracts/openapi-current.json');hashes=read(p/'validation/audit/original-api-path-hashes.json')
check('原123路径完整保留',len(old['paths'])==123 and all(api['paths'].get(k)==v and hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==hashes[k] for k,v in old['paths'].items()))
new=read(p/'contracts/reference-api-delta.json')['new_paths'];check('只新增指定4引用目录路径',len(api['paths'])==127 and set(api['paths'])-set(old['paths'])==set(new))
removed=read(p/'contracts/removed-api-paths.json');removed={x['path'] for x in removed};check('退役路径未恢复',not (set(api['paths'])&removed))
refs=[]
def walk(x):
 if isinstance(x,dict):
  if '$ref' in x:refs.append(x['$ref'])
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(api);bad=[]
for ref in refs:
 try:
  assert ref.startswith('#/')
  v=api
  for part in ref[2:].split('/'):v=v[part.replace('~1','/').replace('~0','~')]
 except Exception:bad.append(ref)
check('OpenAPI本地引用可解析',not bad,{'references':len(refs),'invalid':bad})
ids=[];missing=[];params_bad=[]
for path,verbs in api['paths'].items():
 for method,o in verbs.items():
  if method not in ['get','post','put','patch','delete','head','options']:continue
  ids.append(o.get('operationId'))
  if not o.get('responses'):missing.append(path+':'+method)
  placeholders=set(re.findall(r'\{([^}]+)\}',path))
  provided={x.get('name') for x in o.get('parameters',[])+verbs.get('parameters',[]) if x.get('in')=='path' and x.get('required')}
  # Resolve original reusable parameter refs.
  for a in o.get('parameters',[])+verbs.get('parameters',[]):
   if '$ref' in a:
    v=api
    for t in a['$ref'][2:].split('/'):v=v[t]
    if v.get('in')=='path' and v.get('required'):provided.add(v['name'])
  if placeholders-provided:params_bad.append([method,path,sorted(placeholders-provided)])
check('operationId唯一且响应非空',None not in ids and len(ids)==len(set(ids)) and not missing,{'operations':len(ids)})
check('路径参数声明完整',not params_bad,params_bad)
menus=['accounts','launch','monitor','rules','assets','environments','channels','system'];reg=read(p/'contracts/permission-registry.json');mapping=read(p/'contracts/menu-action-map.json')
check('八菜单与动作映射完整',reg['menus']==menus and mapping['menus']==menus and set(mapping['actions'])==set(reg['permissions']) and all(v in menus for v in mapping['actions'].values()))
check('退役权限不可授予',not any(x.startswith(('requests.','products.','clients.','packages.','vendors.','resource.')) for x in reg['permissions']))
rs=read(p/'requirements.json');cases=read(p/'acceptance-cases.json');tasks=read(p/'development-tasks.json');rid=[r['id'] for r in rs];tid=[c['id'] for c in cases]
check('需求与验收唯一且双向覆盖',len(rid)==len(set(rid)) and len(tid)==len(set(tid)) and {c['requirement_id'] for c in cases}==set(rid) and {r['test_id'] for r in rs}==set(tid),{'requirements':len(rs),'acceptance_cases':len(cases)})
check('验收不伪称生产通过',all(c['status']=='NOT_RUN' for c in cases))
check('开发任务覆盖全部需求',set(rid)=={r for t in tasks for r in t['requirements']},len(tasks))
seen=set();acyclic=True
for t in tasks:
 if not set(t['depends_on'])<=seen:acyclic=False
 seen.add(t['id'])
check('开发依赖无前向缺失或环',acyclic)
prd=(p/'PRD-ORBIT.md').read_text();check('PRD正文包含全部FR与AT',all(r['id'] in prd and r['test_id'] in prd for r in rs))
check('最新布局及生产边界明确',all(x in prd for x in ['单列上下','不要求任意数据量一屏显示','隐藏iframe']))
links_bad=[]
for f in p.glob('*.md'):
 for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',f.read_text()):
  if re.match(r'^(https?://|mailto:|#)',target):continue
  dest=unquote(target.split('#')[0])
  if not (f.parent/dest).exists():links_bad.append([f.name,target])
check('当前文档相对链接有效',not links_bad,links_bad)
result={'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','scope':'静态需求/合同/覆盖校验；不是生产业务或完整OpenAPI规范认证','checks':checks,'passed':sum(x['status']=='PASS' for x in checks),'failed':sum(x['status']=='FAIL' for x in checks)}
(p/'validation/result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['failed']==0 else 1)
