# ENEM em Foco — versão online

Versão hospedada com o mesmo layout, provas e VideoAulas do projeto original. A aplicação roda no navegador; não é necessário instalar Python ou executar um arquivo local.

O catálogo de provas é versionado em `content/catalog.mjs`. As páginas e os PDFs ficam em `public/`. Tentativas, respostas e anotações são salvas no Cloudflare D1. Os registros são separados por um identificador aleatório em cookie HttpOnly, persistente por um ano: não são compartilhados entre visitantes. Ao limpar os cookies ou usar outro navegador, um novo espaço de estudos é criado. Não há sincronização entre dispositivos nesta versão.

Nenhuma tentativa, resposta ou anotação do banco local foi importada para a hospedagem. O servidor retorna o gabarito apenas após a entrega da tentativa correspondente ao visitante.

## Desenvolvimento

- `npm run dev` inicia a prévia local.
- `npm run db:generate` gera novas migrações após alterações em `db/schema.ts`.
- `node --test tests/study.test.mjs` verifica a correção nos seis cadernos e dois idiomas, o tratamento de anulações e a separação dos visitantes.
- A publicação segue o fluxo de hospedagem Sites, com `.openai/hosting.json` e as migrações de `drizzle/`.

As fontes das provas e dos vídeos estão no repositório original ENEM em Foco. Os vídeos são exibidos pelo player do YouTube e precisam estar disponíveis nesse serviço.
