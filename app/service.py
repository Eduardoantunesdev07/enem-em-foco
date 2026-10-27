"""Practice and grading rules. Answer keys are returned only after submission."""
from uuid import uuid4


class InvalidRequest(ValueError):
    pass


def get_attempt(db, attempt_id):
    row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
    if row is None:
        raise InvalidRequest('Tentativa não encontrada.')
    return row


def attempt_questions(db, attempt):
    return db.execute('''SELECT q.*,a.selected_option,n.reason,n.note FROM questions q LEFT JOIN answers a
        ON a.question_id=q.id AND a.attempt_id=?
        LEFT JOIN error_notes n ON n.question_id=q.id
        WHERE q.exam_id=? AND q.language IN ('comum',?) ORDER BY q.number''',
        (attempt['id'], attempt['exam_id'], attempt['language'])).fetchall()


def start_attempt(db, exam_id, language):
    if language not in ('ingles', 'espanhol'):
        raise InvalidRequest('Selecione inglês ou espanhol.')
    if not db.execute('SELECT 1 FROM exams WHERE id=?', (exam_id,)).fetchone():
        raise InvalidRequest('Prova não encontrada.')
    attempt_id = str(uuid4())
    db.execute('INSERT INTO attempts(id,exam_id,language) VALUES(?,?,?)', (attempt_id, exam_id, language))
    return attempt_id


def save_answer(db, attempt_id, question_id, option):
    attempt = get_attempt(db, attempt_id)
    if attempt['status'] != 'in_progress':
        raise InvalidRequest('Esta tentativa já foi corrigida.')
    if option is not None and option not in tuple('ABCDE'):
        raise InvalidRequest('Alternativa inválida.')
    question = db.execute("SELECT 1 FROM questions WHERE id=? AND exam_id=? AND language IN ('comum',?)",
                          (question_id, attempt['exam_id'], attempt['language'])).fetchone()
    if not question:
        raise InvalidRequest('Questão não pertence a esta prova ou idioma.')
    if option is None:
        db.execute('DELETE FROM answers WHERE attempt_id=? AND question_id=?', (attempt_id, question_id))
    else:
        db.execute('''INSERT INTO answers(attempt_id,question_id,selected_option) VALUES(?,?,?)
            ON CONFLICT(attempt_id,question_id) DO UPDATE SET selected_option=excluded.selected_option,
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')''', (attempt_id, question_id, option))


def serialize_attempt(db, attempt_id):
    attempt = get_attempt(db, attempt_id)
    submitted = attempt['status'] == 'submitted'
    questions = []
    totals = {'correct': 0, 'wrong': 0, 'blank': 0, 'cancelled': 0, 'valid': 0}
    areas = {}
    for row in attempt_questions(db, attempt):
        question = {key: row[key] for key in ('id', 'number', 'language', 'area', 'page', 'selected_option')}
        if submitted:
            question.update(reason=row['reason'],note=row['note'])
            status = ('cancelled' if row['cancelled'] else 'blank' if row['selected_option'] is None
                      else 'correct' if row['selected_option'] == row['correct_option'] else 'wrong')
            question.update(correct_option=row['correct_option'], cancelled=bool(row['cancelled']), result=status)
            totals[status] += 1
            area = areas.setdefault(row['area'], {'correct': 0, 'valid': 0})
            if not row['cancelled']:
                totals['valid'] += 1
                area['valid'] += 1
                area['correct'] += int(status == 'correct')
        questions.append(question)
    result = dict(attempt)
    result['questions'] = questions
    result['exam'] = dict(db.execute('SELECT id,year,day,color,booklet,paper_path,source_page FROM exams WHERE id=?',
                                    (attempt['exam_id'],)).fetchone())
    if submitted:
        result['score'] = {**totals, 'percent': round(100 * totals['correct'] / totals['valid'], 1) if totals['valid'] else 0,
                           'areas': areas}
    return result


def submit_attempt(db, attempt_id):
    get_attempt(db, attempt_id)
    db.execute("""UPDATE attempts SET status='submitted',submitted_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE id=? AND status='in_progress'""", (attempt_id,))
    return serialize_attempt(db, attempt_id)
