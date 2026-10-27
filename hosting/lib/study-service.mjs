import catalog from '../content/catalog.mjs';
import videos from '../content/videos.json' with { type: 'json' };

const exams = new Map(catalog.exams.map(exam => [exam.id, exam]));
const questions = new Map(catalog.questions.map(question => [question.id, question]));
const COOKIE = 'enem_progress';
const now = () => new Date().toISOString();
class InvalidRequest extends Error { constructor(message,status=400){super(message);this.status=status;} }

function visitor(request) {
  const raw = (request.headers.get('Cookie') || '').split(';').map(part=>part.trim()).find(part=>part.startsWith(COOKIE+'='))?.slice(COOKIE.length+1);
  const valid = raw && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(raw);
  const id = valid ? raw : crypto.randomUUID();
  return {id,cookie:valid?null:`${COOKIE}=${id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${new URL(request.url).protocol==='https:'?'; Secure':''}`};
}

async function getAttempt(db,id,owner) {
  const attempt=await db.prepare('SELECT * FROM attempts WHERE id=? AND owner=?').bind(id,owner).first();
  if(!attempt)throw new InvalidRequest('Tentativa não encontrada.',404);
  return attempt;
}

function examQuestions(attempt) {
  return catalog.questions.filter(q=>q.exam_id===attempt.exam_id && (q.language==='comum'||q.language===attempt.language)).sort((a,b)=>a.number-b.number);
}

async function serialize(db,attempt,owner) {
  const [answerResult,noteResult] = await Promise.all([
    db.prepare('SELECT question_id,selected_option FROM answers WHERE attempt_id=?').bind(attempt.id).all(),
    attempt.status==='submitted'?db.prepare('SELECT * FROM error_notes WHERE owner=?').bind(owner).all():Promise.resolve({results:[]}),
  ]);
  const answers=new Map(answerResult.results.map(row=>[row.question_id,row.selected_option]));
  const notes=new Map(noteResult.results.map(row=>[row.question_id,row]));
  const submitted=attempt.status==='submitted';
  const totals={correct:0,wrong:0,blank:0,cancelled:0,valid:0,areas:{}};
  const resultQuestions=examQuestions(attempt).map(q=>{
    const selected=answers.get(q.id)??null;
    const item={id:q.id,number:q.number,language:q.language,area:q.area,page:q.page,selected_option:selected};
    if(submitted){
      const status=q.cancelled?'cancelled':selected===null?'blank':selected===q.correct_option?'correct':'wrong';
      Object.assign(item,{correct_option:q.correct_option,cancelled:Boolean(q.cancelled),result:status,reason:notes.get(q.id)?.reason??null,note:notes.get(q.id)?.note??null});
      totals[status]++;
      const area=totals.areas[q.area]??={correct:0,valid:0};
      if(!q.cancelled){totals.valid++;area.valid++;if(status==='correct')area.correct++;}
    }
    return item;
  });
  const exam=exams.get(attempt.exam_id);
  const {owner:discarded,...safeAttempt}=attempt;
  const result={...safeAttempt,questions:resultQuestions,exam:{id:exam.id,year:exam.year,day:exam.day,color:exam.color,booklet:exam.booklet,page_count:exam.page_count,source_page:exam.source_page}};
  if(submitted)result.score={...totals,percent:totals.valid?Math.round(totals.correct/totals.valid*1000)/10:0};
  return result;
}

async function errorRows(db,owner) {
  const [answerRows,noteRows]=await Promise.all([
    db.prepare("SELECT a.question_id,a.selected_option FROM answers a JOIN attempts t ON t.id=a.attempt_id WHERE t.owner=? AND t.status='submitted'").bind(owner).all(),
    db.prepare('SELECT * FROM error_notes WHERE owner=?').bind(owner).all(),
  ]);
  const ids=new Set(answerRows.results.filter(a=>{const q=questions.get(a.question_id);return q&&!q.cancelled&&a.selected_option!==q.correct_option;}).map(a=>a.question_id));
  const notes=new Map(noteRows.results.map(n=>[n.question_id,n]));
  return [...ids].map(id=>{
    const q=questions.get(id),exam=exams.get(q.exam_id),note=notes.get(id);
    return {id:q.id,number:q.number,area:q.area,language:q.language,year:exam.year,day:exam.day,reason:note?.reason??null,note:note?.note??null,updated_at:note?.updated_at??null};
  }).sort((a,b)=>b.year-a.year||a.number-b.number);
}

