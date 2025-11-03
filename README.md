Plataforma Sentinela

Este é o repositório do projeto "Plataforma Sentinela", um Trabalho de Conclusão de Curso (TCC) do curso de Engenharia da Computação.

O projeto consiste na construção de uma plataforma de engenharia de dados para analisar, em larga escala, o conteúdo textual gerado por utilizadores (como comentários do YouTube) utilizando técnicas de busca semântica com Inteligência Artificial.

🚀 Stack Tecnológico

 - Linguagem: Python 3.9

 - Framework da API: FastAPI

 - Processamento Assíncrono: Celery & Celery Beat

 - Fila de Mensagens: RabbitMQ

 - Base de Dados Relacional: PostgreSQL

 - Base de Dados Vetorial: ChromaDB (0.5.x)

 - IA (Embeddings): Sentence-Transformers

 - Ambiente: Docker & Docker Compose

🛠️ Como Executar o Projeto

Certifique-se de que tem o Git, Docker e Docker Compose instalados na sua máquina.

1. Clonar o repositório:

 - git clone [https://github.com/GiulianoMC/sentinel_plataform.git](https://github.com/GiulianoMC/sentinel_plataform.git)


2. Navegar para a pasta do projeto:

 - cd sentinel_plataform


3. Configurar o Ambiente (Obrigatório)

 - Este projeto usa um ficheiro .env para gerir dados sensíveis, como a sua chave de API do YouTube e as credenciais da base de dados.

 - Crie uma cópia do ficheiro .env.example e renomeie-a para .env.

   - cp .env.example .env

   - Abra o ficheiro .env num editor (ex: nano .env).

   - Insira a sua YOUTUBE_API_KEY (obtida na Google Cloud Console) no campo correspondente.

4. Construir e iniciar os contentores:

 - docker-compose up --build


5. Verificar a execução:

 - O sistema completo demora alguns segundos a arrancar.

 - A API principal estará disponível em: http://localhost:8001

 - A Documentação Interativa (Swagger) estará em: http://localhost:8001/docs

 - A API do ChromaDB (base vetorial) estará em: http://localhost:8000

 - A interface de gestão do RabbitMQ estará em: http://localhost:15672 (user: guest, pass: guest)

📖 Fluxo de Uso Básico

 1. Cadastre um Vídeo:

   - Aceda à documentação da API: http://localhost:8001/docs.

   - Use o endpoint POST /video/register.

   - Submeta o URL de um vídeo do YouTube que você deseja monitorizar (ex: {"video_url": "https://www.youtube.com/watch?v=..."}).

2. Aguarde a Coleta Automática:

   - O Celery Beat (o nosso "relógio") irá detetar o novo vídeo na sua próxima verificação (a cada 60 segundos).

   - Ele irá disparar os Celery Workers para buscar todos os comentários desse vídeo e guardá-los no ChromaDB.

   - Você pode observar este processo em tempo real nos logs do docker-compose.

 3. Faça uma Busca Semântica:

   - Use o endpoint POST /semantic-search/semantic-search.

   - Faça uma pergunta (ex: {"query": "opiniões sobre a bateria"}).

Para uma busca mais rápida e filtrada, passe o youtube_id que você deseja pesquisar (ex: {"query": "opiniões sobre a bateria", "youtube_id": "vPsayRIEJmE"}).
