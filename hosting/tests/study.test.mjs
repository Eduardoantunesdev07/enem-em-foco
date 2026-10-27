import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {handleApi} from '../lib/study-service.mjs';
import catalog from '../content/catalog.mjs';

function database() {
  const sqlite=new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('../drizzle/0000_sloppy_war_machine.sql',import.meta.url),'utf8'));
  return {close:()=>sqlite.close(),prepare(sql){let args=[];const query={bind(...values){args=values;return query;},async first(){return sqlite.prepare(sql).get(...args)??null;},async all(){return {results:sqlite.prepare(sql).all(...args)};},async run(){return {meta:sqlite.prepare(sql).run(...args)};}};return query;}};
}

function client(db) {
  let cookie='';
  return {get cookie(){return cookie;},async call(path,data,extra={}){
    const response=await handleApi(new Request('https://study.example'+path,{method:data===undefined?'GET':'POST',headers:{...(cookie?{Cookie:cookie}:{}),...(data===undefined?{}:{'Content-Type':'application/json'}),...extra},...(data===undefined?{}:{body:JSON.stringify(data)})}),db);
    const next=response.headers.get('Set-Cookie');if(next)cookie=next.split(';')[0];
    return {status:response.status,data:await response.json(),headers:response.headers};
  }};
}

test('catalog exposes six exams and no answer keys; visitor cookie persists',async()=>{
  const db=database();try{const visitor=client(db);const result=await visitor.call('/api/exams');
    assert.equal(result.status,200);assert.equal(result.data.exams.length,6);assert.equal(result.data.question_count,555);
    assert(!JSON.stringify(result.data).includes('correct_option'));
    assert.match(result.headers.get('Set-Cookie'),/HttpOnly; SameSite=Lax; Max-Age=31536000; Secure/);
    assert.equal((await visitor.call('/api/history')).headers.get('Set-Cookie'),null);
  }finally{db.close();}
});

test('all six exams grade correctly in both languages, excluding annulled items',async()=>{
  const db=database();try{const visitor=client(db);
    for(const exam of catalog.exams)for(const language of ['ingles','espanhol']){
      const created=await visitor.call('/api/attempts',{exam_id:exam.id,language});assert.equal(created.status,201);
      const path='/api/attempts/'+created.data.id;
      const draft=await visitor.call(path);assert.equal(draft.data.questions.length,90);assert(!JSON.stringify(draft.data).includes('correct_option'));
      const questions=catalog.questions.filter(q=>q.exam_id===exam.id&&['comum',language].includes(q.language));
      for(const q of questions)assert.equal((await visitor.call(path+'/answer',{question_id:q.id,option:q.correct_option??'A'})).status,200);
      const result=await visitor.call(path+'/submit',{});
      assert.equal(result.data.score.percent,100);assert.equal(result.data.score.wrong,0);assert.equal(result.data.score.blank,0);
      assert.equal(result.data.score.cancelled,questions.filter(q=>q.cancelled).length);
    }
  }finally{db.close();}
});

test('different visitors cannot access each other’s attempts, history, errors or notes',async()=>{
  const db=database();try{const a=client(db),b=client(db);
    const created=await a.call('/api/attempts',{exam_id:20251,language:'espanhol'});const path='/api/attempts/'+created.data.id;
    const draft=await a.call(path);const q=draft.data.questions[0];
    assert.equal((await a.call(path+'/answer',{question_id:q.id,option:'A'})).status,200);
    const result=await a.call(path+'/submit',{});assert.equal(result.data.score.wrong,1);
    assert.equal((await a.call('/api/notes',{question_id:q.id,reason:'interpretacao',note:'Somente meu progresso'})).status,200);
    assert.equal((await b.call(path)).status,404);
    assert.equal((await b.call(path+'/answer',{question_id:q.id,option:'B'})).status,404);
    assert.deepEqual((await b.call('/api/history')).data,[]);assert.deepEqual((await b.call('/api/errors')).data,[]);
    assert.equal((await b.call('/api/notes',{question_id:q.id,reason:'conteudo',note:'Outro visitante'})).status,400);
    assert.equal((await a.call(path)).data.questions[0].note,'Somente meu progresso');
  }finally{db.close();}
});

test('saving, replacing, clearing, final correction and blank answers work',async()=>{
  const db=database();try{const visitor=client(db);
    const created=await visitor.call('/api/attempts',{exam_id:20251,language:'ingles'});const path='/api/attempts/'+created.data.id;
    const draft=await visitor.call(path);const [q1,q2]=draft.data.questions;
    await visitor.call(path+'/answer',{question_id:q1.id,option:'A'});await visitor.call(path+'/answer',{question_id:q1.id,option:'D'});
    await visitor.call(path+'/answer',{question_id:q2.id,option:'B'});await visitor.call(path+'/answer',{question_id:q2.id,option:null});
    const result=await visitor.call(path+'/submit',{});assert.equal(result.data.score.correct,1);assert.equal(result.data.score.blank,89);
    assert.equal((await visitor.call(path+'/answer',{question_id:q1.id,option:'A'})).status,400);
    assert.deepEqual((await visitor.call(path+'/submit',{})).data,result.data);
  }finally{db.close();}
});

test('other language/exam questions, invalid answers and cross-origin writes are rejected',async()=>{
  const db=database();try{const visitor=client(db);const created=await visitor.call('/api/attempts',{exam_id:20251,language:'ingles'});const path='/api/attempts/'+created.data.id;
    for(const q of [catalog.questions.find(q=>q.exam_id===20251&&q.language==='espanhol'),catalog.questions.find(q=>q.exam_id===20241)])assert.equal((await visitor.call(path+'/answer',{question_id:q.id,option:'A'})).status,400);
    const q=catalog.questions.find(q=>q.exam_id===20251&&q.language==='ingles');
    assert.equal((await visitor.call(path+'/answer',{question_id:q.id,option:'F'})).status,400);
    assert.equal((await visitor.call('/api/attempts',{exam_id:20251},{Origin:'https://other.example'})).status,403);
  }finally{db.close();}
});

test('video catalogue covers all four exam areas for each year',async()=>{
  const visitor=client(null),result=await visitor.call('/api/videos');assert.equal(result.status,200);assert.equal(result.data.videos.length,14);
  for(const year of [2023,2024,2025])assert.deepEqual(new Set(result.data.videos.filter(v=>v.year===year).flatMap(v=>v.areas)),new Set(['linguagens','humanas','natureza','matematica']));
});