export async function handleApi(request,db) {
  const person=visitor(request);
  const respond=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...(person.cookie?{'Set-Cookie':person.cookie}:{})}});
  try {
    const path=new URL(request.url).pathname;
    if(request.method==='GET') {
      if(path==='/api/exams')return respond({exams:catalog.exams.map(e=>({id:e.id,year:e.year,day:e.day,color:e.color,booklet:e.booklet,page_count:e.page_count,source_page:e.source_page,question_count:90})),question_count:catalog.questions.length});
      if(path==='/api/videos')return respond(videos);
      if(!db)throw new InvalidRequest('O banco de estudos está temporariamente indisponível.',503);
      if(path==='/api/history') {
        const rows=await db.prepare('SELECT * FROM attempts WHERE owner=? ORDER BY created_at DESC,id DESC').bind(person.id).all();
        return respond(await Promise.all(rows.results.map(async row=>{
          const exam=exams.get(row.exam_id),{owner,...item}=row;
          return {...item,year:exam.year,day:exam.day,...(row.status==='submitted'?{score:(await serialize(db,row,person.id)).score}:{})};
        })));
      }
      if(path==='/api/errors')return respond(await errorRows(db,person.id));
      const match=path.match(/^\/api\/attempts\/([\w-]+)$/);
      if(match)return respond(await serialize(db,await getAttempt(db,match[1],person.id),person.id));
    } else if(request.method==='POST') {
      const origin=request.headers.get('Origin');
      if(origin&&origin!==new URL(request.url).origin)throw new InvalidRequest('Origem não permitida.',403);
      if(request.headers.get('Content-Type')?.split(';')[0]!=='application/json')throw new InvalidRequest('Envie os dados em JSON.',415);
      const body=await request.text();
      if(body.length>100_000)throw new InvalidRequest('Pedido muito grande.');
      let data;
      try{data=JSON.parse(body);}catch{throw new InvalidRequest('Dados inválidos.');}
      if(!data||typeof data!=='object'||Array.isArray(data))throw new InvalidRequest('Dados inválidos.');
      if(!db)throw new InvalidRequest('O banco de estudos está temporariamente indisponível.',503);
      if(path==='/api/attempts') {
        const exam=exams.get(Number(data.exam_id));
        if(!exam)throw new InvalidRequest('Prova não encontrada.');
        const language=data.language??'ingles';
        if(!['ingles','espanhol'].includes(language))throw new InvalidRequest('Selecione inglês ou espanhol.');
        const id=crypto.randomUUID();
        await db.prepare("INSERT INTO attempts(id,owner,exam_id,language,created_at,status) VALUES(?,?,?,?,?,'in_progress')").bind(id,person.id,exam.id,language,now()).run();
        return respond({id},201);
      }
      const match=path.match(/^\/api\/attempts\/([\w-]+)\/(answer|submit)$/);
      if(match) {
        const attempt=await getAttempt(db,match[1],person.id);
        if(match[2]==='submit') {
          await db.prepare("UPDATE attempts SET status='submitted',submitted_at=? WHERE id=? AND owner=? AND status='in_progress'").bind(now(),attempt.id,person.id).run();
          return respond(await serialize(db,await getAttempt(db,attempt.id,person.id),person.id));
        }
        if(attempt.status!=='in_progress')throw new InvalidRequest('Esta tentativa já foi corrigida.');
        const question=questions.get(Number(data.question_id));
        if(!question||question.exam_id!==attempt.exam_id||!['comum',attempt.language].includes(question.language))throw new InvalidRequest('Questão não pertence a esta prova ou idioma.');
        const option=data.option??null;
        if(option!==null&&!['A','B','C','D','E'].includes(option))throw new InvalidRequest('Alternativa inválida.');
        if(option===null) {
          await db.prepare("DELETE FROM answers WHERE attempt_id=? AND question_id=? AND EXISTS(SELECT 1 FROM attempts WHERE id=? AND owner=? AND status='in_progress')").bind(attempt.id,question.id,attempt.id,person.id).run();
        } else {
          await db.prepare(`INSERT INTO answers(attempt_id,question_id,selected_option,updated_at) SELECT ?,?,?,? WHERE EXISTS(SELECT 1 FROM attempts WHERE id=? AND owner=? AND status='in_progress') ON CONFLICT(attempt_id,question_id) DO UPDATE SET selected_option=excluded.selected_option,updated_at=excluded.updated_at WHERE EXISTS(SELECT 1 FROM attempts WHERE id=? AND owner=? AND status='in_progress')`).bind(attempt.id,question.id,option,now(),attempt.id,person.id,attempt.id,person.id).run();
        }
        if((await getAttempt(db,attempt.id,person.id)).status!=='in_progress')throw new InvalidRequest('Esta tentativa já foi corrigida.');
        return respond({saved:true});
      }
      if(path==='/api/notes') {
        const questionId=Number(data.question_id),reason=data.reason,note=data.note??'';
        if(!['conteudo','atencao','interpretacao','tempo'].includes(reason)||typeof note!=='string'||note.length>5000)throw new InvalidRequest('Anotação inválida.');
        if(!(await errorRows(db,person.id)).some(q=>q.id===questionId))throw new InvalidRequest('Esta questão ainda não está no caderno de erros.');
        await db.prepare('INSERT INTO error_notes(owner,question_id,reason,note,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(owner,question_id) DO UPDATE SET reason=excluded.reason,note=excluded.note,updated_at=excluded.updated_at').bind(person.id,questionId,reason,note,now()).run();
        return respond({saved:true});
      }
    }
    return respond({error:'Página não encontrada.'},404);
  } catch(error) {
    if(error instanceof InvalidRequest)return respond({error:error.message},error.status);
    console.error('Study request failed:',error instanceof Error?error.message:'Unknown error');
    return respond({error:'Não foi possível concluir. Tente novamente.'},500);
  }
}
